"""
Scheduled pushes (services/scheduled_push.py)
=============================================

Checked every minute per location, in the location's time zone
(AppSettings.timezone):
  18:00 daily   the Daily Journal       → /journal?entry=daily
  12:00 Sunday  the Weekly Journal      → /journal?entry=weekly
  19:00 daily   watched-bird summaries  (services/bird_watch.py)
Each person chooses which they get (Settings → My Notifications).

The daily digest goes out twice, each at its own local hour (AppSettings
digest_push_hour and digest_email_hour, in AppSettings.timezone). An hour
from noon on covers that same day so far; an earlier hour covers
yesterday. daily_digest_tick records the day each one covered, so a missed
minute or a restart neither skips it nor sends it twice.
"""
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger("chirp.scheduled_push")

DAILY_JOURNAL_AT = (18, 0)
WEEKLY_JOURNAL_AT = (6, 12, 0)     # weekday (Sunday=6), hour, minute
WATCH_SUMMARY_AT = (19, 0)


def _pref(name, default=True):
    return lambda u: (getattr(u, name) if getattr(u, name, None) is not None else default)


def _excerpt(text: str, n: int = 160) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


DEFAULT_PUSH_HOUR = 21
DEFAULT_EMAIL_HOUR = 21


def site_tz(s):
    try:
        return ZoneInfo(getattr(s, "timezone", None) or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def digest_hours(s) -> dict:
    """Local send hours {"push": h, "email": h}. Sites saved before these
    existed keep their email time: the old UTC digest_hour, as local time."""
    push = getattr(s, "digest_push_hour", None)
    email = getattr(s, "digest_email_hour", None)
    if email is None:
        legacy = getattr(s, "digest_hour", None)
        if legacy is None:
            email = DEFAULT_EMAIL_HOUR
        else:
            now = datetime.now(timezone.utc).replace(hour=legacy, minute=0, second=0, microsecond=0)
            email = now.astimezone(site_tz(s)).hour
    return {"push": DEFAULT_PUSH_HOUR if push is None else push, "email": email}


def digest_day(hour: int, now_local: datetime):
    """The day a digest sent at `hour` covers: today from noon on,
    otherwise yesterday."""
    return now_local.date() if hour >= 12 else now_local.date() - timedelta(days=1)


def due_digest_day(hour: int, sent_on, now_local: datetime):
    """The day to send now, or None: due once the local clock reaches the
    hour, once per covered day."""
    day = digest_day(hour, now_local)
    if now_local.hour < hour or sent_on == day.isoformat():
        return None
    return day


def daily_digest_tick(db, now_utc: datetime = None) -> list:
    """Send the digest push and email when each is due. Returns what was
    sent, e.g. ["push", "email"]."""
    from ..models import AppSettings
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if not s:
        return []
    now_local = (now_utc or datetime.now(timezone.utc)).astimezone(site_tz(s))
    hours = digest_hours(s)
    due = {kind: due_digest_day(hours[kind], getattr(s, f"digest_{kind}_sent_on", None), now_local)
           for kind in ("push", "email")}
    due = {k: d for k, d in due.items() if d is not None}
    if not due:
        return []
    for kind, day in due.items():   # recorded first: a failure below must not resend every minute
        setattr(s, f"digest_{kind}_sent_on", day.isoformat())
    db.commit()
    if "email" in due:
        try:
            from .email_service import send_daily_digest
            send_daily_digest(db, day=due["email"])
        except Exception as e:
            logger.warning("Daily digest email failed: %s", e)
    if "push" in due:
        try:
            from .push_notifications import send_daily_digest_push
            send_daily_digest_push(db, day=due["push"])
        except Exception as e:
            logger.warning("Daily digest push failed: %s", e)
    return sorted(due)


def tick(db, now_utc: datetime = None) -> list:
    """Send whatever is due this minute. Returns the names of what was sent."""
    from ..models import AppSettings
    from .push_notifications import send_push_to_all
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if not s:
        return []
    tz = site_tz(s)
    now_utc = now_utc or datetime.now(timezone.utc)
    local = now_utc.astimezone(tz)
    hm = (local.hour, local.minute)
    done = []

    if hm == DAILY_JOURNAL_AT and getattr(s, "daily_summary_text", None):
        gen = getattr(s, "daily_summary_generated_at", None)
        if gen and gen.replace(tzinfo=timezone.utc).astimezone(tz).date() == local.date():
            send_push_to_all(db, "Daily Journal", _excerpt(s.daily_summary_text), url="/journal?entry=daily",
                             tag="daily-journal", user_filter=_pref("notify_daily_journal_push"))
            done.append("daily-journal")

    if (local.weekday(),) + hm == WEEKLY_JOURNAL_AT and getattr(s, "weekly_summary_text", None):
        gen = getattr(s, "weekly_summary_generated_at", None)
        if gen and now_utc - gen.replace(tzinfo=timezone.utc) < timedelta(days=7):
            send_push_to_all(db, "Weekly Journal", _excerpt(s.weekly_summary_text), url="/journal?entry=weekly",
                             tag="weekly-journal", user_filter=_pref("notify_weekly_journal_push"))
            done.append("weekly-journal")

    if hm == WATCH_SUMMARY_AT:
        from .bird_watch import send_daily_watch_summaries
        start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
        start = start_local.astimezone(timezone.utc).replace(tzinfo=None)
        if send_daily_watch_summaries(db, start, now_utc.replace(tzinfo=None)):
            done.append("watch-summary")
    return done
