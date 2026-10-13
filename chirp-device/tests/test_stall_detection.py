"""
Standalone test for BatDetector.is_stalled() and attempt_usb_power_cycle().
Run: python3 tests/test_stall_detection.py
No real audio hardware needed — constructs a BatDetector without calling
start(), then drives its internal counters/clock directly.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chirp.bat_detector import BatDetector, attempt_usb_power_cycle  # noqa: E402


def make_detector(stuck_pulse_hours=4.0, active_hours=("00:00", "23:59")):
    config = {
        "detection": {
            "bat_echolocation": {
                "enabled": True,
                "stuck_pulse_hours": stuck_pulse_hours,
                "active_hours_start": active_hours[0],
                "active_hours_end": active_hours[1],
            }
        },
        "server_sync": {},
    }
    d = BatDetector(config)
    # Simulate a successfully-started, healthy stream without touching real
    # hardware: is_stalled() only reads self._running / is_active()'s own
    # inputs (self._stream, self._last_callback_at), so fake those directly.
    d._running = True
    d._last_callback_at = time.time()

    class _FakeStream:
        active = True

    d._stream = _FakeStream()
    return d


def test_disabled_check_never_stalls():
    d = make_detector(stuck_pulse_hours=0)
    assert d.is_stalled() is False
    print("PASS: stuck_pulse_hours<=0 disables the check")


def test_no_stall_when_pulses_progressing():
    d = make_detector(stuck_pulse_hours=0.0001)  # ~0.36s threshold
    d._total_pulses_seen = 5
    assert d.is_stalled() is False  # first call just baselines
    time.sleep(0.5)
    d._total_pulses_seen = 6  # progressed — resets the clock
    assert d.is_stalled() is False
    print("PASS: progressing pulse count never trips the stall check")


def test_stall_trips_after_threshold():
    d = make_detector(stuck_pulse_hours=0.0001)  # ~0.36s threshold
    d._total_pulses_seen = 5
    assert d.is_stalled() is False  # call #1: baselines pulse count
    assert d.is_stalled() is False  # call #2: no change — starts the stall clock
    time.sleep(0.5)
    assert d.is_stalled() is True  # call #3: clock exceeded, still no progress
    print("PASS: stall trips once threshold elapses with zero progress")


def test_no_stall_outside_active_hours():
    # Window that (barring a midnight test run) excludes "now" entirely —
    # use a 1-minute window far from any plausible test time to force False.
    d = make_detector(stuck_pulse_hours=0.0001, active_hours=("00:00", "00:01"))
    d._total_pulses_seen = 5
    d.is_stalled()
    time.sleep(0.5)
    # Only assert the intended behavior if we're actually outside the
    # window right now (avoids a flaky failure the ~1 min/day we're inside it).
    if not d._is_active_hour():
        assert d.is_stalled() is False
        print("PASS: outside active_hours never trips the stall check")
    else:
        print("SKIP: test running inside the 00:00-00:01 window itself")


def test_no_stall_when_stream_dead():
    d = make_detector(stuck_pulse_hours=0.0001)
    d._stream.active = False  # dead stream is is_active()'s job, not this check's
    d._total_pulses_seen = 5
    d.is_stalled()
    time.sleep(0.5)
    assert d.is_stalled() is False
    print("PASS: a dead stream never trips the stall check (is_active()'s job)")


def test_power_cycle_disabled_by_default():
    assert attempt_usb_power_cycle({}) is False
    assert attempt_usb_power_cycle({"detection": {"bat_echolocation": {}}}) is False
    print("PASS: attempt_usb_power_cycle no-ops with no config")


def test_power_cycle_requires_location_and_port():
    cfg = {"detection": {"bat_echolocation": {"usb_power_cycle": {"enabled": True}}}}
    assert attempt_usb_power_cycle(cfg) is False
    print("PASS: attempt_usb_power_cycle refuses to run without hub_location/port")


def test_power_cycle_missing_uhubctl_handled():
    cfg = {
        "detection": {
            "bat_echolocation": {
                "usb_power_cycle": {
                    "enabled": True,
                    "hub_location": "1-1",
                    "port": "2",
                }
            }
        }
    }
    # uhubctl almost certainly isn't installed in this test environment —
    # this must return False cleanly, never raise.
    result = attempt_usb_power_cycle(cfg)
    assert result is False
    print("PASS: attempt_usb_power_cycle handles a missing uhubctl binary without raising")


if __name__ == "__main__":
    test_disabled_check_never_stalls()
    test_no_stall_when_pulses_progressing()
    test_stall_trips_after_threshold()
    test_no_stall_outside_active_hours()
    test_no_stall_when_stream_dead()
    test_power_cycle_disabled_by_default()
    test_power_cycle_requires_location_and_port()
    test_power_cycle_missing_uhubctl_handled()
    print("\nAll tests passed.")
