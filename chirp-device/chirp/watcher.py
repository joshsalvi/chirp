"""
BirdWatch Orchestrator

BirdWatcher ties together all components:
  AudioCapture → DetectionPipeline → RecordingEngine → FileUploader

Also manages:
  - Health monitoring / watchdog
  - Status reporting
  - Graceful startup and shutdown sequencing
"""

import logging
import queue
import threading
import time
from collections import deque
from datetime import datetime
from typing import Dict, Optional

from .audio import AudioCapture
from .detector import DetectionEvent, DetectionPipeline
from .recorder import RecordingEngine
from .uploader import FileUploader
from .utils import format_duration, utc_now
from .bat_detector import BatDetector, attempt_usb_power_cycle

logger = logging.getLogger(__name__)


class BirdWatcher:
    """
    Top-level orchestrator. Create one instance, call start(), then
    call health_check() periodically from the main thread.
    """

    def __init__(self, config: Dict):
        self.config = config
        self._start_time: Optional[datetime] = None
        self._running = False

        # Shared queue: RecordingEngine → FileUploader
        self._upload_queue: queue.Queue = queue.Queue(
            maxsize=config["upload"].get("upload_queue_max_size", 100)
        )

        # Instantiate components
        self._audio = AudioCapture(config)
        self._detector = DetectionPipeline(config, self._audio)
        self._recorder = RecordingEngine(config, self._audio, self._upload_queue)
        self._uploader = FileUploader(config, self._upload_queue)

        # Experimental: bat echolocation detector. Entirely independent of
        # the bird audio pipeline above (separate ultrasonic USB mic at a
        # much higher sample rate) — internally a no-op unless explicitly
        # enabled in config AND a compatible device is found, so this is
        # always safe to instantiate even on a setup with no such hardware.
        self._bat_detector = BatDetector(config)

        # Wire detection → recording
        self._detector.add_callback(self._on_detection)
        # Rate-limit tracking (rolling 1-hour window of trigger timestamps)
        self._hourly_trigger_times = []

        # Health check
        self._health_interval: float = config["system"]["health_check_interval_seconds"]
        self._last_health_log: float = 0.0

        # Escalation tracking for BatDetector.is_stalled() recoveries (see
        # health_check() below). Kept on THIS object, not on BatDetector
        # itself, because a stall recovery replaces self._bat_detector with
        # a fresh instance — any counter living on the detector would be
        # wiped out by the very recovery it's supposed to be counting.
        # A deque of recovery timestamps rather than a plain counter so
        # escalation is based on recoveries clustering within a real
        # window (repeated failures close together), not a lifetime total
        # that would eventually trip even if each individual recovery
        # actually held for weeks in between.
        bat_cfg = (config.get("detection", {}) or {}).get("bat_echolocation", {}) or {}
        self._bat_stall_escalation_window_s: float = float(
            bat_cfg.get("stall_escalation_window_hours", 12.0)
        ) * 3600.0
        self._bat_stall_recoveries_before_hard_reset: int = int(
            bat_cfg.get("stall_recoveries_before_hard_reset", 2)
        )
        self._bat_stall_recovery_times: deque = deque(
            maxlen=max(1, self._bat_stall_recoveries_before_hard_reset)
        )
        # Wall-clock (not monotonic) so this is anchored to when the chirp-device
        # PROCESS started, not how long the Pi has been booted — monotonic time
        # is relative to system boot, which could already be >24h on a long-
        # uptime Pi, causing maintenance to fire immediately on every service
        # restart instead of once per real day of operation.
        self._last_daily_maintenance: float = time.time()
        self._status_lock = threading.Lock()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """
        Start all components in correct order.
        Raises RuntimeError if critical components fail to initialize.
        """
        logger.info("BirdWatcher starting...")
        self._start_time = utc_now()

        # 0. Make sure there's actually a network connection before doing
        # anything else — see ble_provisioning.py for what happens if
        # not (advertises a temporary Bluetooth setup mode for the phone
        # app to hand over WiFi credentials). Fast no-op if connected.
        try:
            from .ble_provisioning import run_setup_if_needed
            run_setup_if_needed()
        except Exception as e:
            logger.warning("Network/BLE setup check failed (continuing anyway): %s", e)

        # 1. Start audio capture
        logger.info("Step 1/4: Initializing audio capture...")
        if not self._audio.start():
            raise RuntimeError(
                "Failed to start audio capture. "
                "Check USB microphone connections and run: python -m main --list-devices"
            )
        logger.info(
            "  Audio: %d USB mic(s) at %d Hz, %.1f-second pre-roll buffer",
            self._audio.device_count,
            self.config["audio"]["sample_rate"],
            self.config["detection"]["pre_roll_seconds"],
        )

        # 2. Load BirdNET model
        logger.info("Step 2/4: Loading BirdNET model...")
        if not self._detector.load_model():
            raise RuntimeError(
                "Failed to load BirdNET model. "
                "Run: pip install birdnetlib"
            )

        # 3. Start recorder and uploader
        logger.info("Step 3/4: Starting recording engine...")
        self._recorder.start()
        logger.info(
            "  Recordings → %s",
            self.config["recording"]["output_dir"],
        )

        logger.info("Step 4/4: Starting uploader...")
        self._uploader.start()

        # 4. Start detection (last — begins consuming audio immediately)
        self._detector.start()

        # 5. Experimental bat detector — only actually starts if enabled in
        # config AND a compatible high-sample-rate ultrasonic mic is found;
        # never blocks bird detection from running either way.
        if self._bat_detector.start():
            logger.info("  Bat echolocation detector (experimental): ACTIVE")
        elif self._bat_detector.enabled:
            logger.info("  Bat echolocation detector (experimental): enabled but no compatible device found")

        self._running = True
        logger.info("=" * 60)
        logger.info("✅ BirdWatch is RUNNING")
        logger.info("   Backend:    BirdNET (%s)", self.config["detection"]["birdnet"]["backend"].upper())
        logger.info("   Threshold:  %.0f%% confidence", self.config["detection"]["birdnet"]["min_confidence"] * 100)
        logger.info("   Rec duration: %.0fs + %.0fs pre-roll",
                    self.config["recording"]["duration_seconds"],
                    self.config["detection"]["pre_roll_seconds"])
        logger.info("   Upload:     %s",
                    "ENABLED → " + self.config["upload"]["server_url"]
                    if self.config["upload"]["enabled"]
                    else "DISABLED (local save only)")
        logger.info("=" * 60)

    def stop(self) -> None:
        """Gracefully stop all components."""
        if not self._running:
            return

        logger.info("BirdWatcher stopping...")
        self._running = False

        # Stop in reverse order
        self._detector.stop()
        self._recorder.stop()
        self._uploader.stop()
        self._audio.stop()
        self._bat_detector.stop()

        uptime = format_duration(
            (utc_now() - self._start_time).total_seconds()
            if self._start_time else 0
        )
        logger.info("BirdWatcher stopped after %s. Final stats:", uptime)
        logger.info("  Detection:  %s", self._detector._format_stats())
        logger.info("  BirdNET:    %s", self._detector.get_birdnet_stats())
        logger.info("  Recording:  %d completed", self._recorder.stats["recordings_completed"])
        logger.info("  Upload:     %s", self._uploader.get_stats_str())

    def is_running(self) -> bool:
        return self._running

    def apply_config(self, new_config: Dict) -> None:
        """
        Hot-apply a new merged config from the server without restarting.
        Updates runtime parameters on each component that supports it.
        Safe to call from any thread — components use their own locks.
        """
        logger.info("Applying server config update...")
        # Snapshot old values BEFORE updating self.config
        old_mph = self.config.get("recording", {}).get("max_per_hour", 0)
        self.config = new_config
        try:
            # ── Always keep every component's config reference in sync first ──
            # Previously this only happened inside per-field `if changed:` blocks
            # below, which meant a push that changed ONLY lat/lon (say) would
            # leave self._detector.config and self._recorder.config pointing at
            # the OLD config object for every other field too. Doing this
            # unconditionally, before any field-specific logic, is what makes
            # the dynamic self.config.get(...) reads in birdnet_cpu.py actually
            # see live data — see CHANGELOG for the detection-stops-working bug
            # this caused.
            self._detector.config = new_config
            self._recorder.config = new_config

            # Hot-swap the backend FIRST, before the field-level updates
            # below — if this changes self._detector._birdnet to a new
            # instance, we need `birdnet_instance` (fetched next) to be
            # that new instance, not the stale one, so min_confidence/
            # lat/lon/blacklist/whitelist land on the right object.
            try:
                backend_switched = self._detector.switch_birdnet_backend(new_config)
                if backend_switched:
                    logger.info("  BirdNET backend hot-swapped (no restart needed)")
            except Exception as e:
                logger.error("Backend hot-swap failed, keeping previous backend: %s", e)

            birdnet_cfg = new_config.get("detection", {}).get("birdnet", {})
            birdnet_instance = getattr(self._detector, "_birdnet", None)
            if birdnet_instance is not None:
                # Keep the BirdNET instance's own config pointed at the SAME
                # live sub-dict (not a stale copy from __init__) — this is the
                # root fix. Every field birdnet_cpu.py reads via self.config.get(...)
                # (min_confidence, latitude, longitude, species_blacklist,
                # species_whitelist) now sees current data automatically,
                # without needing a separate patch here for each one.
                birdnet_instance.config = birdnet_cfg

            # BirdNET confidence threshold — logging only; the actual value
            # change is now picked up automatically via the live config
            # reference set above.
            new_min_conf = birdnet_cfg.get("min_confidence")
            if new_min_conf is not None:
                old_val = getattr(birdnet_instance, "min_confidence", "?") if birdnet_instance else "?"
                logger.info("  BirdNET min_confidence: %s → %.2f", old_val, new_min_conf)

            new_lat = birdnet_cfg.get("latitude")
            new_lon = birdnet_cfg.get("longitude")
            if birdnet_instance is not None and new_lat is not None and new_lon is not None:
                old_lat = getattr(birdnet_instance, "lat", None)
                # Cached attributes still updated too, as a fallback default
                # for the `self.config.get(key, self.X)` pattern in birdnet_cpu.py.
                birdnet_instance.lat = new_lat
                birdnet_instance.lon = new_lon
                if old_lat != new_lat:
                    logger.info("  BirdNET location: %.4f,%.4f (geographic filter now active)",
                                new_lat, new_lon)

            new_blacklist = birdnet_cfg.get("species_blacklist")
            if birdnet_instance is not None and new_blacklist is not None:
                birdnet_instance.species_blacklist = new_blacklist
                logger.info("  BirdNET species_blacklist: %d entries", len(new_blacklist))

            new_whitelist = birdnet_cfg.get("species_whitelist")
            if birdnet_instance is not None and new_whitelist is not None:
                birdnet_instance.species_whitelist = new_whitelist

            # Recording duration
            rec_cfg = new_config.get("recording", {})
            new_dur = rec_cfg.get("duration_seconds")
            if new_dur is not None:
                old_dur = self._recorder.config.get("recording", {}).get("duration_seconds", "?")
                logger.info("  Recording duration: %s → %.0fs", old_dur, new_dur)

            # Cooldown — update both the config dict AND the cached _cooldown attribute
            # so the running detection loop picks up the new value immediately
            new_cooldown = new_config.get("detection", {}).get("cooldown_seconds")
            if new_cooldown is not None:
                old_cooldown = self._detector._cooldown
                self._detector._cooldown = float(new_cooldown)
                self._detector.config = new_config
                logger.info("  Cooldown: %.0fs → %.0fs", old_cooldown, new_cooldown)

            # Stage 1 gate — cached on the detector, so apply it explicitly
            if new_config.get("detection", {}).get("energy_filter"):
                self._detector.update_energy_filter(new_config)

            # Max per hour — compare against snapshot taken before self.config was replaced
            new_mph = new_config.get("recording", {}).get("max_per_hour", 0)
            if new_mph != old_mph:
                self._hourly_trigger_times = []
                logger.info("  Max recordings/hour: %d (window reset)", new_mph)

            # Audio gain — actually apply it to the running stream(s), not
            # just log it. Previously this only logged the new value;
            # AudioStream.gain_linear was computed once at stream-open time
            # and never re-read, so a gain change pushed from the server had
            # zero effect until the device was restarted. If a user pushes a
            # gain boost specifically because the mic is too quiet to trigger
            # detections, that boost needs to take effect immediately.
            audio_cfg = new_config.get("audio", {})
            if "input_gain_db" in audio_cfg:
                new_gain = audio_cfg["input_gain_db"]
                old_gain = getattr(self._audio, "gain_db", "?")
                if new_gain != old_gain:
                    self._audio.update_gain(new_gain)
                    logger.info("  Audio gain: %s → %.1f dB (applied to running stream(s))", old_gain, new_gain)

            # ReSpeaker XVF3800 output routing (raw capsules vs processed beam)
            try:
                self._audio.update_respeaker_output(new_config)
            except Exception as e:
                logger.warning("  XVF3800 output update failed: %s", e)

            # Bat echolocation detector (experimental) — start/stop in place
            # if the server toggled it, without restarting the whole device.
            new_bat_cfg = new_config.get("detection", {}).get("bat_echolocation", {}) or {}
            new_bat_enabled = bool(new_bat_cfg.get("enabled", False))
            if new_bat_enabled != self._bat_detector.enabled:
                if new_bat_enabled:
                    logger.info("  Bat echolocation detector: enabling…")
                    self._bat_detector = BatDetector(new_config)
                    if self._bat_detector.start():
                        logger.info("  Bat echolocation detector: ACTIVE")
                    else:
                        logger.info("  Bat echolocation detector: enabled but no compatible device found")
                else:
                    logger.info("  Bat echolocation detector: disabling…")
                    self._bat_detector.stop()
                    self._bat_detector = BatDetector(new_config)  # fresh disabled instance

            # Bat mic gain — same rationale as the bird pipeline's gain
            # hot-apply above: without this, a gain change pushed while the
            # detector stays enabled would only take effect after a full
            # service restart. Harmless no-op if the detector was just
            # rebuilt above (it already picked up the new gain from
            # new_config in its own __init__) — set_gain_db just re-applies
            # the same value in that case.
            new_bat_gain = float(new_bat_cfg.get("gain_db", 0.0))
            old_bat_gain = getattr(self._bat_detector, "gain_db", "?")
            if self._bat_detector.enabled and new_bat_gain != old_bat_gain:
                self._bat_detector.set_gain_db(new_bat_gain)
                logger.info("  Bat mic gain: %s → %.1f dB (applied to running stream)", old_bat_gain, new_bat_gain)

            logger.info("Config update applied.")
        except Exception as e:
            logger.error("Error applying config update: %s", e)

    # ── Detection Callback ────────────────────────────────────────────────────

    def _on_detection(self, event: DetectionEvent) -> None:
        """Called by DetectionPipeline for each confirmed bird detection."""
        # Enforce max_per_hour rate limit
        max_per_hour = self.config.get("recording", {}).get("max_per_hour", 0)
        if max_per_hour > 0:
            now = time.time()
            # Purge timestamps older than 60 minutes from the rolling window
            window_start = now - 3600.0
            self._hourly_trigger_times = [
                ts for ts in self._hourly_trigger_times if ts > window_start
            ]
            if len(self._hourly_trigger_times) >= max_per_hour:
                logger.debug(
                    "Rate limit: %d/%d recordings in last hour — suppressing trigger",
                    len(self._hourly_trigger_times), max_per_hour,
                )
                return
            self._hourly_trigger_times.append(now)

        self._recorder.trigger(event)

        # Notify OLED display (flash detection page)
        try:
            if hasattr(self, '_display') and self._display:
                top = event.top_detection
                if top:
                    self._display.notify_detection(top.common_name, top.confidence)
        except Exception:
            pass

        # Flash ReSpeaker USB LEDs on detection (non-blocking)
        try:
            rs_cfg = self.config.get("respeaker", {})
            if rs_cfg.get("led_on_detection", True):
                if (hasattr(self._audio, '_respeaker_device') and
                        self._audio._respeaker_device is not None and
                        getattr(self._audio._respeaker_device, 'has_leds', False) and
                        self._audio._respeaker_device.mode == "usb"):
                    from .respeaker import led_detection_flash
                    color = tuple(rs_cfg.get("led_color_detection", [0, 200, 80]))
                    duration = float(rs_cfg.get("led_flash_seconds", 3.0))
                    led_detection_flash(color=color, duration_secs=duration)
        except Exception:
            pass

        # Publish to Zigbee/MQTT if configured
        try:
            if hasattr(self, '_zigbee') and self._zigbee and self._zigbee.enabled:
                top = event.top_detection
                if top:
                    backend = self.config.get("detection", {}).get("birdnet", {}).get("backend", "cpu")
                    self._zigbee.publish_detection(
                        top.common_name,
                        top.confidence,
                        backend=backend,
                    )
        except Exception:
            pass

    # ── Health Check ──────────────────────────────────────────────────────────

    def health_check(self) -> None:
        """
        Periodic health check. Call from main thread every few seconds.
        Logs status, checks watchdogs, restarts hung threads.
        """
        now = time.monotonic()

        # Daily maintenance — runs ~once per 24h of process uptime, anchored
        # to wall-clock time at process start (see __init__ comment).
        now_wall = time.time()
        if now_wall - self._last_daily_maintenance >= 86400:
            self._last_daily_maintenance = now_wall
            try:
                from .utils import daily_maintenance
                daily_maintenance()
            except Exception as e:
                logger.warning("Daily maintenance failed: %s", e)

        if now - self._last_health_log < self._health_interval:
            return

        self._last_health_log = now

        # Check audio streams
        if not self._audio.check_streams():
            logger.error("All audio streams are dead! Attempting recovery...")
            self._audio.stop()
            time.sleep(2.0)
            if not self._audio.start():
                logger.critical("Audio recovery failed. Check USB microphone connections.")
            else:
                logger.info("Audio streams recovered.")

        # Check bat detector stream — a real, previously-missing recovery
        # path. Found via direct investigation of a real report ("AudioMoth
        # keeps crashing daily, only fixes on device reboot"): the bird
        # pipeline above has always had this exact recovery (check_streams
        # → stop → start), but the bat detector had NO equivalent
        # whatsoever — it was only ever (re)created once at startup or on
        # a config change (see _apply_config_update above), so a dead
        # stream stayed dead until the whole process restarted. is_active()
        # (bat_detector.py) is the real fix this depends on: is_running()
        # alone can't detect this, since it only reflects whether start()
        # succeeded once, not whether the stream is still actually alive.
        if self._bat_detector.enabled and self._bat_detector.is_running() and not self._bat_detector.is_active():
            logger.error(
                "Bat detector stream is dead (was running, now inactive). "
                "Attempting recovery — this previously required a full "
                "device reboot to fix."
            )
            self._bat_detector.stop()
            time.sleep(2.0)
            self._bat_detector = BatDetector(self.config)
            if self._bat_detector.start():
                logger.info("Bat detector stream recovered.")
            else:
                logger.critical(
                    "Bat detector recovery failed. Check AudioMoth/ultrasonic "
                    "mic USB connection — if this persists, the device may "
                    "need a full reboot to clear a stuck ALSA handle (see "
                    "bat_detector.py's own comment on this known failure mode)."
                )

        # Check for a stalled (live-but-deaf) bat detector — distinct from
        # the dead-stream case above, and checked as a separate elif so a
        # stream already caught as dead doesn't also get double-handled
        # here. See BatDetector.is_stalled()'s docstring for the real
        # deployment (9 days of zero new pulses with a healthy-reporting
        # stream) this exists to catch, which the dead-stream check above
        # structurally cannot see.
        elif (
            self._bat_detector.enabled
            and self._bat_detector.is_running()
            and self._bat_detector.is_stalled()
        ):
            now_wall2 = time.time()
            self._bat_stall_recovery_times.append(now_wall2)
            # Escalate to a hard USB power-cycle only once several stall
            # recoveries have clustered within the configured window —
            # one isolated stall is worth a normal soft reopen first
            # (cheap, and sometimes genuinely enough to clear it); only a
            # repeating pattern close together justifies reaching for a
            # hardware-level reset.
            recent = [t for t in self._bat_stall_recovery_times
                      if now_wall2 - t <= self._bat_stall_escalation_window_s]
            should_hard_reset = len(recent) >= self._bat_stall_recoveries_before_hard_reset

            if should_hard_reset:
                logger.error(
                    "Bat detector: sensor appears stuck (stream healthy, no "
                    "new pulses for %.1fh during active hours). %d stalls "
                    "within the last %.0fh — attempting a hard USB "
                    "power-cycle before reopening.",
                    self._bat_detector.stuck_pulse_hours, len(recent),
                    self._bat_stall_escalation_window_s / 3600.0,
                )
            else:
                logger.error(
                    "Bat detector: sensor appears stuck (stream healthy, no "
                    "new pulses for %.1fh during active hours). Reopening "
                    "the stream (soft recovery).",
                    self._bat_detector.stuck_pulse_hours,
                )

            if should_hard_reset:
                power_cycled = attempt_usb_power_cycle(self.config)
                if power_cycled:
                    # Give the device a moment to re-enumerate over USB
                    # before trying to reopen the stream against it.
                    time.sleep(5.0)
                else:
                    logger.critical(
                        "Bat detector: repeated stalls detected but hard "
                        "USB power-cycle is unavailable or unconfigured "
                        "(see config.yaml's bat_echolocation."
                        "usb_power_cycle). Falling back to a soft reopen, "
                        "which may not be enough to clear a hardware-level "
                        "AudioMoth fault — manual intervention may be "
                        "needed if this keeps recurring."
                    )
                # Reopening resets the escalation clock either way — a
                # successful hard reset earns a fresh start, and a failed
                # one shouldn't re-trigger every single health check
                # until the window naturally empties on its own.
                self._bat_stall_recovery_times.clear()

            self._bat_detector.stop()
            time.sleep(2.0)
            self._bat_detector = BatDetector(self.config)
            if self._bat_detector.start():
                logger.info("Bat detector stream reopened after stall detection.")
            else:
                logger.critical(
                    "Bat detector: reopen after stall detection failed. "
                    "Check AudioMoth USB connection; a reboot or manual "
                    "power-cycle may be required."
                )

        # Check detection watchdog
        if self._detector.watchdog.is_expired:
            logger.warning(
                "Detection watchdog expired (%.0fs since last activity). "
                "Detection thread may be hung.",
                self._detector.watchdog.elapsed,
            )

        # Log periodic status
        uptime_str = ""
        if self._start_time:
            uptime_seconds = (utc_now() - self._start_time).total_seconds()
            uptime_str = format_duration(uptime_seconds)

        levels = self._audio.get_current_levels_db()
        level_str = " | ".join(
            f"{name.split()[0]}: {db:+.0f}dBFS" for name, db in levels
        )

        logger.info(
            "♥ Status | uptime=%s | %s | triggers=%d | recordings=%d | %s",
            uptime_str,
            level_str,
            self._detector.stats["triggers"],
            self._recorder.stats["recordings_completed"],
            self._uploader.get_stats_str(),
        )
