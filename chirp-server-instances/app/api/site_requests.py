"""
Sign-up requests from the public About page, and their approval.

  POST /api/v1/site-requests                      public; rate-limited per IP
  GET  /api/v1/admin/site-requests                global admin
  POST /api/v1/admin/site-requests/{id}/approve   global admin
  POST /api/v1/admin/site-requests/{id}/deny      global admin
  DELETE /api/v1/admin/site-requests/{id}         global admin

kind "hosted": someone building a station who wants a site on this server.
Approval creates their account (with the password they chose), the site,
a device key, and emails sign-in and device setup instructions.

kind "relay": someone running their own Chirp server who wants iPhone
pushes. Approval issues a push relay token (api/push_relay.py) and emails it.
"""
import logging
import re
import secrets
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime
from html import escape
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..registry_db import RegistrySessionLocal
from ..registry_models import GlobalUser, Instance, Membership, SiteRequest
from .admin_panel import get_current_global_admin

logger = logging.getLogger("chirp.site_requests")
router = APIRouter(tags=["site-requests"])
admin_router = APIRouter(tags=["admin"])

GITHUB_URL = "https://github.com/joshsalvi/chirp"
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_RATE_WINDOW_S = 3600
_RATE_MAX = 5
_MAX_PENDING = 200
_recent = defaultdict(deque)


def _rate_limit(ip: str):
    now = time.time()
    q = _recent[ip]
    while q and now - q[0] > _RATE_WINDOW_S:
        q.popleft()
    if len(q) >= _RATE_MAX:
        raise HTTPException(status_code=429, detail="Too many requests from this address. Try again in an hour.")
    q.append(now)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else "") or (request.client.host if request.client else "")


class SiteRequestIn(BaseModel):
    kind: str = "hosted"
    full_name: str
    email: str
    site_name: str
    username: Optional[str] = None
    password: Optional[str] = None
    location_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone: Optional[str] = None
    hardware: Optional[str] = None
    message: Optional[str] = None
    server_url: Optional[str] = None
    website: Optional[str] = None      # honeypot: people never see or fill it


def _clean(v: Optional[str], limit: int) -> Optional[str]:
    v = (v or "").strip()
    return v[:limit] if v else None


@router.post("", status_code=201)
def submit_request(body: SiteRequestIn, request: Request):
    if body.website:
        return {"ok": True}                       # a bot; pretend it worked
    _rate_limit(_client_ip(request))
    kind = body.kind if body.kind in ("hosted", "relay") else None
    if not kind:
        raise HTTPException(400, "Choose a hosted site or a push relay.")
    full_name, email, site_name = _clean(body.full_name, 120), _clean(body.email, 200), _clean(body.site_name, 80)
    if not full_name or not site_name:
        raise HTTPException(400, "Name and site name are required.")
    if not email or not EMAIL_RE.match(email):
        raise HTTPException(400, "Enter a valid email address.")
    if body.latitude is not None and not -90 <= body.latitude <= 90:
        raise HTTPException(400, "Latitude must be between -90 and 90.")
    if body.longitude is not None and not -180 <= body.longitude <= 180:
        raise HTTPException(400, "Longitude must be between -180 and 180.")
    tz = _clean(body.timezone, 64)
    if tz:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(tz)
        except Exception:
            tz = None

    reg = RegistrySessionLocal()
    try:
        if reg.query(SiteRequest).filter(SiteRequest.status == "pending").count() >= _MAX_PENDING:
            raise HTTPException(503, "Requests are paused for now. Please try again later.")
        row = SiteRequest(kind=kind, full_name=full_name, email=email, site_name=site_name,
                          location_name=_clean(body.location_name, 120), latitude=body.latitude,
                          longitude=body.longitude, timezone=tz, hardware=_clean(body.hardware, 1000),
                          message=_clean(body.message, 2000), ip=_client_ip(request))
        if kind == "hosted":
            username = (body.username or "").strip()
            if not USERNAME_RE.match(username):
                raise HTTPException(400, "Username: 3–32 letters, numbers, dots, dashes or underscores.")
            if not body.password or len(body.password) < 8:
                raise HTTPException(400, "Password must be at least 8 characters.")
            if _username_taken(reg, username):
                raise HTTPException(409, "That username is taken. Choose another.")
            from .auth import _get_crypt
            row.username, row.hashed_pw = username, _get_crypt().hash(body.password)
        else:
            url = (body.server_url or "").strip().rstrip("/")
            if not re.match(r"^https?://[^\s/]+", url):
                raise HTTPException(400, "Enter your server's address, e.g. https://chirp.example.com")
            row.server_url = url[:200]
        reg.add(row)
        reg.commit()
        reg.refresh(row)
        _notify_admins(row, request)
        logger.info("Site request %s (%s) from %s", row.id, kind, email)
        return {"ok": True, "id": row.id}
    finally:
        reg.close()


def _username_taken(reg, username: str, exclude_id: Optional[str] = None) -> bool:
    if reg.query(GlobalUser).filter(GlobalUser.username.ilike(username)).first():
        return True
    q = reg.query(SiteRequest).filter(SiteRequest.status == "pending", SiteRequest.username.ilike(username))
    if exclude_id:
        q = q.filter(SiteRequest.id != exclude_id)
    return q.first() is not None


def _notify_admins(row: SiteRequest, request: Request):
    from ..services.platform_mail import global_admin_emails, public_url, send_platform_email
    to = global_admin_emails()
    if not to:
        return
    base = public_url(request)
    what = "a hosted site" if row.kind == "hosted" else "a push relay token"
    lines = [("Name", row.full_name), ("Email", row.email), ("Site", row.site_name),
             ("Username", row.username), ("Server", row.server_url), ("Location", row.location_name),
             ("Hardware", row.hardware), ("Message", row.message)]
    rows = "".join(f"<tr><td style='padding:4px 12px 4px 0;color:#888'>{k}</td><td>{escape(str(v))}</td></tr>"
                   for k, v in lines if v)
    text = "\n".join(f"{k}: {v}" for k, v in lines if v)
    try:
        send_platform_email(to, f"Chirp: {row.full_name} requests {what}", "New Chirp request",
                            f"{row.full_name} requests {what}",
                            f"<p>{escape(row.full_name)} requests {what}.</p><table>{rows}</table>",
                            text + f"\n\nReview: {base}/global-admin", cta_url=f"{base}/global-admin",
                            cta_label="Review request", server_url=base)
    except Exception as e:
        logger.warning("Admin notification for request %s failed: %s", row.id, e)


# ── Admin ────────────────────────────────────────────────────────────────

def _out(r: SiteRequest) -> dict:
    return {k: getattr(r, k) for k in (
        "id", "created_at", "status", "kind", "full_name", "email", "username", "site_name", "server_url",
        "location_name", "latitude", "longitude", "timezone", "hardware", "message", "decided_at",
        "decided_by", "deny_reason", "instance_id", "relay_server_id", "emailed_at")}


@admin_router.get("")
def list_requests(status: Optional[str] = None, admin: GlobalUser = Depends(get_current_global_admin)):
    reg = RegistrySessionLocal()
    try:
        q = reg.query(SiteRequest)
        if status:
            q = q.filter(SiteRequest.status == status)
        return [_out(r) for r in q.order_by(SiteRequest.created_at.desc()).limit(500).all()]
    finally:
        reg.close()


def _get(reg, request_id: str) -> SiteRequest:
    row = reg.query(SiteRequest).filter(SiteRequest.id == request_id).first()
    if not row:
        raise HTTPException(404, "Request not found")
    return row


def create_hosted_site(reg, row: SiteRequest, base_url: str) -> dict:
    """Account, site, admin membership, local user, settings and a device key."""
    from sqlalchemy.orm import sessionmaker
    from ..instance_registry import get_engine_for_instance, provision_instance_database
    from ..models import AppSettings, User

    if _username_taken(reg, row.username, exclude_id=row.id):
        raise HTTPException(409, f"Username {row.username} was taken since the request. Deny it and ask them to apply again.")
    user = GlobalUser(username=row.username, email=row.email, hashed_pw=row.hashed_pw)
    reg.add(user)
    reg.flush()
    db_filename = f"{user.id[:8]}_{int(datetime.utcnow().timestamp())}.db"
    instance = Instance(name=row.site_name, location_name=row.location_name,
                        db_filename=db_filename, created_by_user_id=user.id)
    reg.add(instance)
    reg.flush()
    provision_instance_database(db_filename)
    reg.add(Membership(user_id=user.id, instance_id=instance.id, role="admin"))

    key = {"id": str(uuid.uuid4()), "name": f"{row.site_name} station",
           "key": "chirp-" + secrets.token_urlsafe(32), "created_at": datetime.utcnow().isoformat()}
    db = sessionmaker(bind=get_engine_for_instance(db_filename))()
    try:
        db.add(User(username=row.username, email=row.email, hashed_pw=row.hashed_pw, role="admin"))
        s = db.query(AppSettings).filter(AppSettings.id == 1).first() or AppSettings(id=1, auth_enabled=True)
        s.latitude, s.longitude = row.latitude, row.longitude
        s.location_name = row.location_name
        if row.timezone:
            s.timezone = row.timezone
        s.server_url = base_url
        s.admin_email = row.email
        s.device_api_keys = [key]
        db.add(s)
        db.commit()
    finally:
        db.close()
    row.instance_id = instance.id
    return {"instance": instance, "device_key": key["key"]}


def hosted_email(row: SiteRequest, base: str, invite_code: str, device_key: str):
    upload = f"{base}/api/v1/recordings/upload"
    config = (f"upload:\n  enabled: true\n  server_url: \"{upload}\"\n  api_key: \"{device_key}\"\n\n"
              f"server_sync:\n  enabled: true\n  server_url: \"{base}\"\n  api_key: \"{device_key}\"")
    steps = [
        f"Sign in at {base} as <b>{escape(row.username)}</b> with the password you chose.",
        f"Get the device software: <a href='{GITHUB_URL}'>{GITHUB_URL}</a> (folder <code>chirp-device</code>).",
        "On a Raspberry Pi 5 with a USB microphone: <code>git clone</code> the repository, "
        "<code>cd chirp/chirp-device</code>, then <code>./install.sh</code>.",
        "Edit <code>config.yaml</code> and set the two sections below.",
        "Run <code>python main.py --test-detection</code>, then <code>sudo systemctl enable --now chirp</code>.",
        "Recordings appear in your site within a minute of the first bird.",
    ]
    html = (f"<p>Hi {escape(row.full_name.split()[0])},</p>"
            f"<p>Your Chirp site <b>{escape(row.site_name)}</b> is ready.</p><ol>"
            + "".join(f"<li style='margin-bottom:6px'>{s}</li>" for s in steps) + "</ol>"
            f"<p style='margin-bottom:4px'><b>config.yaml</b></p>"
            f"<pre style='background:#f4f1ea;padding:12px;border-radius:8px;font-size:12px;white-space:pre-wrap;word-break:break-all'>{escape(config)}</pre>"
            f"<p>Keep the API key private: it lets a device upload to your site. You can make new keys "
            f"or revoke this one in Settings → Devices.</p>"
            f"<p>Invite family or friends as viewers with the code <b>{escape(invite_code)}</b> "
            f"(Create account → invite code).</p>"
            f"<p>On iPhone, open {base} in Safari and choose Share → Add to Home Screen, or use the Chirp app.</p>")
    text = (f"Hi {row.full_name.split()[0]},\n\nYour Chirp site {row.site_name} is ready.\n\n"
            f"1. Sign in at {base} as {row.username} with the password you chose.\n"
            f"2. Device software: {GITHUB_URL} (folder chirp-device).\n"
            "3. On a Raspberry Pi 5 with a USB microphone: git clone, cd chirp/chirp-device, ./install.sh\n"
            "4. Edit config.yaml:\n\n" + config + "\n\n"
            "5. python main.py --test-detection, then sudo systemctl enable --now chirp\n\n"
            "Keep the API key private. Manage keys in Settings → Devices.\n"
            f"Invite code for viewers: {invite_code}\n")
    return "Your Chirp site is ready", html, text


def relay_email(row: SiteRequest, base: str, token: str):
    html = (f"<p>Hi {escape(row.full_name.split()[0])},</p>"
            f"<p>Your Chirp server <b>{escape(row.site_name)}</b> can now send iPhone notifications "
            f"through {escape(base)}.</p><ol>"
            "<li>Update your server to Chirp 0.5.12.p or later.</li>"
            "<li>Open Settings → Alerts &amp; Email → iPhone push.</li>"
            f"<li>Paste this relay token and save:</li></ol>"
            f"<pre style='background:#f4f1ea;padding:12px;border-radius:8px;font-size:12px;word-break:break-all'>{escape(token)}</pre>"
            "<p>Then use “Send test” on that card. Keep the token private; ask us to revoke it if it leaks.</p>")
    text = (f"Hi {row.full_name.split()[0]},\n\nYour Chirp server {row.site_name} can now send iPhone "
            f"notifications through {base}.\n\n1. Update to Chirp 0.5.12.p or later.\n"
            "2. Settings → Alerts & Email → iPhone push.\n3. Paste this relay token and save:\n\n"
            f"{token}\n\nKeep the token private.\n")
    return "Your Chirp push relay token", html, text


@admin_router.post("/{request_id}/approve")
def approve(request_id: str, request: Request, admin: GlobalUser = Depends(get_current_global_admin)):
    from ..services.platform_mail import public_url, send_platform_email
    from .push_relay import issue_token
    base = public_url(request)
    reg = RegistrySessionLocal()
    try:
        row = _get(reg, request_id)
        if row.status != "pending":
            raise HTTPException(409, f"Request is already {row.status}.")
        if row.kind == "hosted":
            made = create_hosted_site(reg, row, base)
            subject, html, text = hosted_email(row, base, made["instance"].invite_code, made["device_key"])
            cta, label = base + "/login", "Sign in"
        else:
            server, token = issue_token(reg, row.site_name, row.email, row.server_url)
            row.relay_server_id = server.id
            subject, html, text = relay_email(row, base, token)
            cta, label = "#", ""
        row.status, row.decided_at, row.decided_by = "approved", datetime.utcnow(), admin.username
        reg.commit()
        sent = send_platform_email(row.email, subject, subject, subject, html, text,
                                   cta_url=cta, cta_label=label, server_url=base)
        if sent:
            row.emailed_at = datetime.utcnow()
            reg.commit()
        logger.info("Approved site request %s (%s) by %s; emailed=%s", row.id, row.kind, admin.username, sent)
        # The instructions come back once so they can be passed on by hand
        # when email isn't set up. The token/key isn't stored in plain text.
        return {**_out(row), "email_sent": sent, "instructions": text}
    except Exception:
        reg.rollback()
        raise
    finally:
        reg.close()


class DenyIn(BaseModel):
    reason: Optional[str] = None
    notify: bool = True


@admin_router.post("/{request_id}/deny")
def deny(request_id: str, body: DenyIn, request: Request, admin: GlobalUser = Depends(get_current_global_admin)):
    from ..services.platform_mail import public_url, send_platform_email
    reg = RegistrySessionLocal()
    try:
        row = _get(reg, request_id)
        if row.status != "pending":
            raise HTTPException(409, f"Request is already {row.status}.")
        row.status, row.decided_at, row.decided_by = "denied", datetime.utcnow(), admin.username
        row.deny_reason = _clean(body.reason, 1000)
        row.hashed_pw = None
        reg.commit()
        sent = False
        if body.notify:
            reason = f"\n\n{row.deny_reason}" if row.deny_reason else ""
            sent = send_platform_email(
                row.email, "About your Chirp request", "About your Chirp request", "Your Chirp request",
                f"<p>Hi {escape(row.full_name.split()[0])},</p><p>We can't set up <b>{escape(row.site_name)}</b> "
                f"right now.</p>" + (f"<p>{escape(row.deny_reason)}</p>" if row.deny_reason else "")
                + f"<p>You can still run your own Chirp server: <a href='{GITHUB_URL}'>{GITHUB_URL}</a>.</p>",
                f"Hi {row.full_name.split()[0]},\n\nWe can't set up {row.site_name} right now.{reason}\n\n"
                f"You can still run your own Chirp server: {GITHUB_URL}\n", server_url=public_url(request))
        return {**_out(row), "email_sent": sent}
    finally:
        reg.close()


@admin_router.delete("/{request_id}", status_code=204)
def delete_request(request_id: str, admin: GlobalUser = Depends(get_current_global_admin)):
    reg = RegistrySessionLocal()
    try:
        reg.delete(_get(reg, request_id))
        reg.commit()
    finally:
        reg.close()
