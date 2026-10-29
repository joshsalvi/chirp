"""
Questions, problem reports, feature ideas and TestFlight requests from
support.html, the About page and the app (My Profile → Help & feedback). Same file in both forks.

  POST /api/v1/support            public, rate-limited per IP; a signed-in
                                  sender is identified from their token
  GET  /api/v1/admin/support      global admin (multi-site server only)
  PATCH/DELETE /api/v1/admin/support/{id}

Each message is emailed to the server's admins: global admins on a
multi-site server, the site's admin email otherwise. The multi-site server
also keeps them for Global Admin → Requests.
"""
import logging
import re
import time
from collections import defaultdict, deque
from html import escape
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger("chirp.support")
router = APIRouter(tags=["support"])

KINDS = {"question": "Question", "problem": "Problem", "feature": "Feature idea",
         "testflight": "TestFlight request", "other": "Other"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_RATE_MAX, _RATE_WINDOW_S = 5, 3600
_recent = defaultdict(deque)

try:   # multi-site server (chirp-server-instances)
    from ..registry_db import RegistrySessionLocal
    from ..registry_models import Instance, SupportMessage
    MULTI = True
except ImportError:
    MULTI = False


class SupportIn(BaseModel):
    kind: str = "question"
    name: Optional[str] = None
    email: Optional[str] = None
    message: str
    page: Optional[str] = None
    website: Optional[str] = None      # honeypot


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else "") or (request.client.host if request.client else "")


def _rate_limit(ip: str):
    now, q = time.time(), _recent[ip]
    while q and now - q[0] > _RATE_WINDOW_S:
        q.popleft()
    if len(q) >= _RATE_MAX:
        raise HTTPException(429, "Too many messages from this address. Try again in an hour.")
    q.append(now)


def _sender(request: Request):
    """(username, site name) for a signed-in sender, else (None, None)."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None, None
    from .auth import verify_token
    payload = verify_token(auth[7:].strip())
    if not payload:
        return None, None
    site = None
    try:
        if MULTI and payload.get("active_instance_id"):
            reg = RegistrySessionLocal()
            try:
                inst = reg.query(Instance).filter(Instance.id == payload["active_instance_id"]).first()
                site = inst.name if inst else None
            finally:
                reg.close()
        elif not MULTI:
            from ..database import SessionLocal
            from ..models import AppSettings
            with SessionLocal() as db:
                s = db.query(AppSettings).first()
                site = getattr(s, "location_name", None) if s else None
    except Exception:
        pass
    return payload.get("sub"), site


def _email(subject: str, html: str, text: str) -> bool:
    if MULTI:
        from ..services.platform_mail import global_admin_emails, send_platform_email
        to = global_admin_emails()
        return bool(to) and send_platform_email(to, subject, "Chirp support", subject, html, text)
    from ..database import SessionLocal
    from ..services.email_service import _get_smtp_config, _send, _wrap_html
    with SessionLocal() as db:
        cfg = _get_smtp_config(db)
    if not cfg or not cfg.get("admin_email"):
        return False
    return _send(cfg, cfg["admin_email"], subject, _wrap_html("Chirp support", subject, html), text)


@router.post("", status_code=201)
def submit(body: SupportIn, request: Request):
    if body.website:
        return {"ok": True}
    ip = _client_ip(request)
    _rate_limit(ip)
    kind = body.kind if body.kind in KINDS else "other"
    message = (body.message or "").strip()
    if len(message) < 5:
        raise HTTPException(400, "Write a few words so we know how to help.")
    message = message[:4000]
    email = (body.email or "").strip()[:200] or None
    if email and not EMAIL_RE.match(email):
        raise HTTPException(400, "Enter a valid email address, or leave it blank.")
    name = (body.name or "").strip()[:120] or None
    page = (body.page or "").strip()[:200] or None
    username, site = _sender(request)
    if kind == "testflight" and not email:
        raise HTTPException(400, "Add the email of your Apple Account so we can send the TestFlight invite.")
    if not email and not username:
        raise HTTPException(400, "Add your email so we can reply.")

    if MULTI:
        reg = RegistrySessionLocal()
        try:
            reg.add(SupportMessage(kind=kind, name=name, email=email, username=username, site=site,
                                   page=page, message=message, ip=ip))
            reg.commit()
        finally:
            reg.close()

    who = name or username or email
    facts = [("From", who), ("Email", email), ("Account", username), ("Site", site), ("Page", page)]
    rows = "".join(f"<tr><td style='padding:3px 12px 3px 0;color:#888'>{k}</td><td>{escape(v)}</td></tr>"
                   for k, v in facts if v)
    subject = f"Chirp {KINDS[kind].lower()}: {message[:60]}{'…' if len(message) > 60 else ''}"
    html = (f"<table>{rows}</table><p style='white-space:pre-wrap'>{escape(message)}</p>"
            + (f"<p>Reply to <a href='mailto:{escape(email)}'>{escape(email)}</a>.</p>" if email else ""))
    text = "\n".join(f"{k}: {v}" for k, v in facts if v) + f"\n\n{message}\n"
    try:
        sent = _email(subject, html, text)
    except Exception as e:
        logger.warning("Support email failed: %s", e)
        sent = False
    logger.info("Support %s from %s (emailed=%s)", kind, who, sent)
    if not sent and not MULTI:
        raise HTTPException(503, "Couldn't send right now. Please try again later.")
    return {"ok": True}


# ── Global Admin (multi-site server) ─────────────────────────────────────

admin_router = APIRouter(tags=["admin"])

if MULTI:
    from .admin_panel import get_current_global_admin

    def _out(m):
        return {k: getattr(m, k) for k in ("id", "created_at", "kind", "name", "email", "username",
                                           "site", "page", "message", "done")}

    @admin_router.get("")
    def list_messages(admin=Depends(get_current_global_admin)):
        reg = RegistrySessionLocal()
        try:
            rows = reg.query(SupportMessage).order_by(SupportMessage.created_at.desc()).limit(300).all()
            return [_out(m) for m in rows]
        finally:
            reg.close()

    class DoneIn(BaseModel):
        done: bool

    @admin_router.patch("/{message_id}")
    def mark(message_id: str, body: DoneIn, admin=Depends(get_current_global_admin)):
        reg = RegistrySessionLocal()
        try:
            m = reg.query(SupportMessage).filter(SupportMessage.id == message_id).first()
            if not m:
                raise HTTPException(404, "Message not found")
            m.done = body.done
            reg.commit()
            return _out(m)
        finally:
            reg.close()

    @admin_router.delete("/{message_id}", status_code=204)
    def remove(message_id: str, admin=Depends(get_current_global_admin)):
        reg = RegistrySessionLocal()
        try:
            m = reg.query(SupportMessage).filter(SupportMessage.id == message_id).first()
            if m:
                reg.delete(m)
                reg.commit()
        finally:
            reg.close()
