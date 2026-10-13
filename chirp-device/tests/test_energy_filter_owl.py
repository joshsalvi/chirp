"""Stage 1 energy gate vs. distant low-pitched night calls.

A synthetic Barred Owl-style hoot series (~400 Hz, short notes with gaps)
at a distant level must pass the default gate, including when the loudest
note sits early in the 3 s window and the window ends in silence.
"""
import numpy as np

from chirp.detector import DetectionPipeline, build_bandpass_sos

SR = 48000


def _hoot_window(level_dbfs: float, note_at_s: float) -> np.ndarray:
    rng = np.random.default_rng(1)
    n = 3 * SR
    x = rng.standard_normal(n).astype(np.float32) * 10 ** (-95 / 20)  # quiet night floor
    t = np.arange(int(0.4 * SR)) / SR
    note = np.sin(2 * np.pi * 400 * t) * np.hanning(len(t))
    note *= 10 ** (level_dbfs / 20) * np.sqrt(2) / np.sqrt(np.mean(np.hanning(len(t)) ** 2))
    a = int(note_at_s * SR)
    x[a:a + len(note)] += note.astype(np.float32)
    return x


def _pipeline(threshold_db: float, band=(150, 12000)) -> DetectionPipeline:
    p = DetectionPipeline.__new__(DetectionPipeline)
    p.sample_rate = SR
    p._threshold_db = threshold_db
    p._bp_low, p._bp_high, p._bp_order = band[0], band[1], 4
    p._energy_window_samples = int(0.5 * SR)
    p._sos = build_bandpass_sos(band[0], band[1], SR, 4)
    return p


def test_distant_hoot_early_in_window_passes_default_gate():
    win = _hoot_window(-70.0, note_at_s=0.3)   # note well before the last 0.5 s
    passed, db = _pipeline(-85.0)._energy_filter(win)
    assert passed, db
    assert db > -75


def test_old_pushed_gate_blocked_the_same_hoot():
    win = _hoot_window(-70.0, note_at_s=0.3)
    passed, _ = _pipeline(-55.0)._energy_filter(win)
    assert not passed


def test_silence_does_not_pass():
    win = _hoot_window(-200.0, note_at_s=0.3)
    passed, db = _pipeline(-85.0)._energy_filter(win)
    assert not passed, db


def test_update_energy_filter_hot_applies():
    p = _pipeline(-55.0, band=(250, 12000))
    p.update_energy_filter({"detection": {"energy_filter": {
        "threshold_db": -85.0, "frequency_band_hz": [150, 12000]}}})
    assert p._threshold_db == -85.0
    assert (p._bp_low, p._bp_high) == (150.0, 12000.0)
