"""Daily digest push and email each go out once, at their own local hour.
From noon on a digest covers that day so far; an earlier hour covers
yesterday. A missed minute or a restart neither skips nor repeats one."""
from datetime import date, datetime, timezone

import tests.test_notifications_inbox  # noqa: F401  (pywebpush stub on bare machines)


def _setup(monkeypatch, push=None, email=None, legacy=None):
    from app.database import SessionLocal, init_db
    from app.models import AppSettings
    from app.services import email_service, push_notifications
    init_db()
    sent = []
    monkeypatch.setattr(email_service, "send_daily_digest", lambda db, day=None: sent.append(("email", day)))
    monkeypatch.setattr(push_notifications, "send_daily_digest_push", lambda db, day=None: sent.append(("push", day)))
    db = SessionLocal()
    s = db.query(AppSettings).filter(AppSettings.id == 1).first() or AppSettings(id=1)
    s.timezone = "America/New_York"
    s.digest_push_hour, s.digest_email_hour, s.digest_hour = push, email, legacy
    s.digest_push_sent_on = s.digest_email_sent_on = None
    db.add(s)
    db.commit()
    return db, sent


def ny(d, h, m=0):
    """A New York wall-clock time in October 2026 (UTC-4), as UTC."""
    return datetime(2026, 10, d, h + 4, m, tzinfo=timezone.utc) if h + 4 < 24 else \
        datetime(2026, 10, d + 1, h + 4 - 24, m, tzinfo=timezone.utc)


def test_evening_push_covers_that_day(monkeypatch):
    from app.services.scheduled_push import daily_digest_tick
    db, sent = _setup(monkeypatch, push=21, email=21)
    try:
        assert daily_digest_tick(db, ny(11, 20, 59)) == []
        assert daily_digest_tick(db, ny(11, 21, 3)) == ["email", "push"]      # minute 0 missed: still sent
        assert daily_digest_tick(db, ny(11, 21, 4)) == []                     # not twice
        assert daily_digest_tick(db, ny(11, 23, 59)) == []
        assert daily_digest_tick(db, ny(12, 0, 30)) == []                     # after midnight: nothing stale
        assert {d for _, d in sent} == {date(2026, 10, 11)}
        assert daily_digest_tick(db, ny(12, 22, 0)) == ["email", "push"]      # next evening, late start
        assert sent[-1] == ("push", date(2026, 10, 12))
    finally:
        db.close()


def test_morning_email_covers_yesterday_separately(monkeypatch):
    from app.services.scheduled_push import daily_digest_tick
    db, sent = _setup(monkeypatch, push=21, email=7)
    try:
        assert daily_digest_tick(db, ny(11, 6, 0)) == []
        assert daily_digest_tick(db, ny(11, 7, 0)) == ["email"]
        assert sent == [("email", date(2026, 10, 10))]
        assert daily_digest_tick(db, ny(11, 21, 0)) == ["push"]
        assert sent[-1] == ("push", date(2026, 10, 11))
    finally:
        db.close()


def test_switching_evening_to_morning_doesnt_repeat(monkeypatch):
    from app.models import AppSettings
    from app.services.scheduled_push import daily_digest_tick
    db, sent = _setup(monkeypatch, push=21, email=21)
    try:
        assert daily_digest_tick(db, ny(11, 21, 0)) == ["email", "push"]
        s = db.query(AppSettings).first()
        s.digest_push_hour = s.digest_email_hour = 7
        db.commit()
        assert daily_digest_tick(db, ny(12, 7, 0)) == []                      # Sunday already sent
        assert daily_digest_tick(db, ny(13, 7, 0)) == ["email", "push"]       # Monday's, Tuesday morning
        assert sent[-1] == ("push", date(2026, 10, 12))
    finally:
        db.close()


def test_legacy_utc_hour_reads_as_local(monkeypatch):
    from app.models import AppSettings
    from app.services.scheduled_push import digest_hours
    db, _ = _setup(monkeypatch, legacy=1)                     # 1 UTC was 9 PM in New York
    try:
        hours = digest_hours(db.query(AppSettings).first())
        assert hours["email"] in (20, 21) and hours["push"] == 21    # 20 once daylight time ends
    finally:
        db.close()
