"""1.4.2: mains hum filter removes 60/50 Hz and harmonics, keeps bird and
owl-range sound, and stays off when there's no hum."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from chirp.hum_filter import HumFilter, detect_mains  # noqa: E402

SR = 48000


def _rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12)


def _tone(f, secs, amp):
    t = np.arange(int(SR * secs)) / SR
    return amp * np.sin(2 * np.pi * f * t)


def _hum(f0, secs):
    return sum(_tone(f0 * k, secs, 0.01 / k) for k in (1, 3, 5, 7, 9))


def _run(hf, y, chunk=8192):
    return np.concatenate([hf.process(y[i:i + chunk].astype(np.float32)) for i in range(0, len(y), chunk)])


def test_detects_60_and_50():
    rng = np.random.default_rng(1)
    noise = 0.001 * rng.standard_normal(SR * 10)
    assert detect_mains(noise + _hum(60, 10), SR) == 60.0
    assert detect_mains(noise + _hum(50, 10), SR) == 50.0
    assert detect_mains(noise, SR) is None


def test_auto_removes_hum_keeps_calls():
    rng = np.random.default_rng(2)
    secs = 20
    noise = 0.0005 * rng.standard_normal(SR * secs)
    owl = _tone(330, secs, 0.01)        # between 300 and 360 Hz harmonics
    bird = _tone(3200, secs, 0.01)
    y = noise + _hum(60, secs) + owl + bird
    out = _run(HumFilter(SR, "auto"), y)
    tail = slice(SR * 12, None)          # after the 10 s detection window
    hum_in = _rms_db(_hum(60, secs)[tail])
    # residual hum = output minus what should be kept
    resid = out[tail] - (noise + owl + bird)[tail]
    assert _rms_db(resid) < hum_in - 25
    # kept sound within 1 dB
    from scipy.signal import butter, sosfiltfilt
    for f, sig in ((330, owl), (3200, bird)):
        sos = butter(4, [f - 10, f + 10], btype="band", fs=SR, output="sos")
        assert abs(_rms_db(sosfiltfilt(sos, out[tail])) - _rms_db(sig[tail])) < 1.0


def test_off_without_hum_and_when_disabled():
    rng = np.random.default_rng(3)
    y = (0.001 * rng.standard_normal(SR * 12)).astype(np.float32)
    hf = HumFilter(SR, "auto")
    out = _run(hf, y)
    assert not hf.active and np.array_equal(out, y)
    hf = HumFilter(SR, "off")
    assert hf.process(y[:100]) is y[:100] or np.array_equal(hf.process(y[:100]), y[:100])


def test_forced_60_filters_immediately():
    y = _hum(60, 2).astype(np.float32)
    hf = HumFilter(SR, "60")
    out = _run(hf, y)
    assert hf.active
    assert _rms_db(out[SR:]) < _rms_db(y[SR:]) - 25
