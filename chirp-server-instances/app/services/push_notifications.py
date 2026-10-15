"""
Web Push support for the PWA — real OS-level notifications on a
subscribed device, including while the app is closed, via the browser's
Push API and the service worker's 'push' handler. Distinct from
email_service.py's notify_new_bird/daily-digest, which only sends email.

VAPID keys are stored as the raw private key scalar, base64url-encoded
with no padding (not PEM — pywebpush's Vapid.from_string() expects the
raw form). Generated once by get_or_create_vapid_keys and never rotated
in place, since rotating would invalidate every already-stored
subscription.
"""

import base64
import json
import logging

from pywebpush import webpush, WebPushException

logger = logging.getLogger("chirp.push")

VAPID_CLAIMS_EMAIL_FALLBACK = "mailto:admin@chirp.local"  # only used if no server_url is configured at all


def _vapid_sub_claim(db) -> str:
    """
    Derives the VAPID 'sub' claim from the configured server domain
    instead of a placeholder. Apple's web push service validates this
    more strictly than Chrome/FCM; a real domain avoids its 403/BadJwtToken
    rejection.
    """
    from ..models import AppSettings
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    server_url = getattr(s, "server_url", None) if s else None
    if server_url:
        try:
            from urllib.parse import urlparse
            host = urlparse(server_url).netloc or urlparse(f"https://{server_url}").netloc
            if host:
                return f"mailto:admin@{host}"
        except Exception:
            pass
    return VAPID_CLAIMS_EMAIL_FALLBACK


def get_or_create_vapid_keys(db):
    """
    Returns (public_key_b64url, private_key_b64url), generating and
    persisting a new pair on first call. public_key_b64url is the raw
    65-byte uncompressed EC point (the exact format a browser's
    PushManager.subscribe({applicationServerKey: ...}) needs), not a PEM
    — confirmed by testing the real extraction against a live key.
    """
    from ..models import AppSettings
    from py_vapid import Vapid02

    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if s and s.vapid_public_key and s.vapid_private_key:
        return s.vapid_public_key, s.vapid_private_key

    v = Vapid02()
    v.generate_keys()

    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    raw_public = v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    public_b64url = base64.urlsafe_b64encode(raw_public).rstrip(b"=").decode("ascii")

    raw_private = v.private_key.private_numbers().private_value.to_bytes(32, "big")
    private_b64url = base64.urlsafe_b64encode(raw_private).rstrip(b"=").decode("ascii")

    if s is None:
        s = AppSettings(id=1)
        db.add(s)
    s.vapid_public_key = public_b64url
    s.vapid_private_key = private_b64url
    db.commit()
    logger.info("Generated new VAPID key pair for push notifications")
    return public_b64url, private_b64url


def send_push_to_subscription(db, subscription, title: str, body: str, url: str = None, tag: str = None):
    """
    Sends one push notification to one stored PushSubscription row.
    Returns a PushResult — truthy on success (so `if
    send_push_to_subscription(...):` still works), also carrying `.error`
    with the real failure reason instead of a generic message. A 404/410
    response means the subscription is dead; that row gets deleted here.
    """
    _public, private_key = get_or_create_vapid_keys(db)
    payload = {"title": title, "body": body}
    if url:
        payload["url"] = url
    if tag:
        payload["tag"] = tag

    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps(payload),
            vapid_private_key=private_key,
            vapid_claims={"sub": _vapid_sub_claim(db)},
        )
        from datetime import datetime as _dt
        subscription.last_used_at = _dt.utcnow()
        db.commit()
        return PushResult(True, None)
    except WebPushException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        body_text = None
        try:
            body_text = getattr(e, "response", None).text
        except Exception:
            pass
        detail = f"HTTP {status}: {body_text}" if status else str(e)
        if status in (404, 410):
            logger.info("Push subscription expired/gone, removing: %s", subscription.endpoint[:60])
            db.delete(subscription)
            db.commit()
            detail = "Subscription expired or was removed by the browser/OS — re-enable notifications to create a fresh one."
        else:
            # Log the actual response body, not just the exception
            # string — the real rejection reason lives there.
            logger.warning("Push send failed (%s): %s | response body: %s", status, e, body_text)
        return PushResult(False, detail)
    except Exception as e:
        logger.warning("Push send failed: %s", e)
        return PushResult(False, str(e))


class PushResult:
    """Truthy/falsy like a bool (so `if send_push_to_subscription(...):`
    keeps working for existing callers that only care about success),
    while also carrying the real error detail for callers that want it."""
    def __init__(self, ok: bool, error):
        self.ok = ok
        self.error = error

    def __bool__(self):
        return self.ok


def app_path(url):
    """In-app path for a push link. A full URL (e.g. built from server_url)
    would open the browser from the iOS app and could point at another
    host, so only its path, query and fragment are kept."""
    if not url or url.startswith("/"):
        return url or None
    from urllib.parse import urlparse
    u = urlparse(url if "://" in url else f"https://{url}")
    path = u.path or "/"
    return path + (f"?{u.query}" if u.query else "") + (f"#{u.fragment}" if u.fragment else "")


def send_push_to_all(db, title: str, body: str, url: str = None, tag: str = None, user_filter=None,
                     record_inbox: bool = True, data: dict = None, signed_in_only: bool = False) -> int:
    """
    Sends to every stored Web Push subscription AND every registered
    native (APNs) device token — one call reaches both the PWA and the
    native iOS app, so existing callers (e.g. the new-bird-detected
    trigger in api/recordings.py) automatically cover both once APNs is
    configured, without needing a second call site added anywhere.
    APNs sending is a safe no-op if unconfigured (see apns_push.py), so
    this doesn't change behavior at all for an install that hasn't set
    up native push.

    Returns the total successful sends across both mechanisms — optionally
    filtered to specific users (user_filter: a callable taking a User and
    returning bool — the same pattern services/email_service.py's
    notify_new_bird already uses for its own recipient filtering, e.g.
    respecting notify_new_bird). Best-effort per-subscription/token; one
    failure doesn't stop the others from being attempted.
    """
    from ..models import PushSubscription, User

    url = app_path(url)
    # The Notifications tab keeps everything sent, delivered or not.
    if record_inbox:
        from .notification_inbox import record
        record(db, title, body, url=url, kind=tag, user_filter=user_filter, data=data)

    q = db.query(PushSubscription)
    if user_filter is not None:
        allowed_user_ids = {u.id for u in db.query(User).all() if user_filter(u)}
        if signed_in_only:   # e.g. admin-only alerts: skip subscriptions with no account
            q = q.filter(PushSubscription.user_id.in_(allowed_user_ids))
        else:
            q = q.filter(
                (PushSubscription.user_id.in_(allowed_user_ids)) | (PushSubscription.user_id.is_(None))
            )
    subscriptions = q.all()

    sent = 0
    for sub in subscriptions:
        if send_push_to_subscription(db, sub, title, body, url=url, tag=tag):
            sent += 1

    try:
        from .apns_push import send_apns_to_all
        sent += send_apns_to_all(db, title, body, url=url, user_filter=user_filter, signed_in_only=signed_in_only)
    except Exception as e:
        logger.warning("APNs portion of send_push_to_all failed (Web Push portion still sent): %s", e)

    return sent


def digest_details(stats) -> dict:
    """What a digest notification keeps: the day's totals and every species
    heard, most detections first, with new species flagged."""
    from .email_service import _hour_label
    new = set(stats["new_species"])
    return {
        "date": stats["yesterday"].isoformat(),
        "day": stats["day_str"],
        "partial": bool(stats.get("partial")),
        "recordings": stats["total_recs"],
        "detections": stats["total_dets"],
        "species_count": stats["unique_species"],
        "busiest_hour": _hour_label(stats["busiest_hour"]) if stats["busiest_hour"] is not None else None,
        "new_species": stats["new_species"],
        "species": [{"name": n, "count": c, "best": round(stats["best_conf"].get(n, 0), 2),
                     "scientific": stats["scientific"].get(n), "new": n in new}
                    for n, c in stats["species_counts"].most_common()],
    }


def send_daily_digest_push(db, server_url: str = "", day=None) -> int:
    """
    Push version of the email daily digest for `day` (default yesterday),
    from the same numbers (email_service.compute_day_stats). Its own opt-in
    (User.notify_daily_digest_push). Tapping it opens the app's
    digest page for that day; the inbox row keeps a summary
    (digest_details).
    Returns the number of successful sends (0 on a quiet day).
    """
    from .email_service import compute_day_stats, compute_yesterday_stats

    stats = compute_day_stats(db, day) if day else compute_yesterday_stats(db)
    if stats is None:
        return 0  # Skip quiet days — same real decision the email digest makes

    top_names = [name for name, _ in stats["top_species"][:3]]
    if len(stats["species_counts"]) > 3:
        species_line = ", ".join(top_names) + f", +{len(stats['species_counts']) - 3} more"
    else:
        species_line = ", ".join(top_names) if top_names else "no species logged"

    title = f"Chirp Digest — {stats['day_str']}"
    so_far = " so far" if stats.get("partial") else ""
    body = (
        f"{stats['total_recs']} recordings, {stats['unique_species']} species{so_far}. "
        f"Top: {species_line}"
    )

    sent = send_push_to_all(
        db, title, body,
        url=f"/digest?date={stats['yesterday'].isoformat()}",
        tag="daily-digest",
        user_filter=lambda u: getattr(u, "notify_daily_digest_push", False),
        data=digest_details(stats),
    )
    if sent:
        logger.info("Daily digest push sent to %d recipient(s)", sent)
    return sent
