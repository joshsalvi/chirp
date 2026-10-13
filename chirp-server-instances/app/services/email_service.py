"""
Chirp Email Service — SMTP-based email notifications.

Features:
  - Beautiful HTML emails for all notification types
  - Daily digest of detections
  - New-bird alert (species not previously on life list)
  - New user registration alert to admin
  - Password change confirmation
  - Graceful failure (logs error, never raises to caller)
"""

import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime, timedelta
from typing import List, Optional, Union

logger = logging.getLogger("chirp.email")


def _get_server_url(db) -> str:
    """Return the configured public base URL, stripping any trailing slash.
    Priority:
      1. server_url stored in app_settings (set via Settings UI)
      2. CHIRP_SERVER_URL environment variable
    Without a URL email links cannot be absolute — log a warning once."""
    import os, logging
    # 1. DB setting
    try:
        from ..models import AppSettings
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        url = getattr(s, "server_url", None) if s else None
        if url and url.strip():
            return url.strip().rstrip("/")
    except Exception:
        pass
    # 2. Environment variable
    env_url = os.environ.get("CHIRP_SERVER_URL", "").strip().rstrip("/")
    if env_url:
        return env_url
    logging.getLogger("chirp.email").warning(
        "server_url is not configured — email links will be broken. "
        "Set it in Settings → General → Web Address, or via the "
        "CHIRP_SERVER_URL environment variable."
    )
    return ""


# ── SMTP config ───────────────────────────────────────────────────────────────

def _get_smtp_config(db):
    try:
        from ..models import AppSettings
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        if not s:
            return None
        host      = getattr(s, "smtp_host", None)
        port      = getattr(s, "smtp_port", 587)
        user      = getattr(s, "smtp_username", None)
        pw        = getattr(s, "smtp_password", None)
        from_addr = getattr(s, "smtp_from_address", None) or user
        if not host or not from_addr:
            return None
        return {
            "host":        host,
            "port":        int(port or 587),
            "username":    user,
            "password":    pw,
            "from_addr":   from_addr,
            "use_tls":     bool(getattr(s, "smtp_use_tls", True)),
            "admin_email": getattr(s, "admin_email", None),
        }
    except Exception as e:
        logger.debug("SMTP config fetch failed: %s", e)
        return None


def _send(cfg: dict, to: Union[str, List[str]], subject: str, html: str, text: str = "",
          attachment: Optional[dict] = None, inline_images: Optional[list] = None) -> bool:
    """
    attachment, if provided: {"filename": str, "content": bytes, "mimetype": str}
    (mimetype e.g. "text/plain" or "application/zip"). Optional and purely
    additive — every existing caller passes nothing here and gets exactly
    the same multipart/alternative message structure as before. When
    provided, the message becomes multipart/mixed with the text/html
    alternative nested inside it alongside the attachment part, which is
    the standard MIME structure for "email body + a file attached to it"
    (a single flat multipart/alternative can't carry a real attachment —
    that subtype means "these parts are different renderings of the same
    content", not "here's the body plus a separate file").
    """
    if not cfg or not to:
        return False
    recipients = [to] if isinstance(to, str) else to
    recipients = [r for r in recipients if r and "@" in r]
    if not recipients:
        return False

    alt = MIMEMultipart("alternative")
    if text:
        alt.attach(MIMEText(text, "plain", "utf-8"))
    alt.attach(MIMEText(html, "html", "utf-8"))

    # Images the HTML shows as cid: (the logo and bird photos) go inside a
    # multipart/related with it, so they display without remote loading.
    images = list(inline_images or [])
    from .email_theme import LOGO_CID, logo_png
    if f"cid:{LOGO_CID}" in html and not any(i["cid"] == LOGO_CID for i in images):
        images.append({"cid": LOGO_CID, "content": logo_png(), "mimetype": "image/png"})
    if images:
        from email.mime.image import MIMEImage
        body = MIMEMultipart("related")
        body.attach(alt)
        for img in images:
            part = MIMEImage(img["content"], _subtype=img.get("mimetype", "image/png").split("/")[-1])
            part.add_header("Content-ID", f"<{img['cid']}>")
            part.add_header("Content-Disposition", "inline", filename=f"{img['cid']}.{part.get_content_subtype()}")
            body.attach(part)
    else:
        body = alt

    if attachment:
        msg = MIMEMultipart("mixed")
        msg.attach(body)
        part = MIMEApplication(attachment["content"], _subtype=attachment.get("mimetype", "application/octet-stream").split("/")[-1])
        part.add_header("Content-Disposition", "attachment", filename=attachment["filename"])
        msg.attach(part)
    else:
        msg = body

    msg["Subject"] = subject
    msg["From"]    = cfg["from_addr"]
    msg["To"]      = ", ".join(recipients)

    try:
        # Port 465 is SSL from the start; any other port is plain SMTP,
        # upgraded with STARTTLS when "Use STARTTLS" is on (587).
        ctx = ssl.create_default_context()
        if cfg["port"] == 465:
            srv_cm = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=15, context=ctx)
        else:
            srv_cm = smtplib.SMTP(cfg["host"], cfg["port"], timeout=15)
        with srv_cm as srv:
            if cfg["port"] != 465 and cfg["use_tls"]:
                srv.ehlo()
                srv.starttls(context=ctx)
            if cfg["username"] and cfg["password"]:
                srv.login(cfg["username"], cfg["password"])
            srv.sendmail(cfg["from_addr"], recipients, msg.as_string())
        logger.info("Email sent to %s: %s", recipients, subject)
        return True
    except Exception as e:
        logger.warning("Email send failed (%s → %s): %s", subject, recipients, e)
        return False


# ── Look (see email_theme) ────────────────────────────────────────────────────

from . import email_theme as _t


def _logo_html(server_url: str = "") -> str:
    """The app icon, attached inline by _send (cid:), so it shows without
    loading remote images and always matches the current logo."""
    return (f'<img src="cid:{_t.LOGO_CID}" width="44" height="44" alt="Chirp" '
            'style="width:44px;height:44px;border-radius:10px;display:block;"/>')


def _journal_box(text: str) -> str:
    return _t.journal_box(text)


def _wrap_html(title: str, preheader: str, body_html: str,
               accent: str = _t.ACCENT, cta_url: str = "#",
               cta_label: str = "", server_url: str = "", subtitle: str = "") -> str:
    return _t.wrap_html(title, preheader, body_html, subtitle=subtitle, accent=accent,
                        cta_url=cta_url, cta_label=cta_label, server_url=server_url)


def _species_row(common_name: str, scientific_name: str = "",
                 count: int = 0, confidence: float = 0,
                 photo_url: str = "", is_new: bool = False) -> str:
    badges = ""
    if is_new:
        badges += _t.badge("&#10022; First detection", _t.ACCENT_TEXT, _t.ACCENT_SOFT) + " "
    if confidence:
        badges += _t.badge(f"{confidence * 100:.0f}%", _t.GREEN, _t.GREEN_SOFT) + " "
    lines = [f"<i>{_t.esc(scientific_name)}</i>" if scientific_name else "",
             f"{count} detection{'s' if count != 1 else ''}" if count else ""]
    return _t.species_card(common_name, photo_url or None, lines, badges)


def _stat_card(value: str, label: str, accent: str = _t.ACCENT_TEXT) -> str:
    soft = {_t.TEAL: _t.TEAL_SOFT, _t.VIOLET: _t.VIOLET_SOFT, _t.GREEN: _t.GREEN_SOFT}.get(accent, _t.ACCENT_SOFT)
    return _t.stat_tile(value, label, accent, soft)


def _section_label(text: str) -> str:
    return _t.section_label(text)


def _info_box(html: str, accent: str = _t.ACCENT) -> str:
    return _t.info_box(html, accent)


# ── Public notification functions ─────────────────────────────────────────────

def notify_new_registration(db, username: str, email: Optional[str],
                            server_url: str = "", to_emails: Optional[list] = None,
                            pending_approval: bool = True, instance_name: str = "") -> None:
    """
    Email admin(s) when a new user registers.

    to_emails overrides the single instance-configured admin_email with
    an explicit recipient list — added for the invite-code registration
    flow (see auth.py's register()), which notifies every one of that
    location's global admins, not the one address AppSettings happens
    to have on file. pending_approval=False (also from that same flow)
    swaps the badge/copy below to reflect that joining via a real
    invite code is already self-approving, not something that still
    needs a decision — sending "awaiting approval" copy for someone
    who's already in would just be inaccurate.
    """
    cfg = _get_smtp_config(db)
    if not cfg:
        return
    recipients = to_emails or ([cfg["admin_email"]] if cfg.get("admin_email") else [])
    if not recipients:
        return
    server_url = server_url or _get_server_url(db)

    avatar = f"""<div style="width:56px;height:56px;border-radius:50%;background:linear-gradient(135deg,#f97316,#dc2626);
                 display:flex;align-items:center;justify-content:center;font-size:22px;font-weight:800;
                 color:#fff;flex-shrink:0;">{username[0].upper()}</div>"""

    status_badge = (
        """<span style="display:inline-block;padding:3px 10px;border-radius:99px;font-size:11px;font-weight:600;
                        background:#fff1e6;color:#c2410c;border:1px solid #fed7aa;">Awaiting approval</span>"""
        if pending_approval else
        """<span style="display:inline-block;padding:3px 10px;border-radius:99px;font-size:11px;font-weight:600;
                        background:#e9f6ec;color:#15803d;border:1px solid #bbe5c6;">Joined automatically</span>"""
    )
    instance_line = f'<div style="font-size:13px;color:#4a6b52;margin-top:3px;">Joined {instance_name}</div>' if instance_name else ""

    body = f"""
    {_section_label("New Registration")}
    <table width="100%" cellpadding="0" cellspacing="0"
           style="background:#f4f7f2;border-radius:12px;padding:16px;border:1px solid #dfe6dc;margin-bottom:20px;">
      <tr>
        <td width="56" style="vertical-align:middle;padding-right:16px;">{avatar}</td>
        <td style="vertical-align:middle;">
          <div style="font-size:17px;font-weight:700;color:#14231a;">{username}</div>
          <div style="font-size:13px;color:#4a6b52;margin-top:3px;">{email or "No email provided"}</div>
          {instance_line}
          <div style="margin-top:8px;">
            {status_badge}
          </div>
        </td>
      </tr>
    </table>
    {_info_box("Review and approve or reject this registration from the <strong style='color:#14231a;'>Users</strong> page in Chirp.") if pending_approval else _info_box(f"{username} joined with a viewer role using an invite code — no action needed, this is just a heads-up. Adjust their role from the <strong style='color:#14231a;'>Users</strong> page if needed.")}
    """

    subject = f"[Chirp] New registration: {username}" if pending_approval else f"[Chirp] {username} joined{f' {instance_name}' if instance_name else ''}"
    intro = f"{username} has registered and is awaiting approval." if pending_approval else f"{username} registered and joined{f' {instance_name}' if instance_name else ''} automatically via invite code."

    _send(cfg, recipients,
          subject,
          _wrap_html("New User Registration" if pending_approval else "New User Joined", intro, body,
                     cta_url=f"{server_url}/users", cta_label="Review Registration" if pending_approval else "View Users",
                     server_url=server_url))


def build_new_bird_email(db, common_name: str, scientific_name: str, confidence: float,
                         photo_url: Optional[str] = None, server_url: str = ""):
    """(subject, html, inline images) for a new-species alert."""
    # The species photo, attached inline (see build_daily_digest); a
    # relative or non-https photo_url wouldn't load in a mail app.
    imgs = _t.InlineImages()
    src = None
    try:
        from ..models import BirdProfile
        prof = db.query(BirdProfile).filter(BirdProfile.common_name == common_name).first()
        if prof and prof.photo_path:
            src = imgs.add_photo(prof.photo_path, 330, 330)
        if not src and prof and str(prof.photo_url or "").startswith("https://"):
            src = prof.photo_url
    except Exception:
        pass
    if not src and str(photo_url or "").startswith("https://"):
        src = photo_url
    photo_url = src

    body = f"""
    <div style="text-align:center;padding:8px 0 20px;">
      <div style="font-size:40px;margin-bottom:4px;">🎉</div>
      <div style="font-size:13px;color:#4a6b52;font-weight:600;text-transform:uppercase;letter-spacing:.08em;">First Detection</div>
    </div>

    <!-- Species hero card -->
    <table width="100%" cellpadding="0" cellspacing="0"
           style="background:#f4f7f2;border-radius:16px;
                  border:1px solid #fed7aa;margin-bottom:24px;overflow:hidden;">
      <tr>
        {'<td width="110" style="vertical-align:top;padding:0;"><img src="' + photo_url + '" width="110" style="display:block;width:110px;height:110px;object-fit:cover;" alt="' + common_name + '"/></td>' if photo_url else ''}
        <td style="padding:20px;">
          <div style="font-size:22px;font-weight:800;color:#14231a;line-height:1.2;letter-spacing:-.3px;">{common_name}</div>
          <div style="font-size:13px;font-style:italic;color:#4a6b52;margin-top:4px;">{scientific_name or ""}</div>
          <div style="margin-top:14px;">
            <span style="display:inline-block;padding:4px 12px;border-radius:99px;font-size:11px;font-weight:700;
                         background:#fff1e6;color:#c2410c;border:1px solid #fed7aa;">✦ New to your life list</span>
            <span style="display:inline-block;padding:4px 12px;border-radius:99px;font-size:11px;font-weight:600;
                         background:#e9f6ec;color:#15803d;border:1px solid #bbe5c6;margin-left:6px;">{confidence*100:.0f}% confidence</span>
          </div>
        </td>
      </tr>
    </table>

    {_info_box(f"A <strong style='color:#14231a;'>{common_name}</strong> was identified at your monitoring location for the first time. Head to the Bird Profiles page to learn more about this species.")}
    """

    subject = f"[Chirp] \U0001F426 New bird: {common_name}!"
    html = _wrap_html("New Species Detected", f"{common_name} just joined your life list!",
                      body, cta_url=f"{server_url}/library", cta_label="View Life List",
                      server_url=server_url)
    return subject, html, imgs.parts


def notify_new_bird(db, common_name: str, scientific_name: str,
                    confidence: float, photo_url: Optional[str] = None,
                    server_url: str = "") -> None:
    """Email opted-in users when a new species is detected for the first time."""
    # Check global notifications_enabled flag first
    try:
        from ..models import AppSettings as _AS_chk
        _s_chk = db.query(_AS_chk).filter(_AS_chk.id == 1).first()
        if _s_chk and not getattr(_s_chk, 'notifications_enabled', False):
            return  # global notifications disabled
    except Exception:
        pass
    cfg = _get_smtp_config(db)
    if not cfg:
        return
    server_url = server_url or _get_server_url(db)

    try:
        from ..models import User as _User
        # Only send to users who have explicitly opted in (notify_new_bird = True).
        # admin_email is intentionally NOT added here — it is only used for system
        # alerts such as new registrations. If the admin wants species alerts they
        # should set notify_new_bird = True on their user profile.
        recipients = [
            u.email for u in db.query(_User).filter(
                _User.active == True,
                _User.email.isnot(None),
            ).all()
            if getattr(u, "notify_new_bird", True) and u.email and "@" in u.email
               and not u.email.endswith("@chirp.local")
        ]
    except Exception:
        recipients = []

    if not recipients:
        return

    subject, html, images = build_new_bird_email(db, common_name, scientific_name, confidence,
                                                 photo_url, server_url)
    for recipient in recipients:
        _send(cfg, recipient, subject, html, inline_images=images)


def site_today(db):
    """Today's date in the site's time zone (AppSettings.timezone)."""
    from datetime import timezone as _tzmod
    from ..models import AppSettings
    from .scheduled_push import site_tz
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    return datetime.now(_tzmod.utc).astimezone(site_tz(s)).date()


def compute_yesterday_stats(db):
    """Yesterday's numbers (see compute_day_stats)."""
    return compute_day_stats(db, site_today(db) - timedelta(days=1))


def compute_day_stats(db, day):
    """
    One day's numbers, shared by the email digest, the push digest and the
    app's digest page so they never disagree. Counts what the app shows: detections at the
    display threshold, and recordings with at least one of them (the
    "Unknown" cards the list hides don't count). Returns None for a day
    with nothing to report.
    """
    from collections import Counter, defaultdict
    from ..models import AppSettings, Detection, Recording

    from datetime import timezone as _tzmod
    from .scheduled_push import site_tz
    yesterday = day
    day_str = yesterday.strftime("%A, %B %-d")  # e.g. "Thursday, June 5"

    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    # The site's local day, as the naive-UTC bounds recordings are stored in.
    tz = site_tz(s)

    def _utc(d):
        return datetime.combine(d, datetime.min.time(), tzinfo=tz).astimezone(_tzmod.utc).replace(tzinfo=None)
    day_start, day_end = _utc(yesterday), _utc(yesterday + timedelta(days=1))
    today = datetime.now(_tzmod.utc).astimezone(tz).date()
    display_min = float(getattr(s, "min_confidence_display", 0.0) or 0.0) if s else 0.0

    recs = db.query(Recording).filter(
        Recording.trigger_timestamp >= day_start,
        Recording.trigger_timestamp < day_end,
        Recording.deleted_at.is_(None),
    ).all()

    shown = {r.id: [d for d in r.detections if float(d.confidence or 0) >= display_min] for r in recs}
    recs = [r for r in recs if shown[r.id]]
    total_recs = len(recs)
    if total_recs == 0:
        return None  # Skip quiet days

    all_dets = [d for r in recs for d in shown[r.id]]
    total_dets = len(all_dets)
    species_counts = Counter(d.common_name for d in all_dets)
    top_species = species_counts.most_common(6)
    unique_species = len(species_counts)
    best_conf = defaultdict(float)
    best_rec = {}
    scientific = {}
    first_heard = {}
    for r in recs:
        for d in shown[r.id]:
            if float(d.confidence or 0) >= best_conf[d.common_name]:
                best_conf[d.common_name] = float(d.confidence or 0)
                best_rec[d.common_name] = r.id
            if d.scientific_name:
                scientific.setdefault(d.common_name, d.scientific_name)
            t = r.trigger_timestamp
            if t and (d.common_name not in first_heard or t < first_heard[d.common_name]):
                first_heard[d.common_name] = t

    # Species heard for the first time ever (at the display threshold).
    earlier = {name for (name,) in (
        db.query(Detection.common_name)
        .join(Recording, Recording.id == Detection.recording_id)
        .filter(Detection.common_name.in_(list(species_counts)),
                Detection.confidence >= display_min,
                Recording.trigger_timestamp < day_start,
                Recording.deleted_at.is_(None))
        .group_by(Detection.common_name).all())}
    new_species = [n for n, _ in species_counts.most_common() if n not in earlier]

    # Busiest hour, local time.
    hours = Counter()
    for r in recs:
        t = r.trigger_timestamp
        if t is None:
            continue
        hours[t.replace(tzinfo=_tzmod.utc).astimezone(tz).hour] += 1
    busiest_hour = hours.most_common(1)[0][0] if hours else None

    return {
        "yesterday": yesterday, "day_str": day_str,
        "day_start": day_start, "day_end": day_end,
        "total_recs": total_recs, "total_dets": total_dets,
        "species_counts": species_counts, "top_species": top_species,
        "unique_species": unique_species, "best_conf": dict(best_conf),
        "scientific": scientific, "new_species": new_species,
        "busiest_hour": busiest_hour, "display_min": display_min,
        "tz": tz, "first_heard": first_heard,
        "best_rec": best_rec, "hours": dict(hours),
        "partial": yesterday >= today,   # the day isn't over yet: numbers so far
        "relative": ("today" if yesterday == today else
                     "yesterday" if yesterday == today - timedelta(days=1) else None),
    }


def _hour_label(h: int) -> str:
    def fmt(x):
        x %= 24
        return f"{12 if x % 12 == 0 else x % 12} {'AM' if x < 12 else 'PM'}"
    return f"{fmt(h)}\u2013{fmt(h + 1)}"


def build_daily_digest(db, server_url: str = "", stats: Optional[dict] = None):
    """(subject, html, inline images, plain text) for one day's digest
    (default yesterday), or None on a quiet day."""
    from ..models import AppSettings, BirdProfile
    stats = stats or compute_yesterday_stats(db)
    if stats is None:
        return None
    day_str = stats["day_str"]
    total_recs, total_dets = stats["total_recs"], stats["total_dets"]
    species_counts, top_species = stats["species_counts"], stats["top_species"]
    unique_species = stats["unique_species"]
    new_species = stats.get("new_species") or []
    base = server_url.rstrip("/") if server_url else ""

    # Photos: the downloaded photo, attached inline (the photo endpoint
    # needs a signed-in session, so a link to it showed nothing in mail),
    # or the profile's public photo URL.
    imgs = _t.InlineImages()
    names = list(dict.fromkeys([n for n, _ in top_species] + new_species[:3]))
    profiles = {p.common_name: p for p in db.query(BirdProfile).filter(BirdProfile.common_name.in_(names)).all()}

    def photo(name):
        p = profiles.get(name)
        if not p:
            return None
        src = imgs.add_photo(p.photo_path) if p.photo_path else None
        if not src and p.photo_url and str(p.photo_url).startswith("https://"):
            src = p.photo_url
        return src

    def link(name):
        p = profiles.get(name)
        return f"{base}/library/{p.id}" if (base and p) else ""

    tz = stats.get("tz")

    def local_time(t):
        if t is None:
            return ""
        if tz is not None:
            from datetime import timezone as _tzmod
            t = t.replace(tzinfo=_tzmod.utc).astimezone(tz)
        return t.strftime("%-I:%M %p").lower()

    top_count = top_species[0][1] if top_species else 1
    cards = []
    for name, count in top_species:
        is_new = name in new_species
        badges = _t.badge("&#10022; New", _t.ACCENT_TEXT, _t.ACCENT_SOFT) if is_new else ""
        lines = [f"{count} detection{'s' if count != 1 else ''} &middot; best {stats['best_conf'].get(name, 0) * 100:.0f}%",
                 f"first heard {local_time(stats['first_heard'].get(name))}" if stats.get("first_heard", {}).get(name) else ""]
        cards.append(_t.species_card(name, photo(name), lines, badges,
                                     bar_pct=100 * count / max(1, top_count), link=link(name)))

    highlight = ""
    if new_species:
        first = new_species[0]
        more = (f" and {len(new_species) - 1} more" if len(new_species) > 1 else "")
        src = photo(first)
        pic = (f'<td width="96" style="padding-right:14px;vertical-align:middle;"><img src="{src}" width="96" '
               f'alt="{_t.esc(first)}" style="display:block;width:96px;height:64px;border-radius:8px;"/></td>'
               if src else "")
        highlight = (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="background:{_t.ACCENT_SOFT};border-radius:12px;margin:0 0 24px;"><tr><td style="padding:14px 16px;">'
            f'<table role="presentation" cellpadding="0" cellspacing="0"><tr>{pic}<td style="vertical-align:middle;">'
            f'<div style="font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:{_t.ACCENT_TEXT};">'
            f'New to your life list</div>'
            f'<div style="font-size:18px;font-weight:800;color:{_t.INK};margin-top:4px;">{_t.esc(first)}{more}</div>'
            f'</td></tr></table></td></tr></table>')

    busiest = stats.get("busiest_hour")
    facts = []
    if busiest is not None:
        facts.append(f"Busiest hour: <b>{_hour_label(busiest)}</b>")
    if len(species_counts) > len(top_species):
        facts.append(f"{len(species_counts) - len(top_species)} more species beyond the top {len(top_species)}")
    facts_html = (f'<p class="em-muted" style="margin:4px 0 0;font-size:13px;color:{_t.MUTED};">'
                  + " &nbsp;&middot;&nbsp; ".join(facts) + "</p>") if facts else ""

    journal_section = ""
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if s and s.daily_summary_text and s.daily_summary_generated_at:
        if datetime.utcnow() - s.daily_summary_generated_at <= timedelta(hours=36):
            journal_section = (f'<div style="height:22px;"></div>{_t.section_label("From your Daily Journal")}'
                               f'{_t.journal_box(s.daily_summary_text)}')

    body = (
        _t.stat_row([
            _t.stat_tile(str(total_recs), "Recordings", _t.ACCENT_TEXT, _t.ACCENT_SOFT),
            _t.stat_tile(str(total_dets), "Detections", _t.TEAL, _t.TEAL_SOFT),
            _t.stat_tile(str(unique_species), "Species", _t.VIOLET, _t.VIOLET_SOFT),
        ])
        + highlight
        + _t.section_label(f"Top {len(top_species)} species")
        + _t.species_grid(cards)
        + facts_html
        + journal_section
    )
    rel = stats.get("relative")
    when = rel or f"on {stats['yesterday'].strftime('%A')}"
    so_far = " so far" if stats.get("partial") else ""
    subject = f"[Chirp] {unique_species} species {when}{so_far} \u2014 {day_str}"
    preheader = (f"{', '.join(n for n, _ in top_species[:3])}"
                 + (f" and {unique_species - 3} more" if unique_species > 3 else "")
                 + f" \u00b7 {total_recs} recordings")
    heading = f"{(rel or stats['yesterday'].strftime('%A')).capitalize()} in your yard{so_far}"
    digest_url = f"{base}/digest?date={stats['yesterday'].isoformat()}"
    html = _wrap_html(heading, preheader, body,
                      cta_url=digest_url, cta_label="Open the full digest",
                      server_url=base, subtitle=day_str)
    text = (f"Chirp digest for {day_str}{so_far}\n{total_recs} recordings, {total_dets} detections, "
            f"{unique_species} species.\n\n"
            + "\n".join(f"- {n}: {c}" for n, c in top_species)
            + (f"\n\nNew to your life list: {', '.join(new_species)}" if new_species else "")
            + (f"\n\n{digest_url}" if base else ""))
    return subject, html, imgs.parts, text


def send_daily_digest(db, server_url: str = "", day=None) -> None:
    """Email one day's digest (default yesterday) to opted-in users."""
    cfg = _get_smtp_config(db)
    if not cfg:
        return
    server_url = server_url or _get_server_url(db)

    try:
        from ..models import User as _User

        users = [u for u in db.query(_User).filter(
            _User.active == True, _User.email.isnot(None)
        ).all() if getattr(u, "notify_daily_digest", False)
                    and u.email and "@" in u.email
                    and not u.email.endswith("@chirp.local")]

        # admin_email not added here — digest goes only to users who opted in
        if not users:
            return

        stats = compute_day_stats(db, day) if day else compute_yesterday_stats(db)
        built = build_daily_digest(db, server_url, stats=stats) if stats else None
        if built is None:
            return  # Skip quiet days
        subject, html, images, text = built
        for user in users:
            _send(cfg, user.email, subject, html, text=text, inline_images=images)

        logger.info("Daily digest sent to %d users", len(users))

    except Exception as e:
        logger.error("Daily digest failed: %s", e)


def send_diagnostics_report(db, to_email: str, mode: str, report_text: str,
                             attachment_bytes: bytes, attachment_filename: str,
                             attachment_mimetype: str, server_url: str = "") -> bool:
    """
    Emails a diagnostics report as a file attachment (the full report text
    or ZIP, exactly what the "Download" button in Settings produces) rather
    than inlining the report text into the email body — a full diagnostics
    report is long, plain-text-formatted output that wouldn't read well
    reflowed into an HTML email, and this way the emailed and downloaded
    versions are guaranteed to be byte-for-byte the same file, not two
    independently-formatted renderings of the same data that could drift
    apart from each other over time.

    Returns True/False (send success) rather than swallowing failures
    silently the way most of this module's notify_* functions do — those
    are best-effort background notifications where a silent failure is
    the right default; this one is a direct result of someone clicking an
    "Email me this report" button and expects to know whether it worked.
    """
    cfg = _get_smtp_config(db)
    if not cfg:
        logger.warning("Diagnostics report email requested but SMTP is not configured")
        return False
    if not to_email or "@" not in to_email:
        logger.warning("Diagnostics report email requested with an invalid address: %r", to_email)
        return False
    server_url = server_url or _get_server_url(db)

    mode_label = {"full": "Full", "db": "Database", "mic": "Microphone"}.get(mode, mode.title())
    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    # Built as a plain string BEFORE the f-string below, not as a nested
    # f-string inside it — a nested f-string containing escaped quotes
    # (a backslash inside the {} expression part) is invalid syntax in
    # Python 3.11 (only allowed from 3.12+), and production runs 3.11.15.
    # This was a real, confirmed bug: it broke this entire module at
    # import time for anyone who happened to trigger this specific
    # function's code path, not just a cosmetic issue.
    attachment_note = _info_box(
        "Attached as <strong style='color:#475569;'>" + attachment_filename +
        "</strong> — the exact same file the \u201cDownload\u201d button in Settings \u2192 Diagnostics produces.",
        "#a78bfa",
    )
    body = f"""
    {_section_label("Diagnostics report")}
    <table width="100%" cellpadding="0" cellspacing="0"
           style="background:#f4f7f2;border-radius:12px;padding:20px;border:1px solid #dfe6dc;margin-bottom:20px;">
      <tr>
        <td style="font-size:32px;width:48px;text-align:center;">🩺</td>
        <td style="padding-left:16px;vertical-align:middle;">
          <div style="font-size:15px;font-weight:600;color:#14231a;">{mode_label} diagnostics report attached</div>
          <div style="font-size:12px;color:#5f6f64;margin-top:6px;">{generated_at}</div>
        </td>
      </tr>
    </table>
    {attachment_note}
    """

    return _send(
        cfg, to_email,
        f"[Chirp] {mode_label} diagnostics report",
        _wrap_html("Diagnostics Report", f"Your requested {mode_label.lower()} diagnostics report is attached.",
                   body, server_url=server_url),
        attachment={"filename": attachment_filename, "content": attachment_bytes, "mimetype": attachment_mimetype},
    )


def notify_password_changed(db, username: str, email: str,
                            server_url: str = "") -> None:
    """Notify a user that their password was changed."""
    cfg = _get_smtp_config(db)
    if not cfg or not email or "@" not in email or email.endswith("@chirp.local"):
        return
    server_url = server_url or _get_server_url(db)

    body = f"""
    {_section_label("Security notice")}
    <table width="100%" cellpadding="0" cellspacing="0"
           style="background:#f4f7f2;border-radius:12px;padding:20px;border:1px solid #dfe6dc;margin-bottom:20px;">
      <tr>
        <td style="font-size:32px;width:48px;text-align:center;">🔐</td>
        <td style="padding-left:16px;vertical-align:middle;">
          <div style="font-size:15px;font-weight:600;color:#14231a;">Password changed</div>
          <div style="font-size:13px;color:#4a6b52;margin-top:3px;">Account: <strong style="color:#475569;">{username}</strong></div>
          <div style="font-size:12px;color:#5f6f64;margin-top:6px;">{datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}</div>
        </td>
      </tr>
    </table>
    {_info_box("If you made this change, no action is needed. If you did <strong style='color:#c2410c;'>not</strong> change your password, contact your Chirp administrator immediately.", "#f97316")}
    """

    _send(cfg, email,
          "[Chirp] Your password was changed",
          _wrap_html("Password Changed", "Your Chirp account password was updated.",
                     body, server_url=server_url))
