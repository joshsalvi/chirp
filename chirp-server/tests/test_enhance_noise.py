"""Enhanced audio cleans before it raises the level: the hiss between calls
ends up quiet, and the calls stand further above it than in the original."""
import os
import sys

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
pytest.importorskip("noisereduce")


def _db(x):
    return 20 * np.log10(max(float(x), 1e-12))


def _levels(y, sr):
    from app.services.audio_processor import _frame_rms, _hiss_band
    r, _ = _frame_rms(_hiss_band(y, sr), sr, 50)
    return _db(np.percentile(r, 99)), _db(np.percentile(r, 20))


@pytest.fixture(scope="module")
def station_clip(tmp_path_factory):
    """35 s like a station recording: quiet hiss, low rumble, 3.5 kHz chirps
    about 12 dB above the hiss, peak near -35 dBFS."""
    sr = 48000
    rng = np.random.default_rng(1)
    t = np.arange(35 * sr) / sr
    hiss = 0.0015 * rng.standard_normal(len(t))
    rumble = 0.012 * np.sin(2 * np.pi * 60 * t) * (1 + 0.3 * np.sin(2 * np.pi * 0.2 * t))
    chirps = np.zeros_like(t)
    for start in np.arange(1.0, 34.0, 2.5):
        m = (t >= start) & (t < start + 0.35)
        chirps[m] = 0.006 * np.sin(2 * np.pi * (3200 + 800 * (t[m] - start)) * t[m]) * np.hanning(m.sum())
    p = tmp_path_factory.mktemp("enh") / "station.wav"
    sf.write(p, (hiss + rumble + chirps).astype(np.float32), sr, subtype="PCM_16")
    return str(p), sr


@pytest.mark.parametrize("kw", [dict(apply_bandpass=False), dict(low_hz=1000, apply_bandpass=True)],
                         ids=["enhanced", "rumble-removed-enhanced"])
def test_enhanced_hiss_stays_quiet(station_clip, tmp_path, kw):
    from app.services.audio_processor import AudioProcessor
    path, sr = station_clip
    x, _ = sf.read(path)
    call0, floor0 = _levels(x, sr)
    out = AudioProcessor().enhance_audio(path, str(tmp_path), "t", **kw)
    y, _ = sf.read(out)
    call, floor = _levels(y, sr)
    assert floor < -50                                   # hiss stays quiet (was about -25)
    assert (call - floor) - (call0 - floor0) > 10        # calls stand out at least 10 dB more
    assert call > call0 + 6                              # and still come up in level
    assert np.max(np.abs(y)) <= 0.95


def test_rumble_filter_alone_adds_no_gain(station_clip, tmp_path):
    from app.services.audio_processor import AudioProcessor
    path, sr = station_clip
    x, _ = sf.read(path)
    y, _ = sf.read(AudioProcessor().enhance_audio(path, str(tmp_path), "hp", low_hz=1000,
                                                  apply_noise_reduction=False))
    assert _levels(y, sr)[1] <= _levels(x, sr)[1] + 1    # hiss no louder than the original
