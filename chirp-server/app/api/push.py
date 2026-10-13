"""
Push Notification Endpoints (api/push.py)
============================================

REST surface for services/push_notifications.py — the PWA calls these
directly to get the VAPID public key, register/unregister a browser's
push subscription, and send itself a test notification.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PushSubscription

router = APIRouter(tags=["push"])


@router.get("/vapid-public-key")
def get_vapid_public_key(db: Session = Depends(get_db)):
    """The PWA needs this to call PushManager.subscribe({applicationServerKey: ...})."""
    from ..services.push_notifications import get_or_create_vapid_keys
    public_key, _ = get_or_create_vapid_keys(db)
    return {"public_key": public_key}


class SubscribeRequest(BaseModel):
    endpoint: str
    keys: dict  # {"p256dh": "...", "auth": "..."} — as delivered directly by PushSubscription.toJSON() in the browser
    user_agent: Optional[str] = None


def _current_user_id(request: Request, db: Session) -> Optional[str]:
    """Best-effort — a subscription is still useful even with auth disabled
    or no valid token, it just won't be tied to a specific user's
    notify_new_bird preference in that case (send_push_to_all's
    user_filter only restricts subscriptions that ARE tied to a user)."""
    try:
        from .auth import verify_token
        from ..models import User
        auth_header = request.headers.get("Authorization", "")
        token = auth_header[7:] if auth_header.startswith("Bearer ") else None
        if not token:
            return None
        payload = verify_token(token)
        if not payload:
            return None
        user = db.query(User).filter(User.username == payload.get("sub")).first()
        return user.id if user else None
    except Exception:
        return None


@router.post("/subscribe")
def subscribe(body: SubscribeRequest, request: Request, db: Session = Depends(get_db)):
    """
    Registers (or re-registers) a browser's push subscription. Endpoint
    is unique — re-subscribing the same browser (e.g. after a permission
    reset) updates the existing row via its endpoint rather than creating
    a duplicate.
    """
    keys = body.keys or {}
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")
    if not p256dh or not auth:
        raise HTTPException(status_code=400, detail="Subscription is missing p256dh/auth keys")

    user_id = _current_user_id(request, db)
    existing = db.query(PushSubscription).filter(PushSubscription.endpoint == body.endpoint).first()
    if existing:
        existing.p256dh = p256dh
        existing.auth = auth
        existing.user_id = user_id
        existing.user_agent = body.user_agent
        db.commit()
        return {"ok": True, "id": existing.id}

    import uuid
    sub = PushSubscription(
        id=str(uuid.uuid4()), endpoint=body.endpoint, p256dh=p256dh, auth=auth,
        user_id=user_id, user_agent=body.user_agent,
    )
    db.add(sub)
    db.commit()
    return {"ok": True, "id": sub.id}


class UnsubscribeRequest(BaseModel):
    endpoint: str


@router.post("/unsubscribe")
def unsubscribe(body: UnsubscribeRequest, db: Session = Depends(get_db)):
    sub = db.query(PushSubscription).filter(PushSubscription.endpoint == body.endpoint).first()
    if sub:
        db.delete(sub)
        db.commit()
    return {"ok": True}


class RegisterNativeRequest(BaseModel):
    device_token: str  # the raw APNs device token, as delivered by native.push.register()'s onRegistration callback


@router.post("/register-native")
def register_native(body: RegisterNativeRequest, request: Request, db: Session = Depends(get_db)):
    """
    Registers (or re-registers) the native iOS app's APNs device token —
    the counterpart to /subscribe above, for the Capacitor app rather
    than the PWA. Called from frontend/src/native/index.js's
    push.register() once Apple hands back a token, not called at all
    when running as the PWA (native.js's own platform check already
    gates that — see App.jsx's usage).
    """
    from ..models import ApnsDeviceToken

    if not body.device_token:
        raise HTTPException(status_code=400, detail="device_token is required")

    user_id = _current_user_id(request, db)
    existing = db.query(ApnsDeviceToken).filter(ApnsDeviceToken.device_token == body.device_token).first()
    if existing:
        existing.user_id = user_id
        db.commit()
        return {"ok": True, "id": existing.id}

    import uuid
    row = ApnsDeviceToken(id=str(uuid.uuid4()), device_token=body.device_token, user_id=user_id)
    db.add(row)
    db.commit()
    return {"ok": True, "id": row.id}


@router.post("/unregister-native")
def unregister_native(body: RegisterNativeRequest, db: Session = Depends(get_db)):
    from ..models import ApnsDeviceToken
    row = db.query(ApnsDeviceToken).filter(ApnsDeviceToken.device_token == body.device_token).first()
    if row:
        db.delete(row)
        db.commit()
    return {"ok": True}


@router.get("/status")
def push_status(endpoint: Optional[str] = None, db: Session = Depends(get_db)):
    """Whether THIS browser (identified by an endpoint it already knows,
    passed as a query param by the frontend) is currently subscribed —
    lets the Settings UI show the right button state (Enable vs. Disable)
    without needing its own separate tracking."""
    subscribed = False
    if endpoint:
        subscribed = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first() is not None
    total = db.query(PushSubscription).count()
    return {"subscribed": subscribed, "total_subscriptions": total}


class TestPushRequest(BaseModel):
    endpoint: str


@router.post("/test")
def send_test_push(body: TestPushRequest, db: Session = Depends(get_db)):
    """Sends a test notification to the CURRENT browser's subscription only
    (identified by its endpoint) — not a broadcast to every device, so
    testing on one browser doesn't spam every other subscribed device."""
    from ..services.push_notifications import send_push_to_subscription
    sub = db.query(PushSubscription).filter(PushSubscription.endpoint == body.endpoint).first()
    if not sub:
        raise HTTPException(status_code=404, detail="This browser isn't subscribed yet")
    result = send_push_to_subscription(db, sub, "Chirp test notification", "If you can see this, push notifications are working.")
    if not result:
        raise HTTPException(status_code=502, detail=result.error or "Send failed for an unknown reason")
    return {"ok": True}


@router.post("/test-native")
def send_test_native(request: Request, db: Session = Depends(get_db)):
    """Sends a test notification to the signed-in person's iPhones (every
    APNs token registered to them) and adds it to their Notifications tab.
    Reports how many phones Apple accepted it for, or why none did."""
    from ..models import ApnsDeviceToken
    from ..services.apns_push import send_apns_push
    from ..services.notification_inbox import record
    uid = _current_user_id(request, db)
    q = db.query(ApnsDeviceToken)
    q = q.filter(ApnsDeviceToken.user_id == uid) if uid else q.filter(ApnsDeviceToken.user_id.is_(None))
    tokens = q.all()
    title, text = "Chirp test notification", "If you can see this, push notifications are working."
    record(db, title, text, url="/notifications", kind="test",
           user_filter=(lambda u: u.id == uid) if uid else None)
    if not tokens:
        raise HTTPException(status_code=404, detail="No iPhone is registered for push on this account yet. Open the Chirp app and allow notifications.")
    errors, sent = [], 0
    for row in tokens:
        r = send_apns_push(db, row.device_token, title, text, url="/notifications", token_row=row)
        if r:
            sent += 1
        else:
            errors.append(r.error)
    if not sent:
        raise HTTPException(status_code=502, detail="; ".join(e for e in errors if e) or "Send failed")
    return {"ok": True, "sent": sent, "devices": len(tokens)}
