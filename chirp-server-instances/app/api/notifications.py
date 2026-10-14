"""
Notifications inbox API (api/notifications.py)
================================================

GET    /api/v1/notifications             newest first, with the unread count
GET    /api/v1/notifications/unread      {"unread": n} for the tab badge
POST   /api/v1/notifications/read-all    mark everything read
POST   /api/v1/notifications/{id}/read   mark one read
DELETE /api/v1/notifications             clear the signed-in person's inbox
GET/PUT /api/v1/notifications/prefs      personal push and email choices + bird watches
POST/PUT/DELETE /api/v1/notifications/watches[/{id}]   tag species to be told about
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import InboxNotification
from ..services import notification_inbox as inbox
from .auth import get_current_user

router = APIRouter()


def _uid(user) -> Optional[str]:
    return user.id if user is not None else None


def _out(n: InboxNotification) -> dict:
    return {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "url": n.url,
            "data": n.data,
            "created_at": n.created_at.isoformat() + "Z" if n.created_at else None,
            "read": n.read_at is not None}


@router.get("")
def list_notifications(limit: int = Query(100, ge=1, le=300), db: Session = Depends(get_db),
                       user=Depends(get_current_user)):
    uid = _uid(user)
    rows = inbox.query_for(db, uid).order_by(InboxNotification.created_at.desc(),
                                             InboxNotification.id.desc()).limit(limit).all()
    return {"items": [_out(n) for n in rows], "unread": inbox.unread_count(db, uid)}


@router.get("/unread")
def unread(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return {"unread": inbox.unread_count(db, _uid(user))}


@router.post("/read-all")
def read_all(db: Session = Depends(get_db), user=Depends(get_current_user)):
    n = inbox.query_for(db, _uid(user)).filter(InboxNotification.read_at.is_(None)) \
        .update({InboxNotification.read_at: datetime.utcnow()}, synchronize_session=False)
    db.commit()
    return {"marked": n, "unread": 0}


@router.post("/{notification_id}/read")
def read_one(notification_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    row = inbox.query_for(db, _uid(user)).filter(InboxNotification.id == notification_id).first()
    if not row:
        raise HTTPException(404, "Notification not found")
    if row.read_at is None:
        row.read_at = datetime.utcnow()
        db.commit()
    return {"ok": True, "unread": inbox.unread_count(db, _uid(user))}


@router.delete("/{notification_id}")
def delete_one(notification_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    n = inbox.query_for(db, _uid(user)).filter(InboxNotification.id == notification_id) \
        .delete(synchronize_session=False)
    db.commit()
    if not n:
        raise HTTPException(404, "Notification not found")
    return {"deleted": n, "unread": inbox.unread_count(db, _uid(user))}


@router.delete("")
def clear(db: Session = Depends(get_db), user=Depends(get_current_user)):
    n = inbox.query_for(db, _uid(user)).delete(synchronize_session=False)
    db.commit()
    return {"deleted": n, "unread": 0}


# ── Personal notification settings and bird watches ──────────────────────
PREF_FIELDS = {
    "new_bird_push": ("notify_new_bird_push", True),
    "daily_digest_push": ("notify_daily_digest_push", False),
    "daily_journal_push": ("notify_daily_journal_push", True),
    "weekly_journal_push": ("notify_weekly_journal_push", True),
    "new_bird_email": ("notify_new_bird", True),
    "daily_digest_email": ("notify_daily_digest", False),
    "device_offline_push": ("notify_device_offline_push", False),
    "device_offline_email": ("notify_device_offline_email", False),
}


def _me(db, user):
    """The signed-in person, or the admin account when sign-in is off."""
    from ..models import User
    if user is not None:
        return user
    u = db.query(User).filter(User.username == "admin").first()
    if not u:
        raise HTTPException(404, "No account to store notification settings on")
    return u


def _watch_out(w):
    return {"id": w.id, "common_name": w.common_name, "mode": w.mode}


@router.get("/prefs")
def get_prefs(db: Session = Depends(get_db), user=Depends(get_current_user)):
    from ..models import BirdWatch
    u = _me(db, user)
    out = {k: (getattr(u, col) if getattr(u, col, None) is not None else d) for k, (col, d) in PREF_FIELDS.items()}
    out["is_admin"] = getattr(u, "role", None) == "admin"   # station alerts are for admins
    out["watches"] = [_watch_out(w) for w in db.query(BirdWatch).filter(BirdWatch.user_id == u.id)
                      .order_by(BirdWatch.common_name).all()]
    # When the site sends the digest (local hours), for the descriptions.
    from ..models import AppSettings
    from ..services.scheduled_push import digest_hours
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if s:
        hours = digest_hours(s)
        out["digest_push_hour"], out["digest_email_hour"] = hours["push"], hours["email"]
    return out


@router.put("/prefs")
def put_prefs(body: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    u = _me(db, user)
    for k, (col, _d) in PREF_FIELDS.items():
        if k in body:
            setattr(u, col, bool(body[k]))
    db.commit()
    return get_prefs(db, user)


@router.post("/watches")
def add_watch(body: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    from ..models import BirdWatch
    from sqlalchemy import func
    u = _me(db, user)
    name = (body.get("common_name") or "").strip()
    mode = body.get("mode") or "every"
    if not name:
        raise HTTPException(400, "common_name is required")
    if mode not in ("every", "daily"):
        raise HTTPException(400, "mode must be 'every' or 'daily'")
    w = db.query(BirdWatch).filter(BirdWatch.user_id == u.id, func.lower(BirdWatch.common_name) == name.lower()).first()
    if w:
        w.mode = mode
    else:
        w = BirdWatch(user_id=u.id, common_name=name, mode=mode)
        db.add(w)
    db.commit()
    return _watch_out(w)


@router.put("/watches/{watch_id}")
def update_watch(watch_id: str, body: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    from ..models import BirdWatch
    u = _me(db, user)
    w = db.query(BirdWatch).filter(BirdWatch.id == watch_id, BirdWatch.user_id == u.id).first()
    if not w:
        raise HTTPException(404, "Not found")
    if body.get("mode") not in ("every", "daily"):
        raise HTTPException(400, "mode must be 'every' or 'daily'")
    w.mode = body["mode"]
    db.commit()
    return _watch_out(w)


@router.delete("/watches/{watch_id}")
def delete_watch(watch_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    from ..models import BirdWatch
    u = _me(db, user)
    n = db.query(BirdWatch).filter(BirdWatch.id == watch_id, BirdWatch.user_id == u.id).delete()
    db.commit()
    if not n:
        raise HTTPException(404, "Not found")
    return {"deleted": True}
