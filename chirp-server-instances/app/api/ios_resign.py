"""
Events from the optional iOS re-sign service (ios-resign/ in the stack):
it posts here when Apple needs a two-factor code or a re-sign fails, and
the admin gets an email with a link to the service's page.

Authenticated with the stack's CHIRP_DEVICE_API_KEY (X-API-Key), the same
key the service is given in docker-compose.yml.
"""
import hmac
import logging
import time
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from ..config import settings

router = APIRouter()
logger = logging.getLogger("chirp.ios_resign")
_last_sent: dict = {}
REPEAT_S = 600     # the same event for the same phone at most every 10 minutes


class ResignEvent(BaseModel):
    event: str                      # needs_code | failed | signed
    device: str = ""
    error: str = ""
    page: str = ""


def _sessions():
    """(label, session) for every database whose admin should hear about it:
    each instance (multi-tenant fork), else the one database."""
    found = False
    try:
        from ..instance_registry import iter_instance_sessions
        for inst, db in iter_instance_sessions():
            found = True
            yield inst.name, db
    except ImportError:
        pass
    except Exception as e:
        logger.debug("Instance list unavailable: %s", e)
    if found:
        return
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        yield "", db
    finally:
        db.close()


@router.post("/event")
def resign_event(body: ResignEvent, x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.device_api_key):
        raise HTTPException(status_code=401, detail="Bad or missing X-API-Key")
    logger.info("iOS re-sign: %s %s %s", body.event, body.device, body.error)
    if body.event not in ("needs_code", "failed"):
        return {"emailed": 0}
    key = (body.event, body.device)
    if time.time() - _last_sent.get(key, 0) < REPEAT_S:
        return {"emailed": 0, "throttled": True}
    _last_sent[key] = time.time()

    from ..services import email_service as es
    from ..services import email_theme as t
    page = body.page or ""
    phone = t.esc(body.device or "your iPhone")
    if body.event == "needs_code":
        title, subject = "Two-factor code needed", f"[Chirp] Apple needs a code to re-sign Chirp on {body.device}"
        html_body = (t.info_box(f"Apple sent a six-digit code to your devices so the server can re-sign Chirp on "
                                f"<b>{phone}</b>. Open the re-sign page and type it in within 15 minutes; "
                                "after that the attempt stops and the next one asks again."))
        cta = "Enter the code"
    else:
        title, subject = "Re-sign failed", f"[Chirp] Couldn't re-sign Chirp on {body.device}"
        html_body = (t.info_box(f"Re-signing Chirp on <b>{phone}</b> failed:<br><code>{t.esc(body.error)[:400]}</code>"
                                "<br><br>It tries again at the next check while the phone is on the network. "
                                "The app keeps working until its 7 days run out.", t.ACCENT))
        cta = "Open the re-sign page"
    sent = 0
    seen = set()
    for _label, db in _sessions():
        cfg = es._get_smtp_config(db)
        if not cfg or not cfg.get("admin_email") or cfg["admin_email"] in seen:
            continue
        seen.add(cfg["admin_email"])
        html = es._wrap_html(title, subject.replace("[Chirp] ", ""), html_body,
                             cta_url=page or "#", cta_label=cta if page else "",
                             server_url=es._get_server_url(db))
        if es._send(cfg, cfg["admin_email"], subject, html):
            sent += 1
    return {"emailed": sent}
