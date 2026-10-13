"""
Email sent on behalf of the whole server rather than one site: site
requests from the About page, approvals, relay tokens.

SMTP: the server's CHIRP_SMTP_* environment (config.py) first, then the
oldest site that has SMTP set up. Credentials are only read here, never
returned to anyone.
"""
import logging
from typing import Optional

logger = logging.getLogger("chirp.platform_mail")


def platform_smtp_config() -> Optional[dict]:
    from ..config import settings as cfg
    if cfg.smtp_host and (cfg.smtp_from_address or cfg.smtp_username):
        return {
            "host": cfg.smtp_host,
            "port": int(cfg.smtp_port or 587),
            "username": cfg.smtp_username,
            "password": cfg.smtp_password,
            "from_addr": cfg.smtp_from_address or cfg.smtp_username,
            "use_tls": True if cfg.smtp_use_tls is None else bool(cfg.smtp_use_tls),
            "admin_email": cfg.admin_email,
        }
    from sqlalchemy.orm import sessionmaker
    from ..registry_db import RegistrySessionLocal
    from ..registry_models import Instance
    from ..instance_registry import get_engine_for_instance
    from .email_service import _get_smtp_config
    reg = RegistrySessionLocal()
    try:
        instances = reg.query(Instance).order_by(Instance.created_at).all()
    finally:
        reg.close()
    for inst in instances:
        try:
            db = sessionmaker(bind=get_engine_for_instance(inst.db_filename))()
            try:
                c = _get_smtp_config(db)
            finally:
                db.close()
            if c:
                return c
        except Exception as e:
            logger.debug("SMTP lookup skipped %s: %s", inst.id, e)
    return None


def public_url(request=None) -> str:
    """https://ourchirp.com — CHIRP_PUBLIC_URL, else CHIRP_SERVER_URL, else the request's own base."""
    import os
    from ..config import settings as cfg
    url = (cfg.public_url or os.environ.get("CHIRP_SERVER_URL") or "").strip()
    if not url and request is not None:
        url = str(request.base_url)
    return url.rstrip("/")


def global_admin_emails() -> list:
    from ..registry_db import RegistrySessionLocal
    from ..registry_models import GlobalUser
    reg = RegistrySessionLocal()
    try:
        return [u.email for u in reg.query(GlobalUser).filter(GlobalUser.is_global_admin == True,  # noqa: E712
                                                              GlobalUser.active == True).all()  # noqa: E712
                if u.email and "@" in u.email]
    finally:
        reg.close()


def send_platform_email(to, subject: str, title: str, preheader: str, body_html: str, text: str,
                        cta_url: str = "#", cta_label: str = "", server_url: str = "") -> bool:
    from .email_service import _send, _wrap_html
    cfg = platform_smtp_config()
    if not cfg:
        logger.warning("No SMTP available for server email: %s", subject)
        return False
    html = _wrap_html(title, preheader, body_html, cta_url=cta_url, cta_label=cta_label, server_url=server_url)
    return _send(cfg, to, subject, html, text)
