"""
Bird watch alerts (services/bird_watch.py)
===========================================

People tag species in Settings → My Notifications (or on a species page):
  every  a push each time the species is in a new recording, linking to it
         (at most one per species per person every 10 minutes)
  daily  one summary at 7 pm local time with today's counts
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("chirp.bird_watch")
COOLDOWN = timedelta(minutes=10)


def _display_threshold(db) -> float:
    from ..models import AppSettings
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    return float(getattr(s, "min_confidence_display", 0) or 0) if s else 0.0


def notify_watchers(db, rec_id: str) -> int:
    """Push "every" watchers for the species shown on this recording."""
    from ..models import BirdWatch, Recording
    from .push_notifications import send_push_to_all
    rec = db.query(Recording).filter(Recording.id == rec_id).first()
    if not rec or getattr(rec, "deleted_at", None) or getattr(rec, "is_live_detect_clip", False) \
            or getattr(rec, "is_live_session", False) or getattr(rec, "is_bat", False):
        return 0
    floor = _display_threshold(db)
    best = {}
    for d in rec.detections or []:
        if d.common_name and (d.confidence or 0) >= floor:
            k = d.common_name.lower()
            best[k] = max(best.get(k, (0, d.common_name))[0], d.confidence or 0), d.common_name
    if not best:
        return 0
    now = datetime.utcnow()
    sent = 0
    for w in db.query(BirdWatch).filter(BirdWatch.mode == "every").all():
        hit = best.get((w.common_name or "").lower())
        if not hit or (w.last_notified_at and now - w.last_notified_at < COOLDOWN):
            continue
        conf, name = hit
        uid = w.user_id
        send_push_to_all(db, f"{name} detected", f"{round(conf * 100)}% confidence. Tap to listen.",
                         url=f"/recordings/{rec.id}", tag="bird-watch",
                         user_filter=(lambda u, uid=uid: u.id == uid) if uid else None)
        w.last_notified_at = now
        db.commit()
        sent += 1
    return sent


def send_daily_watch_summaries(db, day_start_utc: datetime, day_end_utc: datetime) -> int:
    """One push per person with "daily" watches: today's detection counts."""
    from sqlalchemy import func
    from ..models import BirdWatch, Detection, Recording
    from .push_notifications import send_push_to_all
    floor = _display_threshold(db)
    by_user = {}
    for w in db.query(BirdWatch).filter(BirdWatch.mode == "daily").all():
        by_user.setdefault(w.user_id, []).append(w.common_name)
    sent = 0
    for uid, names in by_user.items():
        rows = (db.query(Detection.common_name, func.count(func.distinct(Detection.recording_id)))
                .join(Recording, Detection.recording_id == Recording.id)
                .filter(func.lower(Detection.common_name).in_([n.lower() for n in names]),
                        Detection.confidence >= floor,
                        Recording.trigger_timestamp >= day_start_utc,
                        Recording.trigger_timestamp < day_end_utc,
                        Recording.deleted_at.is_(None))
                .group_by(Detection.common_name).all())
        if rows:
            rows.sort(key=lambda r: -r[1])
            body = " · ".join(f"{n} ×{c}" for n, c in rows[:6])
            if len(rows) > 6:
                body += f" · +{len(rows) - 6} more"
        else:
            body = "None of your watched birds were heard today."
        send_push_to_all(db, "Your watched birds today", body, url="/notifications",
                         tag="bird-watch-daily", user_filter=(lambda u, uid=uid: u.id == uid) if uid else None)
        sent += 1
    return sent
