"""The song line: loudness bars and merged stretches (no call marks)."""
import numpy as np
import soundfile as sf

from app.services import songline as sl

RATE = 48000


def _clip(path, seconds=12.0, chirps=(1.0, 2.0, 7.0, 8.5)):
    """Quiet noise with short 4 kHz chirps at the given times."""
    rng = np.random.default_rng(1)
    y = rng.normal(0, 0.003, int(seconds * RATE)).astype(np.float32)
    t = np.arange(int(0.12 * RATE)) / RATE
    tone = (0.4 * np.sin(2 * np.pi * 4000 * t) * np.hanning(len(t))).astype(np.float32)
    for c in chirps:
        i = int(c * RATE)
        y[i:i + len(tone)] += tone
    sf.write(path, y, RATE)
    return path


def test_merge():
    assert sl.merge([(0, 5), (2.5, 7.5), (20, 25), (5, 10)]) == [[0.0, 10.0], [20.0, 25.0]]
    assert sl.merge([]) == []


def test_bars_and_ranges(tmp_path):
    path = _clip(str(tmp_path / "a.wav"))
    out = sl.build(path, 12.0, {"Tufted Titmouse": [(0, 3), (2, 4)], "Blue Jay": [(6, 10)]}, "Tufted Titmouse")
    assert out["duration"] == 12.0 and len(out["bars"]) == sl.BARS
    assert max(out["bars"]) == 1.0 and min(out["bars"]) == 0.0
    # loud bars where the chirps are
    loud = [i for i, v in enumerate(out["bars"]) if v > 0.5]
    assert loud and all(abs(i * 12 / sl.BARS - c) < 0.5 for i in loud for c in [min((1.0, 2.0, 7.0, 8.5), key=lambda c: abs(c - i * 12 / sl.BARS))])
    assert out["segments"]["Tufted Titmouse"] == [[0.0, 4.0]]
    assert out["calls"] == []          # kept, empty, for Chirp Lite 1.1


def test_without_audio():
    out = sl.build(None, 9.0, {"Blue Jay": [(0, 3)]}, "Blue Jay")
    assert out == {"duration": 9.0, "bird": "Blue Jay", "bars": [], "segments": {"Blue Jay": [[0.0, 3.0]]}, "calls": []}


def test_route(client, tmp_path):
    from app.database import SessionLocal
    from app.models import Detection, Recording
    path = _clip(str(tmp_path / "r.wav"))
    db = SessionLocal()
    import datetime as dt
    db.add(Recording(id="sl-1", filename="r.wav", wav_path=path, duration_seconds=12.0, sample_rate=RATE, channels=1,
                     trigger_timestamp=dt.datetime(2026, 11, 8, 12), created_at=dt.datetime(2026, 11, 8, 12)))
    db.add(Detection(recording_id="sl-1", common_name="Tufted Titmouse", label="x", confidence=0.6, start_time=0, end_time=4))
    db.add(Detection(recording_id="sl-1", common_name="Blue Jay", label="y", confidence=0.9, start_time=6, end_time=10))
    db.commit(); db.close()
    out = client.get("/api/v1/lite/recording/sl-1/songline").json()
    assert out["bird"] == "Blue Jay" and out["calls"] == []          # most confident bird by default
    out = client.get("/api/v1/lite/recording/sl-1/songline", params={"bird": "Tufted Titmouse"}).json()
    assert out["bird"] == "Tufted Titmouse" and out["segments"]["Tufted Titmouse"] == [[0.0, 4.0]]
    assert client.get("/api/v1/lite/recording/nope/songline").status_code == 404
