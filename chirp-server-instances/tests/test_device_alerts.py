"""Station offline alerts: once after the delay (default 15 min), once when back; admins only."""
from datetime import datetime, timedelta

import tests.test_notifications_inbox  # noqa: F401  (pywebpush stub on bare machines)


def _setup(monkeypatch):
    from app.services import device_alerts, push_notifications
    sent, mails = [], []
    monkeypatch.setattr(push_notifications, "send_push_to_all",
                        lambda db, title, body, **k: sent.append((title, body, k)) or 1)
    monkeypatch.setattr(device_alerts, "_email", lambda db, subject, text: mails.append(subject) or 1)
    return sent, mails


def test_offline_then_back(monkeypatch):
    from app.database import SessionLocal, init_db
    from app.models import AppSettings, Device, User
    from app.services import device_alerts
    init_db()
    sent, mails = _setup(monkeypatch)
    db = SessionLocal()
    try:
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        s.device_offline_minutes = None; db.commit()                                   # unset → 15
        now = datetime(2026, 10, 14, 14, 0)
        admin = User(username="alert_admin", hashed_pw="x", role="admin", notify_device_offline_push=True)
        viewer = User(username="alert_viewer", hashed_pw="x", role="viewer", notify_device_offline_push=True)
        pi = Device(name="AlertPi", last_seen=now - timedelta(minutes=5))
        old = Device(name="RetiredPi", last_seen=now - timedelta(days=3))
        hb = Device(name="Haikubox", platform="Haikubox", last_seen=now - timedelta(hours=1))
        db.add_all([admin, viewer, pi, old, hb]); db.commit()

        assert device_alerts.device_offline_tick(db, now) == []                         # 5 min: fine
        assert device_alerts.device_offline_tick(db, now + timedelta(minutes=6)) == []  # 11 min: under 15
        later = now + timedelta(minutes=11)                                             # 16 min silent
        assert device_alerts.device_offline_tick(db, later) == ["AlertPi offline"]
        assert sent[-1][0] == "AlertPi is offline" and "16 min" in sent[-1][1]
        f = sent[-1][2]["user_filter"]
        assert f(admin) and not f(viewer)                                               # admins who opted in
        assert "signed_in_only" in sent[-1][2]
        assert device_alerts.device_offline_tick(db, later + timedelta(minutes=30)) == []  # not again

        pi.last_seen = later + timedelta(minutes=40); db.commit()                       # heartbeat resumes
        assert device_alerts.device_offline_tick(db, later + timedelta(minutes=40, seconds=20)) == ["AlertPi back"]
        assert sent[-1][0] == "AlertPi is back online" and "offline for about 56 min" in sent[-1][1]
        assert db.query(Device).filter_by(name="AlertPi").one().offline_since is None
        assert len(mails) == 2
        for d in (pi, old, hb):
            db.delete(d)
        db.commit()
    finally:
        db.close()


def test_delay_setting(monkeypatch):
    from app.database import SessionLocal, init_db
    from app.models import AppSettings, Device
    from app.services import device_alerts
    init_db()
    sent, _ = _setup(monkeypatch)
    db = SessionLocal()
    try:
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        s.device_offline_minutes = 45; db.commit()
        assert device_alerts.offline_after(db) == timedelta(minutes=45)
        now = datetime(2026, 10, 15, 3, 0)
        pi = Device(name="DelayPi", last_seen=now - timedelta(minutes=30))
        db.add(pi); db.commit()
        assert device_alerts.device_offline_tick(db, now) == []
        assert device_alerts.device_offline_tick(db, now + timedelta(minutes=16)) == ["DelayPi offline"]
        s.device_offline_minutes = 1; db.commit()
        assert device_alerts.offline_after(db) == timedelta(minutes=5)                 # clamped
        db.delete(pi); s.device_offline_minutes = 15; db.commit()
    finally:
        db.close()


def test_settings_api_clamps():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    for sent, want in ((2, 5), (30, 30), (5000, 1440)):
        r = c.put("/api/v1/settings", json={"device_offline_minutes": sent})
        assert r.status_code == 200, r.text
        assert c.get("/api/v1/settings").json()["device_offline_minutes"] == want
    c.put("/api/v1/settings", json={"device_offline_minutes": 15})


def test_signed_in_only_skips_anonymous_subscriptions(monkeypatch):
    from app.database import SessionLocal, init_db
    from app.models import PushSubscription, User
    from app.services import push_notifications
    init_db()
    got = []
    monkeypatch.setattr(push_notifications, "send_push_to_subscription",
                        lambda db, sub, *a, **k: got.append(sub.user_id) or True)
    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="anon_test_admin").first() or User(
            username="anon_test_admin", hashed_pw="x", role="admin")
        db.add(admin); db.commit()
        subs = [PushSubscription(id="sub-admin-t", user_id=admin.id, endpoint="https://e/a", p256dh="k", auth="a"),
                PushSubscription(id="sub-anon-t", user_id=None, endpoint="https://e/anon", p256dh="k", auth="a")]
        db.add_all(subs); db.commit()
        only_admin = lambda u: u.id == admin.id
        push_notifications.send_push_to_all(db, "t", "b", user_filter=only_admin, record_inbox=False)
        assert set(got) >= {admin.id, None}
        got.clear()
        push_notifications.send_push_to_all(db, "t", "b", user_filter=only_admin, record_inbox=False,
                                            signed_in_only=True)
        assert None not in got and admin.id in got
        for x in subs:
            db.delete(x)
        db.commit()
    finally:
        db.close()
