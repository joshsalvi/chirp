"""
Station offline alerts. A Pi heartbeats every 30 s; when one has been
silent for AppSettings.device_offline_minutes (default 15, Settings →
Alerts & Email), admins who turned on "Station offline" (My Notifications)
get a push and/or email, and another when it reports again. Only admins:
with sign-in on, pushes skip devices that aren't signed in.

Run once a minute per site (main.py's digest loop). Haikubox and Bird
Buddy aren't stations and are skipped. A station already silent for more
than a day when this first sees it (unplugged, retired) isn't announced.
"""
import logging
from datetime import datetime, timedelta, timezone
from html import escape

logger = logging.getLogger("chirp.device_alerts")

DEFAULT_OFFLINE_MINUTES = 15
BACK_WITHIN = timedelta(minutes=2)
STALE_AFTER = timedelta(hours=24)


def offline_after(db) -> timedelta:
    from ..models import AppSettings
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    m = getattr(s, "device_offline_minutes", None) or DEFAULT_OFFLINE_MINUTES
    return timedelta(minutes=min(1440, max(5, int(m))))


def _virtual(d) -> bool:
    return d.platform in ("Haikubox", "Bird Buddy") or d.birdnet_backend in ("haikubox", "bird_buddy")


def _wants(col):
    return lambda u: getattr(u, "role", None) == "admin" and bool(getattr(u, col, False))


def _when(db, dt_utc: datetime) -> str:
    from ..models import AppSettings
    from .scheduled_push import site_tz
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    local = dt_utc.replace(tzinfo=timezone.utc).astimezone(site_tz(s))
    return local.strftime("%-I:%M %p").replace("AM", "am").replace("PM", "pm")


def _span(td: timedelta) -> str:
    m = max(1, int(td.total_seconds() // 60))
    if m < 60:
        return f"{m} min"
    h, m = divmod(m, 60)
    return f"{h} h {m} min" if m else f"{h} h"


def _email(db, subject: str, text: str):
    from ..models import User
    from .email_service import _get_smtp_config, _get_server_url, _send, _wrap_html
    cfg = _get_smtp_config(db)
    if not cfg:
        return 0
    want = _wants("notify_device_offline_email")
    to = [u.email for u in db.query(User).all() if getattr(u, "active", True) and u.email and want(u)]
    if not to:
        return 0
    base = _get_server_url(db)
    html = f"<p>{escape(text)}</p>"
    return int(_send(cfg, to, subject, _wrap_html(subject, text, html, cta_url=f"{base}/devices",
                                                  cta_label="Open Devices", server_url=base), text))


def _notify(db, title: str, body: str):
    from .push_notifications import send_push_to_all
    from .notification_inbox import _auth_on
    send_push_to_all(db, title, body, url="/devices", tag="device-offline",
                     user_filter=_wants("notify_device_offline_push"), signed_in_only=_auth_on(db))
    try:
        _email(db, title, body)
    except Exception as e:
        logger.warning("Station alert email failed: %s", e)


def device_offline_tick(db, now: datetime = None) -> list:
    """Announce stations that went silent or came back. Returns what was sent."""
    from ..models import Device
    now = now or datetime.utcnow()
    after = offline_after(db)
    sent = []
    for d in db.query(Device).all():
        if _virtual(d) or not d.last_seen:
            continue
        name = d.name or d.hostname or "Your station"
        silent = now - d.last_seen
        if d.offline_since is None:
            if after <= silent <= STALE_AFTER:
                d.offline_since = d.last_seen
                db.commit()
                _notify(db, f"{name} is offline",
                        f"No signal since {_when(db, d.last_seen)} ({_span(silent)}). "
                        "It may have crashed, lost power or lost Wi-Fi.")
                sent.append(f"{name} offline")
        elif silent <= BACK_WITHIN:
            down = now - d.offline_since
            since = _when(db, d.offline_since)
            d.offline_since = None
            db.commit()
            _notify(db, f"{name} is back online", f"It was offline for about {_span(down)}, since {since}.")
            sent.append(f"{name} back")
    return sent
