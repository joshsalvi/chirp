"""0.5.10.l: spectrogram cache cleanup, spectrogram fallback without a
folder glob, batched pruning, quiet library logs."""
import datetime
import logging
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

T = os.environ["CHIRP_DATA_DIR"]   # set by conftest.py


def _touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


def _rec(db, rid, wav, **kw):
    from app.models import Recording
    ts = kw.pop("ts", datetime.datetime.utcnow())
    db.add(Recording(id=rid, filename=f"{rid}.wav", wav_path=wav, trigger_timestamp=ts, created_at=ts,
                     duration_seconds=12, sample_rate=48000, channels=1, pre_roll_seconds=5,
                     device_count=1, processing_status="done", device_id="dev1", **kw))


def test_spectrogram_cache_scan_and_purge(client):
    from app.config import settings
    from app.database import SessionLocal
    from app.models import Recording
    d = settings.spectrograms_dir
    db = SessionLocal()
    _rec(db, "sc-live", _touch(os.path.join(T, "recordings_dir", "sc-live.wav")))
    _rec(db, "sc-arch", "", archived_at=datetime.datetime.utcnow())
    db.commit()
    keep = [_touch(os.path.join(d, n)) for n in (
        "sc-live_spectrogram_15.png", "sc-live_spectrogram_15_thumb2.png", "sc-live_spectrogram_0.png",
        "sc-live_spectrogram_bat.png", "sc-live_spectrogram_enhanced_v3.png",
        "sc-arch_spectrogram_40.png", "sc-arch_spectrogram_40_thumb.png")]
    drop = [_touch(os.path.join(d, n)) for n in (
        "sc-live_spectrogram_40.png", "sc-live_spectrogram_40_thumb2.png", "sc-live_spectrogram_15_thumb.png",
        "sc-live_spectrogram_15_pal-mono.png", "sc-gone_spectrogram_15.png")]
    try:
        r = client.get("/api/v1/recordings/storage/status")
        assert r.status_code == 200, r.text
        spec = r.json()["orphans"]["spectrograms"]
        assert spec["orphaned_count"] >= len(drop) and spec["no_owner_count"] >= 1
        r = client.post("/api/v1/recordings/storage/purge-orphans?target=spectrograms&confirm=false")
        assert r.json()["dry_run"] is True and all(os.path.exists(p) for p in drop)
        r = client.post("/api/v1/recordings/storage/purge-orphans?target=spectrograms&confirm=true")
        assert r.status_code == 200 and r.json()["deleted_count"] >= len(drop)
        assert not any(os.path.exists(p) for p in drop)
        assert all(os.path.exists(p) for p in keep)
    finally:
        for p in keep:
            if os.path.exists(p):
                os.unlink(p)
        for r in db.query(Recording).filter(Recording.id.like("sc-%")).all():
            db.delete(r)
        db.commit()
        db.close()


def test_archived_spectrogram_fallback(client):
    from app.config import settings
    from app.database import SessionLocal
    from app.models import Recording
    db = SessionLocal()
    _rec(db, "fb-arch", "", archived_at=datetime.datetime.utcnow())
    db.commit()
    full = _touch(os.path.join(settings.spectrograms_dir, "fb-arch_spectrogram_42.png"), b"\x89PNGfull")
    thumb = _touch(os.path.join(settings.spectrograms_dir, "fb-arch_spectrogram_42_thumb.png"), b"\x89PNGthumb")
    try:
        r = client.get("/api/v1/recordings/fb-arch/spectrogram")
        assert r.status_code == 200 and r.content == b"\x89PNGfull"
        r = client.get("/api/v1/recordings/fb-arch/spectrogram?thumb=true")
        assert r.status_code == 200 and r.content == b"\x89PNGthumb"
    finally:
        os.unlink(full)
        os.unlink(thumb)
        db.query(Recording).filter(Recording.id == "fb-arch").delete()
        db.commit()
        db.close()


def test_prune_by_age_removes_every_file_in_batches(client):
    from app.config import settings
    from app.database import SessionLocal
    from app.models import Detection, Recording
    from app.services.storage_manager import StorageManager
    db = SessionLocal()
    old = datetime.datetime.utcnow() - datetime.timedelta(days=400)
    files = []
    for i in range(25):
        rid = f"pa-{i:02d}"
        wav = _touch(os.path.join(T, "recordings_dir", f"{rid}.flac"))
        twin = _touch(os.path.join(T, "recordings_dir", f"{rid}.wav"))
        spec = _touch(os.path.join(settings.spectrograms_dir, f"{rid}_spectrogram_15_thumb2.png"))
        clip = _touch(os.path.join(settings.clips_dir, f"{rid}_clip.wav"))
        files += [wav, twin, spec, clip]
        _rec(db, rid, wav, ts=old)
        db.add(Detection(recording_id=rid, common_name="Blue Jay", label="x_Blue Jay", confidence=0.5,
                         source="device", clip_path=clip))
    db.commit()
    sm = StorageManager(SessionLocal, settings.recordings_dir, settings.spectrograms_dir, settings.clips_dir)
    try:
        n = sm._prune_by_age(db, 365, keep_flagged=False)
        assert n == 25
        assert db.query(Recording).filter(Recording.id.like("pa-%")).count() == 0
        assert not any(os.path.exists(p) for p in files)
    finally:
        for r in db.query(Recording).filter(Recording.id.like("pa-%")).all():
            db.delete(r)
        db.commit()
        db.close()


def test_library_debug_logs_are_quiet(client):
    from app.services import log_buffer
    log_buffer.install()
    for name in ("matplotlib", "httpcore", "birdbuddy", "asyncio"):
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("chirp.api.recordings").getEffectiveLevel() == logging.DEBUG
