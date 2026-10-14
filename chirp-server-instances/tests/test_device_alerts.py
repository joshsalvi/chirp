"""Station offline alerts: once after 10 silent minutes, once when back."""
from datetime import datetime, timedelta

import tests.test_notifications_inbox  # noqa: F401  (pywebpush stub on bare machines)


def test_offline_then_back(monkeypatch):
    from app.database import SessionLocal, init_db
    from app.models import Device, User
    from app.services import device_alerts, push_notifications
    init_db()
    sent, mails = [], []
    monkeypatch.setattr(push_notifications, "send_push_to_all",
                        lambda db, title, body, **k: sent.append((title, body, k["user_filter"])) or 1)
    monkeypatch.setattr(device_alerts, "_email", lambda db, subject, text: mails.append(subject) or 1)
    db = SessionLocal()
    try:
        now = datetime(2026, 10, 14, 14, 0)
        admin = User(username="alert_admin", hashed_pw="x", role="admin", notify_device_offline_push=True)
        viewer = User(username="alert_viewer", hashed_pw="x", role="viewer", notify_device_offline_push=True)
        pi = Device(name="AlertPi", last_seen=now - timedelta(minutes=5))
        old = Device(name="RetiredPi", last_seen=now - timedelta(days=3))
        hb = Device(name="Haikubox", platform="Haikubox", last_seen=now - timedelta(hours=1))
        db.add_all([admin, viewer, pi, old, hb]); db.commit()

        assert device_alerts.device_offline_tick(db, now) == []                         # 5 min: fine
        later = now + timedelta(minutes=6)                                              # 11 min silent
        assert device_alerts.device_offline_tick(db, later) == ["AlertPi offline"]
        assert sent[-1][0] == "AlertPi is offline" and "11 min" in sent[-1][1]
        f = sent[-1][2]
        assert f(admin) and not f(viewer)                                               # admins who opted in
        assert device_alerts.device_offline_tick(db, later + timedelta(minutes=30)) == []  # not again

        pi.last_seen = later + timedelta(minutes=40); db.commit()                       # heartbeat resumes
        assert device_alerts.device_offline_tick(db, later + timedelta(minutes=40, seconds=20)) == ["AlertPi back"]
        assert sent[-1][0] == "AlertPi is back online" and "offline for about 51 min" in sent[-1][1]
        assert db.query(Device).filter_by(name="AlertPi").one().offline_since is None
        assert len(mails) == 2
    finally:
        db.close()
