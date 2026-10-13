"""
BirdWatch Detection Pipeline

Two-stage architecture for efficient, low-latency bird call detection:

Stage 1 — Energy/Frequency Filter (every chunk, ~microseconds):
  Applies a bandpass filter and checks RMS energy against a threshold.
  Cheap guard to avoid running BirdNET on silence/noise.

Stage 2 — BirdNET Analysis (~50-500ms depending on backend):
  Runs the BirdNET deep learning model on a 3-second window.
  Only triggered when Stage 1 passes.
  Returns species identifications with confidence scores.

On confirmed detection: calls registered on_detection callback(s).
"""

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional

import numpy as np
from scipy.signal import butter, sosfilt

from .audio import AudioCapture
from .birdnet_cpu import BirdDetection
from .utils import WatchdogTimer, rms_db, utc_now

logger = logging.getLogger(__name__)


# ── Detection Event ───────────────────────────────────────────────────────────

@dataclass
class DetectionEvent:
    """Encapsulates a confirmed bird detection event."""
    timestamp: datetime
    detections: List[BirdDetection]
    audio_window: np.ndarray  # The 3-second window that triggered detection
    energy_db: float          # Stage 1 energy level

    @property
    def top_detection(self) -> Optional[BirdDetection]:
        if self.detections:
            return max(self.detections, key=lambda d: d.confidence)
        return None

    @property
    def max_confidence(self) -> float:
        if self.detections:
            return max(d.confidence for d in self.detections)
        return 0.0

    @property
    def species_summary(self) -> str:
        if not self.detections:
            return "Unknown"
        names = [d.common_name for d in self.detections[:3]]
        return ", ".join(names)

    def __str__(self) -> str:
        return (
            f"DetectionEvent @ {self.timestamp.strftime('%H:%M:%S')} | "
            f"{len(self.detections)} species | "
            f"Top: {self.top_detection} | "
            f"Energy: {self.energy_db:.1f} dBFS"
        )


# ── Bandpass Filter ───────────────────────────────────────────────────────────

def build_bandpass_sos(
    low_hz: float, high_hz: float, sample_rate: int, order: int
) -> np.ndarray:
    """Build a Butterworth bandpass filter (second-order sections)."""
    nyq = sample_rate / 2.0
    low_norm = low_hz / nyq
    high_norm = high_hz / nyq
    # Clamp to valid range
    low_norm = max(0.001, min(low_norm, 0.999))
    high_norm = max(0.001, min(high_norm, 0.999))
    if low_norm >= high_norm:
        raise ValueError(
            f"Invalid bandpass: [{low_hz}, {high_hz}] Hz at {sample_rate} Hz SR"
        )
    sos = butter(order, [low_norm, high_norm], btype="band", output="sos")
    return sos


# ── Detection Pipeline ────────────────────────────────────────────────────────

class DetectionPipeline:
    """
    Runs detection on audio windows from AudioCapture.
    Calls registered callbacks when a bird is detected.

    Usage:
        pipeline = DetectionPipeline(config, audio_capture)
        pipeline.add_callback(my_function)
        pipeline.start()
        ...
        pipeline.stop()
    """

    def __init__(self, config: Dict, audio_capture: AudioCapture):
        self.config = config
        self.audio = audio_capture
        self.sample_rate: int = config["audio"]["sample_rate"]

        # Stage 1 config
        ef = config["detection"]["energy_filter"]
        self._energy_enabled: bool = ef["enabled"]
        self._threshold_db: float = ef["threshold_db"]
        self._bp_low: float = ef["frequency_band_hz"][0]
        self._bp_high: float = ef["frequency_band_hz"][1]
        self._bp_order: int = ef.get("filter_order", 4)
        self._energy_window_samples: int = int(
            ef["window_seconds"] * self.sample_rate
        )
        self._log_energy: bool = config["logging"].get("log_energy_filter", False)
        # Periodic one-line summary of window levels vs the gate (0 = off).
        # This is what to read when tuning threshold_db for night calls.
        self._stats_interval: float = float(config["logging"].get("window_stats_interval_seconds", 600))
        self._win_levels: List[float] = []
        self._win_stats_t0: float = time.monotonic()
        self._win_stats_base: Dict = {}

        # Stage 2 config
        self._birdnet_enabled: bool = config["detection"]["birdnet"]["enabled"]
        self._min_detections: int = config["detection"].get(
            "min_detections_to_trigger", 1
        )
        self._cooldown: float = config["detection"]["cooldown_seconds"]
        self._log_detections: bool = config["logging"].get("log_detections", True)

        # Build bandpass filter (once, at startup)
        self._sos: Optional[np.ndarray] = None
        if self._energy_enabled:
            try:
                self._sos = build_bandpass_sos(
                    self._bp_low, self._bp_high,
                    self.sample_rate, self._bp_order
                )
                logger.debug(
                    "Bandpass filter built: %.0f–%.0f Hz, order %d",
                    self._bp_low, self._bp_high, self._bp_order,
                )
            except Exception as e:
                logger.error("Failed to build bandpass filter: %s", e)

        # BirdNET backend
        backend = config["detection"]["birdnet"]["backend"]
        self._birdnet = None
        if self._birdnet_enabled:
            if backend == "coral":
                from .birdnet_coral import BirdNetCoral, check_coral_available
                if check_coral_available():
                    self._birdnet = BirdNetCoral(config)
                else:
                    logger.warning(
                        "Coral requested but not available; falling back to CPU."
                    )
                    from .birdnet_cpu import BirdNetCPU
                    self._birdnet = BirdNetCPU(config)
            else:
                from .birdnet_cpu import BirdNetCPU
                self._birdnet = BirdNetCPU(config)

        # Callbacks
        self._callbacks: List[Callable[[DetectionEvent], None]] = []
        self._callback_lock = threading.Lock()

        # Thread control
        self._thread: Optional[threading.Thread] = None
        self._running = threading.Event()

        # Cooldown tracking
        self._last_trigger_time: float = 0.0

        # Watchdog
        self._watchdog = WatchdogTimer(
            config["system"]["watchdog_timeout_seconds"],
            name="DetectionPipeline",
        )

        # Stats
        self.stats = {
            "windows_analyzed": 0,
            "stage1_passed": 0,
            "stage2_passed": 0,
            "triggers": 0,
            "cooldown_skips": 0,
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def load_model(self) -> bool:
        """Load the BirdNET model (must call before start())."""
        if self._birdnet is None:
            logger.warning("BirdNET disabled in config; no model to load.")
            return True
        if self._birdnet.load():
            return True
        if type(self._birdnet).__name__ == "BirdNetCoral":
            # Coral is the default backend; a TPU that's present but won't load
            # (runtime missing, model not compiled) must not stop detection.
            logger.warning("Coral model failed to load; falling back to CPU BirdNET.")
            from .birdnet_cpu import BirdNetCPU
            self._birdnet = BirdNetCPU(self.config)
            return self._birdnet.load()
        return False

    @property
    def active_backend(self) -> Optional[str]:
        """Backend actually running inference ("coral" / "cpu"), which can
        differ from the configured one after a Coral load fallback."""
        if self._birdnet is None:
            return None
        return "coral" if type(self._birdnet).__name__ == "BirdNetCoral" else "cpu"

    def switch_birdnet_backend(self, new_config: Dict) -> bool:
        """
        Hot-swap the active BirdNET backend (cpu <-> coral) without a
        service restart, when detection.birdnet.backend changes via a
        live server config push.

        Root cause this closes: apply_config() previously only ever
        hot-updated fields on the EXISTING birdnet instance (min_confidence,
        lat/lon, blacklist/whitelist) and never touched which backend was
        actually active. Toggling cpu<->coral in the Devices UI and pushing
        it appeared to work — server_sync.py's own reported backend string
        updated immediately — while the real running inference silently
        kept using whichever backend was active at the last service start,
        with nothing telling anyone a restart was actually required. That's
        a confirmed real bug (not user error) behind "I set backend to
        coral and it didn't work."

        Builds and loads a fresh backend instance using the same
        selection+fallback logic __init__ uses, and only swaps it in on
        success — a failed load (e.g. Coral unplugged, bad model file)
        leaves the current, working backend running rather than tearing it
        down first and leaving detection with nothing.

        The swap itself (self._birdnet = new_instance) is a single atomic
        pointer assignment — safe even if an audio analysis thread is
        mid-call: any in-flight call already holds its own reference to the
        OLD instance and finishes normally against it; the next call picks
        up the new one. No lock needed around the swap itself.

        Returns True if the backend actually changed, False if unchanged or
        the load failed (previous backend remains active either way).
        """
        if not self._birdnet_enabled:
            return False

        new_backend_name = new_config.get("detection", {}).get("birdnet", {}).get("backend", "cpu")
        current_is_coral = type(self._birdnet).__name__ == "BirdNetCoral" if self._birdnet else False
        want_coral = new_backend_name == "coral"

        if want_coral == current_is_coral:
            return False  # no backend-family change requested

        logger.info(
            "BirdNET backend change requested: %s -> %s (hot-swap, no restart needed)",
            "coral" if current_is_coral else "cpu", new_backend_name,
        )

        new_instance = None
        if want_coral:
            from .birdnet_coral import BirdNetCoral, check_coral_available
            if check_coral_available():
                candidate = BirdNetCoral(new_config)
                if candidate.load():
                    new_instance = candidate
                else:
                    logger.error(
                        "Coral backend requested but failed to load (see errors above) — "
                        "keeping the current backend active rather than leaving detection "
                        "with no working model at all."
                    )
            else:
                logger.warning(
                    "Coral backend requested but no Coral TPU is currently reachable — "
                    "keeping the current backend active."
                )
        else:
            from .birdnet_cpu import BirdNetCPU
            candidate = BirdNetCPU(new_config)
            if candidate.load():
                new_instance = candidate
            else:
                logger.error("CPU backend failed to (re)load — keeping the current backend active.")

        if new_instance is not None:
            self._birdnet = new_instance
            logger.info("BirdNET backend is now: %s", type(self._birdnet).__name__)
            return True
        return False

    def add_callback(self, fn: Callable[[DetectionEvent], None]) -> None:
        """Register a callback to be called on each detection event."""
        with self._callback_lock:
            self._callbacks.append(fn)

    def start(self) -> None:
        """Start the detection thread."""
        self._running.set()
        self._thread = threading.Thread(
            target=self._detection_loop,
            name="DetectionPipeline",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "DetectionPipeline started [Stage1=%s, BirdNET=%s, backend=%s]",
            self._energy_enabled,
            self._birdnet_enabled,
            self.config["detection"]["birdnet"]["backend"],
        )

    def stop(self) -> None:
        """Stop the detection thread."""
        self._running.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10.0)
        logger.info("DetectionPipeline stopped. Stats: %s", self._format_stats())

    @property
    def is_running(self) -> bool:
        return self._running.is_set()

    @property
    def watchdog(self) -> WatchdogTimer:
        return self._watchdog

    # ── Detection Loop ────────────────────────────────────────────────────────

    def _detection_loop(self) -> None:
        """Main detection thread. Processes audio windows continuously."""
        logger.debug("Detection loop started")
        consecutive_errors = 0

        while self._running.is_set():
            try:
                # Get next 3-second window from audio capture
                window = self.audio.get_detection_window(timeout=1.0)
                if window is None:
                    continue  # Timeout — loop and check _running flag

                self._watchdog.pet()
                self.stats["windows_analyzed"] += 1

                # ── Stage 1: Energy / Frequency Filter ────────────────────
                if self._energy_enabled:
                    passed, energy_db = self._energy_filter(window)
                    if self._log_energy:
                        logger.debug("Energy filter: %.1f dBFS → %s", energy_db, "PASS" if passed else "fail")
                    self._note_window_level(energy_db)
                    if not passed:
                        consecutive_errors = 0
                        continue
                    self.stats["stage1_passed"] += 1
                else:
                    energy_db = rms_db(window)

                # ── Check cooldown ─────────────────────────────────────────
                now = time.monotonic()
                since_last = now - self._last_trigger_time
                if since_last < self._cooldown:
                    self.stats["cooldown_skips"] += 1
                    logger.debug(
                        "Cooldown active (%.1fs remaining)", self._cooldown - since_last
                    )
                    continue

                # ── Stage 2: BirdNET Analysis ──────────────────────────────
                if self._birdnet_enabled and self._birdnet is not None:
                    detections = self._birdnet.analyze(
                        window, timestamp=utc_now()
                    )
                else:
                    # BirdNET disabled: treat any energy above threshold as detection
                    detections = []

                # ── Trigger decision ───────────────────────────────────────
                should_trigger = False

                if self._birdnet_enabled:
                    if len(detections) >= self._min_detections:
                        should_trigger = True
                        self.stats["stage2_passed"] += 1
                else:
                    # Energy-only mode (no BirdNET)
                    should_trigger = True
                    self.stats["stage2_passed"] += 1

                if should_trigger:
                    self._last_trigger_time = time.monotonic()
                    self.stats["triggers"] += 1

                    event = DetectionEvent(
                        timestamp=utc_now(),
                        detections=detections,
                        audio_window=window.copy(),
                        energy_db=energy_db,
                    )

                    if self._log_detections:
                        logger.info("🐦 DETECTION: %s", event)

                    self._fire_callbacks(event)

                consecutive_errors = 0

            except Exception as e:
                consecutive_errors += 1
                logger.error(
                    "Detection loop error (consecutive: %d): %s",
                    consecutive_errors, e, exc_info=True,
                )
                if consecutive_errors > 10:
                    logger.critical(
                        "Too many consecutive detection errors; sleeping 5s"
                    )
                    time.sleep(5.0)
                    consecutive_errors = 0

        logger.debug("Detection loop exiting")

    # ── Stage 1 ───────────────────────────────────────────────────────────────

    def _note_window_level(self, energy_db: float) -> None:
        """Collect gate levels; log a summary every window_stats_interval_seconds."""
        if self._stats_interval <= 0:
            return
        if np.isfinite(energy_db):
            self._win_levels.append(float(energy_db))
        now = time.monotonic()
        if now - self._win_stats_t0 < self._stats_interval:
            return
        lv = np.asarray(self._win_levels) if self._win_levels else np.asarray([-np.inf])
        base = self._win_stats_base
        n = self.stats["windows_analyzed"] - base.get("windows_analyzed", 0)
        s1 = self.stats["stage1_passed"] - base.get("stage1_passed", 0)
        s2 = self.stats["stage2_passed"] - base.get("stage2_passed", 0)
        dropped = getattr(self.audio, "stats", {}).get("detection_windows_dropped", 0)
        p10, p50, p90 = np.percentile(lv, [10, 50, 90])
        logger.info(
            "Window stats (%.0f min): n=%d stage1=%d (%.0f%%) birdnet=%d | level p10 %.1f p50 %.1f "
            "p90 %.1f max %.1f dBFS | gate %.0f dB %.0f-%.0f Hz | dropped total=%d overlap cuts=%d",
            (now - self._win_stats_t0) / 60, n, s1, 100.0 * s1 / max(n, 1), s2,
            p10, p50, p90, float(lv.max()), self._threshold_db, self._bp_low, self._bp_high, dropped,
            getattr(self.audio, "stats", {}).get("overlap_throttle_events", 0))
        self._win_levels = []
        self._win_stats_t0 = now
        self._win_stats_base = dict(self.stats)

    def update_energy_filter(self, config: Dict) -> None:
        """Hot-apply a pushed energy_filter (threshold and band)."""
        ef = config.get("detection", {}).get("energy_filter", {}) or {}
        if "threshold_db" in ef:
            self._threshold_db = float(ef["threshold_db"])
        band = ef.get("frequency_band_hz")
        if band and len(band) == 2 and (band[0], band[1]) != (self._bp_low, self._bp_high):
            try:
                self._sos = build_bandpass_sos(
                    float(band[0]), float(band[1]), self.sample_rate, self._bp_order)
                self._bp_low, self._bp_high = float(band[0]), float(band[1])
            except Exception as e:
                logger.error("Energy filter band %s rejected: %s", band, e)
        logger.info("  Energy filter: %.0f dB, %.0f-%.0f Hz",
                    self._threshold_db, self._bp_low, self._bp_high)

    def _energy_filter(self, audio: np.ndarray) -> tuple[bool, float]:
        """
        Apply bandpass filter and compute RMS energy.
        Returns (passed: bool, energy_db: float).
        """
        try:
            if self._sos is not None:
                filtered = sosfilt(self._sos, audio.astype(np.float64)).astype(np.float32)
            else:
                filtered = audio

            # Loudest sub-window anywhere in the 3 s window. Checking only the
            # last 0.5 s missed a hoot that landed earlier in the window and
            # was followed by silence (owl series have long gaps).
            n = min(self._energy_window_samples, len(filtered))
            hop = max(1, n // 2)
            db = max(
                rms_db(filtered[i:i + n])
                for i in range(0, max(1, len(filtered) - n + 1), hop)
            )
            return db >= self._threshold_db, db

        except Exception as e:
            logger.debug("Energy filter error: %s", e)
            # On error, pass through to Stage 2 conservatively
            return True, 0.0

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _fire_callbacks(self, event: DetectionEvent) -> None:
        """Call all registered callbacks with the detection event."""
        with self._callback_lock:
            callbacks = list(self._callbacks)
        for fn in callbacks:
            try:
                fn(event)
            except Exception as e:
                logger.error("Detection callback error: %s", e, exc_info=True)

    # ── Stats ─────────────────────────────────────────────────────────────────

    def _format_stats(self) -> str:
        s = self.stats
        return (
            f"windows={s['windows_analyzed']}, "
            f"stage1_pass={s['stage1_passed']}, "
            f"stage2_pass={s['stage2_passed']}, "
            f"triggers={s['triggers']}, "
            f"cooldown_skips={s['cooldown_skips']}, "
            f"dropped={getattr(self.audio, 'stats', {}).get('detection_windows_dropped', 0)}"
        )

    def get_birdnet_stats(self) -> str:
        if self._birdnet:
            return self._birdnet.get_stats_str()
        return "BirdNET not enabled."
