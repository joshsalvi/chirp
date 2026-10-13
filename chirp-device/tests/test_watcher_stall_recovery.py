"""
Integration test for BirdWatcher.health_check()'s stall-detection branch,
including escalation to a hard USB power-cycle after repeated stalls.
Mocks BatDetector/AudioCapture/etc. entirely — no real hardware, no real
sounddevice streams. Run: python3 tests/test_watcher_stall_recovery.py
"""
import os
import sys
import time
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIG = {
    "upload": {"upload_queue_max_size": 100},
    "audio": {"sample_rate": 48000},
    "detection": {
        "pre_roll_seconds": 5.0,
        "birdnet": {"backend": "cpu", "min_confidence": 0.7},
        "bat_echolocation": {
            "enabled": True,
            "stuck_pulse_hours": 4.0,
            "stall_recoveries_before_hard_reset": 2,
            "stall_escalation_window_hours": 12.0,
            "usb_power_cycle": {"enabled": False},
        },
    },
    "recording": {"output_dir": "/tmp/chirp_test_recordings", "duration_seconds": 15},
    "system": {"health_check_interval_seconds": 0},  # always due
}


def stalled_detector():
    d = mock.MagicMock()
    d.enabled = True
    d.is_running.return_value = True
    d.is_active.return_value = True
    d.is_stalled.return_value = True
    d.stuck_pulse_hours = 4.0
    d.start.return_value = True
    return d


class Harness:
    """Keeps all patches alive for the lifetime of one test."""

    def __enter__(self):
        self.patchers = [
            mock.patch("chirp.watcher.AudioCapture"),
            mock.patch("chirp.watcher.DetectionPipeline"),
            mock.patch("chirp.watcher.RecordingEngine"),
            mock.patch("chirp.watcher.FileUploader"),
            mock.patch("chirp.watcher.BatDetector"),
        ]
        (self.MockAudio, self.MockDetector, self.MockRecorder,
         self.MockUploader, self.MockBatDetectorClass) = [p.start() for p in self.patchers]

        self.MockAudio.return_value.check_streams.return_value = True
        self.MockAudio.return_value.get_current_levels_db.return_value = []
        self.MockDetector.return_value.watchdog.is_expired = False
        self.MockDetector.return_value.stats = {"triggers": 0}
        self.MockUploader.return_value.get_stats_str.return_value = ""
        self.MockBatDetectorClass.side_effect = lambda cfg: stalled_detector()

        from chirp.watcher import BirdWatcher
        self.watcher = BirdWatcher(CONFIG)
        self.watcher._recorder.stats = {"recordings_completed": 0}
        return self

    def __exit__(self, *exc):
        for p in self.patchers:
            p.stop()


def test_single_stall_does_soft_reopen_only():
    with Harness() as h:
        old_bat = h.watcher._bat_detector
        with mock.patch("chirp.watcher.attempt_usb_power_cycle") as mock_pc, \
             mock.patch("time.sleep"):
            h.watcher.health_check()

        mock_pc.assert_not_called()  # only ONE stall so far — shouldn't escalate
        old_bat.stop.assert_called_once()
        new_bat = h.watcher._bat_detector
        assert new_bat is not old_bat
        new_bat.start.assert_called_once()
    print("PASS: a single stall does a soft reopen, no hard power-cycle")


def test_repeated_stalls_escalate_to_power_cycle():
    with Harness() as h:
        with mock.patch("chirp.watcher.attempt_usb_power_cycle") as mock_pc, \
             mock.patch("time.sleep"):
            mock_pc.return_value = True
            # First stall: recorded, no escalation yet (threshold is 2 within window)
            h.watcher.health_check()
            assert mock_pc.call_count == 0
            # Second stall within the escalation window: should trigger hard reset
            h.watcher.health_check()
            assert mock_pc.call_count == 1
    print("PASS: a second stall within the escalation window triggers a hard power-cycle")


def test_escalation_window_expiry_resets_count():
    with Harness() as h:
        # Force a very short escalation window so we can test expiry without
        # actually waiting hours in a unit test.
        h.watcher._bat_stall_escalation_window_s = 0.2

        with mock.patch("chirp.watcher.attempt_usb_power_cycle") as mock_pc:
            mock_pc.return_value = True
            h.watcher.health_check()
            time.sleep(0.3)  # let the escalation window expire between real stalls
            h.watcher.health_check()
            assert mock_pc.call_count == 0, (
                "stalls outside the escalation window should NOT combine to "
                "trigger a hard reset"
            )
    print("PASS: stalls outside the escalation window don't combine to escalate")


def test_hard_reset_failure_falls_back_to_soft_reopen():
    with Harness() as h:
        with mock.patch("chirp.watcher.attempt_usb_power_cycle") as mock_pc, \
             mock.patch("time.sleep"):
            mock_pc.return_value = False  # uhubctl unavailable/misconfigured
            h.watcher.health_check()
            h.watcher.health_check()  # this one crosses the escalation threshold
            assert mock_pc.call_count == 1
            # Even though the hard reset failed, the soft reopen must still
            # have been attempted — never leave the detector un-recovered.
            assert h.watcher._bat_detector.start.called
    print("PASS: a failed hard power-cycle still falls back to a soft reopen")


if __name__ == "__main__":
    test_single_stall_does_soft_reopen_only()
    test_repeated_stalls_escalate_to_power_cycle()
    test_escalation_window_expiry_resets_count()
    test_hard_reset_failure_falls_back_to_soft_reopen()
    print("\nAll watcher integration tests passed.")
