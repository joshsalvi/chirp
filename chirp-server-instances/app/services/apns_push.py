"""
Native iOS push via Apple Push Notification service (APNs) — the
counterpart to push_notifications.py's Web Push (VAPID) support, for
the Capacitor-wrapped native app rather than the PWA. Genuinely
different mechanisms under the hood (see ApnsDeviceToken's own
docstring in models.py) despite both surfacing as "a push notification"
to the person using the app.

Uses token-based (JWT) authentication with a .p8 auth key from Apple
Developer's console, not the older per-app push certificate — token
auth doesn't expire yearly and one key works across every app a
developer account owns, which matters here since self-hosters
generating their own key shouldn't have to repeat that process
annually just to keep push working.

APNs requires HTTP/2 specifically (this is Apple's own hard requirement,
not a Chirp choice) — httpx supports it via the optional `h2` package
(see requirements.txt).
"""
import json
import logging
import time

import httpx
# python-jose (already used for sign-in tokens) signs ES256; PyJWT, which this
# imported before, isn't installed, so every native push failed on import.
from jose import jwt as jose_jwt

logger = logging.getLogger("chirp.apns_push")

# APNs JWTs are valid for up to 60 minutes; Apple explicitly asks
# clients not to generate a fresh one per-request (their docs note
# generating too many will get rate-limited). Cached here per
# (team_id, key_id) pair, regenerated a few minutes before the real
# expiry rather than exactly at it, so a send in flight right at the
# boundary doesn't get a token that expires mid-request.
_jwt_cache = {}  # {(team_id, key_id): (token, generated_at_epoch)}
_JWT_MAX_AGE_S = 50 * 60  # regenerate after 50 minutes, under Apple's 60-minute ceiling


def _get_apns_jwt(team_id: str, key_id: str, auth_key_pem: str) -> str:
    cache_key = (team_id, key_id)
    cached = _jwt_cache.get(cache_key)
    if cached and (time.time() - cached[1]) < _JWT_MAX_AGE_S:
        return cached[0]

    token = jose_jwt.encode(
        {"iss": team_id, "iat": int(time.time())},
        auth_key_pem.strip(),
        algorithm="ES256",
        headers={"kid": key_id},
    )
    _jwt_cache[cache_key] = (token, time.time())
    return token


DEFAULT_RELAY_URL = "https://ourchirp.com"


def _apns_configured(s) -> bool:
    return bool(s and s.apns_team_id and s.apns_key_id and s.apns_bundle_id and s.apns_auth_key)


def platform_credentials():
    """The server-wide key from CHIRP_APNS_* (config.py), or None."""
    from ..config import settings as cfg
    key = cfg.apns_auth_key
    if not key and cfg.apns_auth_key_file:
        try:
            with open(cfg.apns_auth_key_file) as f:
                key = f.read()
        except OSError as e:
            logger.warning("CHIRP_APNS_AUTH_KEY_FILE unreadable: %s", e)
    if cfg.apns_team_id and cfg.apns_key_id and cfg.apns_bundle_id and key:
        return {"team_id": cfg.apns_team_id, "key_id": cfg.apns_key_id, "bundle_id": cfg.apns_bundle_id,
                "auth_key": key, "production": bool(cfg.apns_production)}
    return None


def _credentials(s):
    """This site's own key first, then the server-wide one."""
    if _apns_configured(s):
        return {"team_id": s.apns_team_id, "key_id": s.apns_key_id, "bundle_id": s.apns_bundle_id,
                "auth_key": s.apns_auth_key, "production": s.apns_production is not False}
    return platform_credentials()


def _relay(s):
    """(url, token) when this server sends through a push relay, else None."""
    token = (getattr(s, "push_relay_token", None) or "").strip() if s else ""
    if not token:
        return None
    url = (getattr(s, "push_relay_url", None) or DEFAULT_RELAY_URL).strip().rstrip("/")
    return url, token


def push_route(s) -> str:
    """'site', 'server', 'relay' or '' (no iPhone push)."""
    if _apns_configured(s):
        return "site"
    if platform_credentials():
        return "server"
    if _relay(s):
        return "relay"
    return ""


def deliver(creds: dict, device_token: str, payload: dict):
    """Sends one payload with the given key. Returns (ok, detail, dead) where
    dead is Apple's reason when the token no longer reaches an install."""
    try:
        token = _get_apns_jwt(creds["team_id"], creds["key_id"], creds["auth_key"])
    except Exception as e:
        return False, f"Failed to generate APNs auth token: {e}", None
    # TestFlight/App Store builds get production tokens, builds installed from
    # Xcode get sandbox tokens. Try the configured environment first and the
    # other one if Apple says the token isn't valid there, so one server can
    # reach both kinds of install. A token is dropped only if both reject it.
    hosts = ["api.push.apple.com", "api.sandbox.push.apple.com"]
    if not creds.get("production", True):
        hosts.reverse()
    last = None
    try:
        with httpx.Client(http2=True) as client:
            for host in hosts:
                resp = client.post(
                    f"https://{host}/3/device/{device_token}",
                    headers={
                        "authorization": f"bearer {token}",
                        "apns-topic": creds["bundle_id"],
                        "apns-push-type": "alert",
                        "apns-priority": "10",
                    },
                    content=json.dumps(payload),
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    return True, None, None
                try:
                    reason = resp.json().get("reason", "")
                except Exception:
                    reason = resp.text
                last = (resp.status_code, reason)
                if resp.status_code == 410 and reason == "Unregistered":
                    return False, f"HTTP 410: {reason}", reason      # app removed from that phone
                if not (resp.status_code == 400 and reason == "BadDeviceToken"):
                    break                           # a real error; the other host won't differ
        if last == (400, "BadDeviceToken"):
            return False, "HTTP 400: BadDeviceToken", "BadDeviceToken"
        return False, (f"HTTP {last[0]}: {last[1]}" if last else "no response"), None
    except Exception as e:
        return False, str(e), None


def _deliver_via_relay(relay, device_token: str, payload: dict, server_url: str = ""):
    url, token = relay
    try:
        r = httpx.post(f"{url}/api/v1/push-relay/send",
                       headers={"Authorization": f"Bearer {token}"},
                       json={"device_token": device_token, "payload": payload, "server": server_url},
                       timeout=15.0)
        try:
            j = r.json()
        except Exception:
            j = {}
        if r.status_code == 200:
            return bool(j.get("ok")), j.get("error"), j.get("dead")
        return False, f"Relay HTTP {r.status_code}: {j.get('detail') or r.text[:200]}", None
    except Exception as e:
        return False, f"Relay unreachable: {e}", None


def send_apns_push(db, device_token: str, title: str, body: str, url: str = None,
                    s=None, token_row=None) -> "ApnsResult":
    """
    Sends one push to one device token, with this site's own key, the
    server-wide key (CHIRP_APNS_*) or, for a self-hosted server with neither,
    through the push relay (Settings → Alerts & Email → Push relay token).
    Returns an ApnsResult — truthy on success, carrying `.error` on failure.
    A 400 BadDeviceToken or 410 Unregistered response means the token is
    dead (app uninstalled, or Apple rotated it); that row gets deleted here,
    mirroring how push_notifications.py handles an expired Web Push
    subscription.

    s / token_row: the caller's already-fetched AppSettings and
    ApnsDeviceToken rows, if it has them (send_apns_to_all passes both).
    """
    from ..models import AppSettings, ApnsDeviceToken

    if s is None:
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    payload = {"aps": {"alert": {"title": title, "body": body}, "sound": "default"}}
    if url:
        from .push_notifications import app_path
        payload["url"] = app_path(url)

    creds = _credentials(s)
    relay = None if creds else _relay(s)
    if creds:
        ok, detail, dead = deliver(creds, device_token, payload)
    elif relay:
        ok, detail, dead = _deliver_via_relay(relay, device_token, payload, getattr(s, "server_url", "") or "")
    else:
        return ApnsResult(False, "iPhone push isn't set up (Settings → Alerts & Email)")

    def _row():
        return token_row if token_row is not None else \
            db.query(ApnsDeviceToken).filter(ApnsDeviceToken.device_token == device_token).first()

    if ok:
        from datetime import datetime as _dt
        row = _row()
        if row:
            row.last_used_at = _dt.utcnow()
            db.commit()
        return ApnsResult(True, None)
    if dead:
        logger.info("APNs device token dead (%s), removing: %s...", dead, device_token[:12])
        row = _row()
        if row:
            db.delete(row)
            db.commit()
        return ApnsResult(False, f"Device token expired/invalid ({dead}) — removed")
    logger.warning("APNs send failed: %s", detail)
    return ApnsResult(False, detail)


class ApnsResult:
    """Same truthy/falsy-with-error-detail shape as push_notifications.py's PushResult, deliberately — one consistent pattern for both push mechanisms' results."""
    def __init__(self, ok: bool, error):
        self.ok = ok
        self.error = error

    def __bool__(self):
        return self.ok


def send_apns_to_all(db, title: str, body: str, url: str = None, user_filter=None,
                     signed_in_only: bool = False) -> int:
    """
    Sends to every registered native device token, optionally filtered
    to specific users — same signature/behavior shape as
    push_notifications.py's send_push_to_all, so a caller notifying
    "everyone" doesn't need two near-identical call sites, one per push
    mechanism (see send_push_to_all's own updated docstring, which now
    calls both this and the Web Push version together).
    """
    from ..models import AppSettings, ApnsDeviceToken, User

    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if not push_route(s):
        return 0  # silently a no-op when unconfigured, same convention as an unset AI provider elsewhere in this codebase

    q = db.query(ApnsDeviceToken)
    if user_filter is not None:
        allowed_user_ids = {u.id for u in db.query(User).all() if user_filter(u)}
        if signed_in_only:
            q = q.filter(ApnsDeviceToken.user_id.in_(allowed_user_ids))
        else:
            q = q.filter(
                (ApnsDeviceToken.user_id.in_(allowed_user_ids)) | (ApnsDeviceToken.user_id.is_(None))
            )
    tokens = q.all()

    sent = 0
    for row in tokens:
        # Passing the already-fetched s and row avoids re-querying the
        # single-row AppSettings table and this exact ApnsDeviceToken
        # row once per device — previously a batch of N devices meant
        # N+1 redundant AppSettings queries and N redundant
        # ApnsDeviceToken re-fetches for what's fundamentally the same
        # handful of rows throughout one notification send.
        if send_apns_push(db, row.device_token, title, body, url=url, s=s, token_row=row):
            sent += 1
    return sent
