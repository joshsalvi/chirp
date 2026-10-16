"""0.5.14: saved recordings are kept out of automatic cleanup; recordings
filter by time of day (site time zone, DST included)."""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _setup():
    from app.database import SessionLocal, init_db
    from app.models import AppSettings, Recording
    init_db()
    db = SessionLocal()
    db.query(Recording).filter(Recording.filename.like("tod-%")).delete(synchronize_session=False)
    s = db.query(AppSettings).filter(AppSettings.id == 1).first() or AppSettings(id=1)
    s.timezone = "America/New_York"
    db.merge(s); db.commit()
    return db


def test_time_of_day_filter_respects_dst():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import recordings
    from app.models import Recording
    db = _setup()
    # 06:30 local in summer (EDT, UTC-4) and winter (EST, UTC-5); 23:30 local in summer.
    rows = {"tod-summer-dawn": dt.datetime(2026, 7, 1, 10, 30), "tod-winter-dawn": dt.datetime(2026, 1, 15, 11, 30),
            "tod-summer-night": dt.datetime(2026, 7, 2, 3, 30), "tod-noon": dt.datetime(2026, 7, 3, 16, 0)}
    for name, ts in rows.items():
        db.add(Recording(id=name, filename=name, wav_path="", trigger_timestamp=ts, duration_seconds=3))
    db.commit()
    app = FastAPI(); app.include_router(recordings.router, prefix="/api/v1/recordings")
    c = TestClient(app)

    def ids(**p):
        r = c.get("/api/v1/recordings", params={"limit": 200, "no_detections": True, **p})
        assert r.status_code == 200, r.text
        body = r.json()
        items = body["items"] if isinstance(body, dict) else body
        return {x["id"] for x in items if x["id"].startswith("tod-")}

    assert ids(time_from="06:00", time_to="07:00") == {"tod-summer-dawn", "tod-winter-dawn"}
    assert ids(time_from="21:00", time_to="04:00") == {"tod-summer-night"}          # wraps midnight
    assert ids(time_from="11:00", time_to="13:00") == {"tod-noon"}
    assert c.get("/api/v1/recordings", params={"time_from": "25:00"}).status_code == 422
    db.query(Recording).filter(Recording.filename.like("tod-%")).delete(synchronize_session=False); db.commit()


def test_saved_recordings_survive_cleanup(tmp_path):
    from app.api.app_settings import _empty_recording_query
    from app.models import Recording
    from app.services.storage_manager import StorageManager
    db = _setup()
    old = dt.datetime(2020, 1, 1)
    db.add(Recording(id="tod-saved", filename="tod-saved", wav_path="", trigger_timestamp=old, duration_seconds=3, is_saved=True))
    db.add(Recording(id="tod-plain", filename="tod-plain", wav_path="", trigger_timestamp=old, duration_seconds=3))
    db.commit()
    empty = {r.id for r in _empty_recording_query(db, "no_detections").all()}
    assert "tod-plain" in empty and "tod-saved" not in empty
    sm = StorageManager(lambda: db, str(tmp_path), str(tmp_path), str(tmp_path))
    sm._prune_by_age(db, 30, keep_flagged=False)
    db.expire_all()
    left = {r.id for r in db.query(Recording).filter(Recording.filename.like("tod-%"))}
    assert left == {"tod-saved"}
    db.query(Recording).filter(Recording.filename.like("tod-%")).delete(synchronize_session=False); db.commit(); db.close()
