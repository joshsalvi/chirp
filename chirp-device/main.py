#!/usr/bin/env python3
"""Chirp Device — Raspberry Pi 5 Bird Call Detection"""
import argparse, logging, signal, sys, time, os

# ── Auto-activate venv if not already in one ──────────────────────────────────
# This lets you run `python main.py` directly without `source venv/bin/activate`.
# The script re-executes itself under the venv Python when needed.
def _ensure_venv():
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _venv_python = os.path.join(_script_dir, 'venv', 'bin', 'python3')
    # Already inside the venv, or venv doesn't exist yet → proceed normally
    if not os.path.exists(_venv_python):
        return
    # sys.prefix points to the active venv; if it matches ours, we're good
    _venv_dir = os.path.join(_script_dir, 'venv')
    if os.path.realpath(sys.prefix) == os.path.realpath(_venv_dir):
        return
    # Re-exec under venv python, passing all original arguments
    os.execv(_venv_python, [_venv_python] + sys.argv)

_ensure_venv()

def _warn_if_service_running():
    """
    Best-effort check: if the chirp systemd service is already running, it
    holds the microphone open exclusively, and --test-audio/--test-detection
    will fail with a cryptic ALSA error ("unable to open slave", "Device or
    resource busy") trying to open the SAME hardware device a second time.
    Warn clearly up front instead of letting the user hit that raw error.
    Silently does nothing if systemctl isn't available (e.g. local dev, or
    non-systemd environments) — this is a courtesy check, not a hard gate.
    """
    import subprocess
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "chirp"],
            capture_output=True, text=True, timeout=3,
        )
        if result.stdout.strip() == "active":
            print(
                "\n⚠️  The chirp systemd service is currently RUNNING and already has "
                "the microphone open.\n"
                "   This test will likely fail with an ALSA 'unable to open slave' / "
                "'Device or resource busy' error.\n"
                "   Stop the service first, then re-run this test:\n"
                "     sudo systemctl stop chirp\n"
                "   ...and restart it when you're done testing:\n"
                "     sudo systemctl start chirp\n",
                file=sys.stderr,
            )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        pass  # systemctl not available — not a systemd environment, nothing to check


def parse_args():
    p = argparse.ArgumentParser(description="Chirp: Automated Bird Call Detection")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--list-devices", action="store_true",
                   help="List all audio input devices (includes ReSpeaker if connected)")
    p.add_argument("--test-audio", action="store_true",
                   help="Show live audio levels from all active input devices")
    p.add_argument("--test-detection", action="store_true",
                   help="Run BirdNET detection without recording")
    p.add_argument("--test-upload", action="store_true",
                   help="Send one real, clearly-fake detection to every configured upload target and report success/failure per target — no microphone or config changes needed")
    p.add_argument("--respeaker-info", action="store_true",
                   help="Probe and print ReSpeaker hardware info, then exit")
    p.add_argument("--respeaker-leds", metavar="R,G,B",
                   help="Set ReSpeaker USB LED ring to color (e.g. 0,200,80), then exit")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()

def main():
    args = parse_args()

    # ── --list-devices ────────────────────────────────────────────────────────
    if args.list_devices:
        import sounddevice as sd
        _RESPEAKER_HINTS = ["respeaker","seeed","xvf","2886","voicecard","ac108","wm8960"]
        _USB_HINTS = ["USB","Microphone","Blue","Yeti","Rode","Snowball"]
        print("\nAvailable Input Devices:")
        print(f"  {'ID':>3}  {'Name':<44} {'Ch':>3}  {'Type'}")
        print("  " + "─" * 68)
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] < 1:
                continue
            n = d["name"]
            ch = d["max_input_channels"]
            if any(h.lower() in n.lower() for h in _RESPEAKER_HINTS):
                tag = "★ ReSpeaker"
            elif any(h in n for h in _USB_HINTS):
                tag = "→ USB mic"
            else:
                tag = "  other"
            print(f"  [{i:2d}] {n:<44} {ch:>3}  {tag}")
        print()
        # Also run the auto-probe
        try:
            from chirp.respeaker import respeaker_info
            print(respeaker_info())
        except Exception as e:
            print(f"ReSpeaker probe: {e}")
        return

    # ── --respeaker-info ──────────────────────────────────────────────────────
    if args.respeaker_info:
        try:
            from chirp.respeaker import respeaker_info
            print(respeaker_info())
        except Exception as e:
            print(f"Error: {e}")
        return

    # ── --respeaker-leds ──────────────────────────────────────────────────────
    if args.respeaker_leds:
        try:
            parts = [int(x.strip()) for x in args.respeaker_leds.split(",")]
            r, g, b = parts[0], parts[1], parts[2]
            from chirp.respeaker import set_led_color_usb
            ok = set_led_color_usb((r, g, b))
            print(f"LED set to R={r} G={g} B={b}: {'OK' if ok else 'FAILED (pyusb missing or device not found)'}")
        except Exception as e:
            print(f"LED error: {e}")
        return

    from chirp.config import load_config
    from chirp.utils import setup_logging
    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        print(f"Config error: {e}", file=sys.stderr); sys.exit(1)
    setup_logging(config, verbose=args.verbose)
    logger = logging.getLogger(__name__)

    # ── --test-audio ──────────────────────────────────────────────────────────
    if args.test_audio:
        from chirp.audio import AudioCapture
        _warn_if_service_running()
        print("\n Chirp — Live Audio Levels (Ctrl+C to stop)\n")
        audio = AudioCapture(config)
        if not audio.start():
            sys.exit(1)
        rs = audio.respeaker_info
        if rs:
            print(f"  ReSpeaker: {rs}\n")
        time.sleep(0.5)
        try:
            while True:
                levels = audio.get_current_levels_db()
                for name, db in levels:
                    bar = "█" * max(0, min(40, int((db + 80) / 80 * 40))) if db > -80 else ""
                    print(f"\r  {name[:24]:<24} [{bar:<40}] {db:+.1f} dBFS     ",
                          end="", flush=True)
                time.sleep(0.1)
        except KeyboardInterrupt:
            print()
        finally:
            audio.stop()
        return

    # ── --test-detection ──────────────────────────────────────────────────────
    if args.test_detection:
        from chirp.audio import AudioCapture
        from chirp.detector import DetectionPipeline
        _warn_if_service_running()
        audio = AudioCapture(config)
        detector = DetectionPipeline(config, audio)
        rs = None

        def on_event(e):
            print(f"\n🐦 {e.timestamp:%H:%M:%S} | {e.species_summary} | {e.max_confidence:.0%}")
            # Flash LEDs on test detection too
            try:
                rs_cfg = config.get("respeaker", {})
                if rs_cfg.get("led_on_detection", True):
                    if (audio._respeaker_device is not None and
                            getattr(audio._respeaker_device, 'has_leds', False) and
                            audio._respeaker_device.mode == "usb"):
                        from chirp.respeaker import led_detection_flash
                        color = tuple(rs_cfg.get("led_color_detection", [0, 200, 80]))
                        led_detection_flash(color=color, duration_secs=2.0)
            except Exception:
                pass

        detector.add_callback(on_event)
        if not audio.start():
            sys.exit(1)
        rs = audio.respeaker_info
        if rs:
            print(f"  ReSpeaker active: {rs}")
        if not detector.load_model():
            sys.exit(1)
        detector.start()
        print("  Listening for birds... (Ctrl+C to stop)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            detector.stop()
            audio.stop()
        return

    # ── --test-upload ─────────────────────────────────────────────────────────
    if args.test_upload:
        import io
        import wave
        from chirp.uploader import UploadTarget

        print("\nChirp — Upload Pipeline Test\n")

        upload_cfg = config.get("upload", {})
        if not upload_cfg.get("enabled", False):
            print("⚠️  upload.enabled is false in config.yaml — the real service")
            print("   would never attempt to upload at all. Testing anyway, but")
            print("   fix this first if uploads are supposed to be happening.\n")

        # Same backward-compatibility logic as FileUploader.__init__ — a
        # config.yaml with no explicit `targets:` list still gets exactly
        # one chirp-server target built from the legacy top-level fields,
        # so this test exercises the SAME target(s) the real service would.
        target_configs = upload_cfg.get("targets")
        if not target_configs:
            target_configs = [{
                "name": "chirp-server", "type": "chirp-server", "enabled": True,
                "server_url": upload_cfg.get("server_url", ""),
                "api_key": upload_cfg.get("api_key", ""),
                "auth_header": upload_cfg.get("auth_header", "X-API-Key"),
            }]

        state_dir = os.path.expanduser(upload_cfg.get("state_dir", "~/.chirp_upload_state"))
        targets = [UploadTarget(tc, upload_cfg, state_dir) for tc in target_configs]

        # A real, tiny, valid WAV file — half a second of silence at
        # 16kHz mono, matching what the real pipeline actually sends
        # (a real audio file, not an empty or fake payload) — but a
        # server-side listener wouldn't be able to tell this one apart
        # from a real (very quiet) recording just from the bytes alone,
        # which is exactly why the metadata below is labeled unmistakably
        # as a test.
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00\x00" * 8000)
        test_audio_bytes = buf.getvalue()

        import datetime as _dt
        test_metadata = {
            "duration_seconds": 0.5,
            "trigger_timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "is_bat": False,
            "detections": [{"common_name": "TEST — Chirp Upload Diagnostic", "confidence": 0.99}],
        }
        test_wav_name = "chirp_test_upload.wav"

        any_failed = False
        for target in targets:
            if not target.enabled:
                print(f"[{target.name}] SKIPPED — disabled in config.yaml\n")
                continue
            print(f"[{target.name}] type={target.type} → {target.server_url}")
            if "PLACEHOLDER" in (target.server_url or "") or "PLACEHOLDER" in (target.api_key or target.pairing_key or ""):
                print(f"[{target.name}] ❌ FAILED — server_url or api_key/pairing_key is still a PLACEHOLDER value in config.yaml\n")
                any_failed = True
                continue
            try:
                ok = target.upload_once(test_wav_name, test_audio_bytes, test_metadata, None)
            except Exception as e:
                print(f"[{target.name}] ❌ FAILED — unhandled exception: {type(e).__name__}: {e}\n")
                any_failed = True
                continue
            if ok:
                print(f"[{target.name}] ✅ SUCCESS — the server accepted the test upload. "
                      f"Check its recent recordings for \"TEST — Chirp Upload Diagnostic\" to confirm end-to-end, then delete it.\n")
            else:
                print(f"[{target.name}] ❌ FAILED — see the WARNING-level log line just above "
                      f"for the real HTTP status / response body / exception from this attempt.\n")
                any_failed = True

        if any_failed:
            print("One or more targets failed. Common causes, cheapest to check first:")
            print("  1. Is the chirp service actually running/restarted since config.yaml was last edited?")
            print("  2. Does server_url include the full path, e.g. https://your-server/api/v1/recordings/upload — not just the base https://your-server?")
            print("  3. Is the api_key still valid on the server (not deleted/rotated)?")
            print("  4. Can this device reach the server at all right now? Try: curl -v <server_url>")
            print("  5. If the server uses HTTPS with a certificate this device doesn't trust yet, check the WARNING log line above for a certificate error.")
            sys.exit(1)
        else:
            print("All enabled targets succeeded.")
        return

    # ── Normal run ────────────────────────────────────────────────────────────
    from chirp.watcher import BirdWatcher
    from chirp.server_sync import ServerSync
    from chirp.tailscale_manager import TailscaleManager

    tailscale = TailscaleManager(config)
    tailscale.start()

    sync = ServerSync(config)
    sync._tailscale_manager = tailscale

    # watcher is assigned much later (after BirdWatcher() succeeds), but
    # sync.start() below spawns a background thread that can call
    # on_config_update() immediately — often before this function reaches
    # the `watcher = BirdWatcher(config)` line. Since `watcher` is closed
    # over by on_config_update, Python treats it as a cell variable of this
    # function; referencing it before ANY assignment has happened raises
    # "cannot access free variable 'watcher' where it is not associated
    # with a value in enclosing scope" — NOT an AttributeError, so the old
    # `except AttributeError: pass` never actually caught it, and every
    # device logged a startup error on first pairing. Initializing watcher
    # to None here gives the name a bound value immediately, so the early
    # callback hits the `is None` check instead of raising.
    watcher = None

    def on_config_update(merged_config):
        if watcher is None:
            # BirdWatcher not started yet. Reported directly: returning
            # cleanly here (no exception) meant server_sync.py's
            # _apply_config() saw this as a SUCCESSFUL apply and stamped
            # _applied_version to the new version — even though the
            # config was silently dropped, never reaching anything. That
            # window is normally brief (a few seconds at startup), so in
            # practice the config usually did apply moments later when
            # BirdWatcher read the merged config fresh on its own
            # construction — but if pairing/config-poll landed unusually
            # early, or BirdWatcher's own startup took longer than usual
            # (mic enumeration, Coral init), the version could get marked
            # "applied" for a config that was never actually picked up by
            # anything live, with no way to tell from the server side.
            # Raising here instead makes server_sync.py correctly leave
            # this version "Pending" and retry on its own next poll cycle
            # (CONFIG_POLL_INTERVAL) rather than reporting false success.
            raise RuntimeError("BirdWatcher not started yet — will retry once it is")
        try:
            watcher.apply_config(merged_config)
        except Exception as e:
            logger.warning("Config update callback error: %s", e)

    def bat_status_getter():
        # Same "watcher not assigned yet" guard as on_config_update above —
        # returns None (heartbeat just omits bat_status) rather than
        # raising during the startup window before BirdWatcher exists.
        if watcher is None or not hasattr(watcher, "_bat_detector"):
            return None
        try:
            return watcher._bat_detector.get_status()
        except Exception:
            return None

    def active_backend_getter():
        # Effective BirdNET backend (after any Coral -> CPU fallback), so the
        # Devices page can tell "Coral selected" from "Coral running".
        if watcher is None or not hasattr(watcher, "_detector"):
            return None
        try:
            return watcher._detector.active_backend
        except Exception:
            return None

    sync._on_config_update = on_config_update
    sync._bat_status_getter = bat_status_getter
    sync._active_backend_getter = active_backend_getter
    sync.start()

    if sync.is_paired():
        config = sync.get_merged_config()

    from chirp.discovery import DeviceDiscovery
    discovery = DeviceDiscovery(
        config,
        coral_form=getattr(sync, '_coral_form', ''),
        is_paired=sync.is_paired(),
    )
    discovery.start()

    _orig_apply = sync._apply_config
    def _patched_apply(version):
        _orig_apply(version)
        discovery.update_paired_state(sync.is_paired())
        backend = sync._backend
        discovery.update_backend(backend)
    sync._apply_config = _patched_apply

    from chirp.display import OledDisplay, build_stats_for_display
    display = OledDisplay(config)
    display_active = display.start()

    from chirp.zigbee import ZigbeeIntegration
    zigbee = ZigbeeIntegration(config)
    zigbee.start()

    try:
        watcher = BirdWatcher(config)
        watcher._sync    = sync
        watcher._display = display if display_active else None
        watcher._zigbee  = zigbee
    except Exception as e:
        logger.critical("Init failed: %s", e); sys.exit(1)

    # ── Local status server ──────────────────────────────────────────────────
    # Exposes live mic levels already captured by watcher._audio / watcher._bat_detector
    # over HTTP, so the server's diagnostics page doesn't need a second ALSA open
    # (which fails on most USB audio class devices — see status_server.py docstring).
    # watcher._audio / watcher._bat_detector are read fresh on every request via
    # these lambdas (not captured by value) since _bat_detector in particular can
    # be reassigned on a config update.
    from chirp.status_server import StatusServer
    status_server = StatusServer(
        config,
        level_providers=[
            lambda: watcher._audio.get_live_level_snapshot(),
            lambda: watcher._bat_detector.get_live_level_snapshot(),
        ],
        # Bird capture's raw audio streams straight through — already in
        # human hearing range. The bat/AudioMoth stream is ALSO exposed
        # here now (get_recent_audio_samples returns one dict, not a
        # list, since BatDetector represents exactly one stream) — its
        # raw samples are still ultrasonic and inaudible as-is, but
        # status_server.py applies the same time-expansion downshift
        # AudioProcessor.downshift_bat_clip() uses server-side before
        # wrapping it in a WAV, so it's audible on the other
        # end. No species ID or detection-quality claim either way —
        # this is purely "can I hear that the AudioMoth is picking
        # something up," the same scope as the bird Listen button.
        audio_providers=[
            lambda seconds: watcher._audio.get_recent_audio_samples(seconds),
            lambda seconds: watcher._bat_detector.get_recent_audio_samples(seconds),
        ],
        version=sync.VERSION,
    )
    status_server.start()

    def shutdown(sig, frame):
        if display_active:
            display.stop()
        # Turn off ReSpeaker LEDs on shutdown
        try:
            if (watcher._audio._respeaker_device is not None and
                    getattr(watcher._audio._respeaker_device, 'has_leds', False) and
                    watcher._audio._respeaker_device.mode == "usb"):
                from chirp.respeaker import set_led_color_usb
                set_led_color_usb((0, 0, 0), brightness=0)
        except Exception:
            pass
        status_server.stop()
        zigbee.stop()
        discovery.stop()
        sync.stop()
        tailscale.stop()
        watcher.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        watcher.start()
    except RuntimeError as e:
        logger.critical("Startup failed: %s", e); sys.exit(1)

    # Log ReSpeaker info after start
    try:
        rs = watcher._audio.respeaker_info
        if rs:
            logger.info("ReSpeaker active: %s", rs)
    except Exception:
        pass

    try:
        _display_tick = 0
        while watcher.is_running():
            time.sleep(5)
            watcher.health_check()
            _display_tick += 1
            if _display_tick % 2 == 0:
                if display_active or zigbee.enabled:
                    _stats = build_stats_for_display(watcher)
                    if display_active:
                        display.update_stats(_stats)
                    if zigbee.enabled:
                        zigbee.update_stats(_stats)
    except KeyboardInterrupt:
        pass
    finally:
        if display_active:
            display.stop()
        try:
            if (watcher._audio._respeaker_device is not None and
                    getattr(watcher._audio._respeaker_device, 'has_leds', False) and
                    watcher._audio._respeaker_device.mode == "usb"):
                from chirp.respeaker import set_led_color_usb
                set_led_color_usb((0, 0, 0), brightness=0)
        except Exception:
            pass
        zigbee.stop()
        discovery.stop()
        sync.stop()
        tailscale.stop()
        watcher.stop()

if __name__ == "__main__":
    main()
