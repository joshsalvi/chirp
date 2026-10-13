"""0.5.12.a: personal notification settings, bird watches, scheduled pushes."""
import sys
import types
import uuid
from datetime import datetime, timedelta, timezone

try:
    import pywebpush  # noqa: F401
except ImportError:
    _m = types.ModuleType("pywebpush"); _m.webpush = lambda *a, **k: None
    class WebPushException(Exception):
        pass
    _m.WebPushException = WebPushException; sys.modules["pywebpush"] = _m


def _db():
    from app.database import SessionLocal
    return SessionLocal()


def test_prefs_and_watches_api(client):
    r = client.get("/api/v1/notifications/prefs")
    if r.status_code == 404:            # no admin row in this test database
        from app.api.auth import _get_crypt
        from app.models import User
        db = _db(); db.add(User(id=str(uuid.uuid4()), username="admin", hashed_pw=_get_crypt().hash("x"), role="admin", active=True)); db.commit(); db.close()
        r = client.get("/api/v1/notifications/prefs")
    p = r.json()
    assert p["new_bird_push"] is True and p["daily_journal_push"] is True and p["weekly_journal_push"] is True
    p = client.put("/api/v1/notifications/prefs", json={"daily_journal_push": False, "daily_digest_push": True}).json()
    assert p["daily_journal_push"] is False and p["daily_digest_push"] is True
    w = client.post("/api/v1/notifications/watches", json={"common_name": "Blue Jay", "mode": "every"}).json()
    again = client.post("/api/v1/notifications/watches", json={"common_name": "blue jay", "mode": "daily"}).json()
    assert again["id"] == w["id"] and again["mode"] == "daily"
    assert client.put(f"/api/v1/notifications/watches/{w['id']}", json={"mode": "every"}).json()["mode"] == "every"
    assert client.post("/api/v1/notifications/watches", json={"common_name": "X", "mode": "hourly"}).status_code == 400
    assert [x["common_name"] for x in client.get("/api/v1/notifications/prefs").json()["watches"]] == ["Blue Jay"]
    assert client.delete(f"/api/v1/notifications/watches/{w['id']}").json()["deleted"]


def test_watch_every_pushes_with_cooldown(client, monkeypatch):
    from app.models import BirdWatch, Detection, Recording
    from app.services import bird_watch, push_notifications
    sent = []
    monkeypatch.setattr(push_notifications, "send_push_to_all", lambda db, t, b, **k: sent.append((t, k["url"])) or 1)
    db = _db()
    try:
        rid = str(uuid.uuid4())
        db.add(Recording(id=rid, filename="w.wav", wav_path="/tmp/w.wav", duration_seconds=3.0, trigger_timestamp=datetime.utcnow(), processing_status="done"))
        db.add(Detection(id=str(uuid.uuid4()), recording_id=rid, label="Cyanocitta cristata_Blue Jay",
                         common_name="Blue Jay", scientific_name="Cyanocitta cristata", confidence=0.93))
        w = BirdWatch(user_id=None, common_name="Blue Jay", mode="every"); db.add(w); db.commit()
        assert bird_watch.notify_watchers(db, rid) == 1
        assert sent == [("Blue Jay detected", f"/recordings/{rid}")]
        assert bird_watch.notify_watchers(db, rid) == 0          # within 10 minutes
        w.last_notified_at = datetime.utcnow() - timedelta(minutes=11); db.commit()
        assert bird_watch.notify_watchers(db, rid) == 1
        db.delete(w); db.commit()
    finally:
        db.query(Detection).filter(Detection.recording_id == rid).delete()
        db.query(Recording).filter(Recording.id == rid).delete()
        db.commit()
        db.close()


def test_scheduled_journal_pushes(client, monkeypatch):
    from app.models import AppSettings
    from app.services import push_notifications, scheduled_push
    sent = []
    monkeypatch.setattr(push_notifications, "send_push_to_all", lambda db, t, b, **k: sent.append((t, k["url"], k["tag"])) or 1)
    db = _db()
    try:
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        s.timezone = "America/New_York"
        s.daily_summary_text = "A quiet, rainy morning."; s.daily_summary_generated_at = datetime(2026, 10, 11, 13, 0)
        s.weekly_summary_text = "A big week."; s.weekly_summary_generated_at = datetime(2026, 10, 11, 12, 0)
        db.commit()
        # Sunday 2026-10-11, 12:00 EDT = 16:00 UTC → weekly; 18:00 EDT = 22:00 UTC → daily
        assert scheduled_push.tick(db, datetime(2026, 10, 11, 16, 0, tzinfo=timezone.utc)) == ["weekly-journal"]
        assert scheduled_push.tick(db, datetime(2026, 10, 11, 22, 0, tzinfo=timezone.utc)) == ["daily-journal"]
        assert scheduled_push.tick(db, datetime(2026, 10, 11, 21, 59, tzinfo=timezone.utc)) == []
        assert sent == [("Weekly Journal", "/journal?entry=weekly", "weekly-journal"),
                        ("Daily Journal", "/journal?entry=daily", "daily-journal")]
        # A journal from a previous day isn't re-sent
        s.daily_summary_generated_at = datetime(2026, 10, 10, 13, 0); db.commit()
        assert scheduled_push.tick(db, datetime(2026, 10, 11, 22, 0, tzinfo=timezone.utc)) == []
    finally:
        db.close()


def test_device_live_detect_uses_device_location(client):
    from app.api.live_detect import device_location
    from app.models import Device, Recording
    db = _db()
    try:
        did = "dev-" + uuid.uuid4().hex[:8]
        db.add(Device(id=did, name="Yard Pi", managed_config={"detection": {"birdnet": {"latitude": 42.1, "longitude": -71.1}}}))
        db.commit()
        assert device_location(db, did) == (42.1, -71.1)                 # from its config
        db.add(Recording(id=str(uuid.uuid4()), filename="d.wav", wav_path="/tmp/d.wav", duration_seconds=3.0,
                         trigger_timestamp=datetime.utcnow(), device_id=did, latitude=42.2768, longitude=-71.3247))
        db.commit()
        assert device_location(db, did) == (42.2768, -71.3247)           # its latest reported GPS wins
        assert device_location(db, None) == (None, None)
    finally:
        db.query(Recording).filter(Recording.device_id == did).delete()
        db.query(Device).filter(Device.id == did).delete()
        db.commit()
        db.close()
