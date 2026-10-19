"""Apple Watch: newest recordings and their audio (api/watch.py)."""
import datetime as _dt
import os
import shutil

import pytest

pytest.importorskip("birdnetlib")
T = os.environ["CHIRP_DATA_DIR"]   # set by conftest.py


def test_watch_recent_and_audio(client):
    from app.database import SessionLocal
    from app.models import Detection, Recording
    db = SessionLocal()
    import numpy as np
    import soundfile as sf
    src = os.path.join(T, "watch-src.wav")
    t = np.arange(48000 * 3) / 48000
    sf.write(src, (0.2 * np.sin(2 * np.pi * 3000 * t)).astype("float32"), 48000)
    now = _dt.datetime.utcnow() + _dt.timedelta(days=1)   # newest of all
    for rid, conf, bat in (("watch-new", 0.91, False), ("watch-bat", 0.95, True)):
        path = os.path.join(T, "recordings_dir", f"{rid}.wav")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.copy(src, path)
        db.add(Recording(id=rid, filename=f"{rid}.wav", wav_path=path, trigger_timestamp=now, created_at=now,
                         duration_seconds=12, sample_rate=48000, channels=1, pre_roll_seconds=5,
                         device_count=1, processing_status="done", device_id="dev1", is_bat=bat))
        db.add(Detection(recording_id=rid, common_name="Carolina Wren", label="x_Carolina Wren",
                         confidence=conf, source="server"))
    db.commit()
    db.close()

    r = client.get("/api/v1/watch/recent")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert 1 <= len(rows) <= 5
    assert rows[0]["id"] == "watch-new"                       # newest first
    assert all(x["id"] != "watch-bat" for x in rows)          # bats left out
    assert [x["time"] for x in rows] == sorted((x["time"] for x in rows), reverse=True)
    a = rows[0]
    assert a["species"] == "Carolina Wren" and a["has_audio"] and a["duration"] > 0 and a["confidence"] == 0.91
    au = client.get("/api/v1/watch/audio/watch-new")
    assert au.status_code == 200 and au.headers["content-type"] == "audio/mp4"
    assert au.content[4:8] == b"ftyp" and len(au.content) > 1000
    assert client.get("/api/v1/watch/audio/nope").status_code == 404


def test_watch_token_may_use_watch_routes():
    from app.main import watch_may_use
    assert watch_may_use("/api/v1/watch/recent")
    assert watch_may_use("/api/v1/watch/audio/3f2a-11")
    assert not watch_may_use("/api/v1/watch/audio/../x")
    assert not watch_may_use("/api/v1/recordings")
