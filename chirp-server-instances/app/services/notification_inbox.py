"""
Notifications inbox (services/notification_inbox.py)
=====================================================

Every notification the server sends is also stored per person, so the app's
Notifications tab can list it, show it as unread and keep it after the push
banner is gone. send_push_to_all() calls record() before sending.
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("chirp.notifications")

KEEP_DAYS = 90
KEEP_PER_USER = 300


def record(db, title: str, body: str = None, url: str = None, kind: str = None, user_filter=None,
           data: dict = None) -> int:
    """Store one inbox row per active user who passes user_filter (the same
    filter the push uses, e.g. notify_new_bird). With no users (sign-in
    off) one shared row is stored. Returns the number of rows written."""
    from ..models import InboxNotification, User
    try:
        users = [u for u in db.query(User).all()
                 if getattr(u, "active", True) and (user_filter is None or user_filter(u))]
        now = datetime.utcnow()
        # Sign-in off: everyone reads the one shared inbox (user_id None).
        targets = [u.id for u in users] if _auth_on(db) and db.query(User).count() else [None]
        for uid in targets:
            db.add(InboxNotification(user_id=uid, kind=kind, title=title[:200],
                                     body=(body or "")[:2000] or None, url=url, data=data,
                                     created_at=now))
        db.commit()
        _prune(db)
        return len(targets)
    except Exception as e:
        db.rollback()
        logger.warning("Inbox record failed: %s", e)
        return 0


def _auth_on(db) -> bool:
    from ..config import settings
    from ..models import AppSettings
    try:
        s = db.query(AppSettings).first()
        return bool(s.auth_enabled) if (s and s.auth_enabled is not None) else bool(settings.auth_enabled)
    except Exception:
        return bool(settings.auth_enabled)


def _prune(db):
    from ..models import InboxNotification
    cutoff = datetime.utcnow() - timedelta(days=KEEP_DAYS)
    db.query(InboxNotification).filter(InboxNotification.created_at < cutoff).delete(synchronize_session=False)
    db.commit()


def query_for(db, user_id):
    from ..models import InboxNotification
    return db.query(InboxNotification).filter(InboxNotification.user_id == user_id) if user_id \
        else db.query(InboxNotification).filter(InboxNotification.user_id.is_(None))


def unread_count(db, user_id) -> int:
    from ..models import InboxNotification
    return query_for(db, user_id).filter(InboxNotification.read_at.is_(None)).count()
