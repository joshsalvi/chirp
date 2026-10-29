"""
Apple TV app.

Sign-in by code: the TV can't type a password comfortably, so it asks for a
short code, shows it (and a QR code to /tv?code=...), and polls until someone
signed in on a phone or computer approves it.

  POST /tv/pair/start      (no sign-in) → {pair_id, code, expires_in}
  POST /tv/pair/poll       (no sign-in) {pair_id} → pending | approved + token
  POST /tv/pair/approve    (signed in)  {code} → links that TV to this account

The TV's token (scope "tv") lasts TV_TOKEN_DAYS and only reaches the routes in
main.py's _TV_OK: these, the digest and journal, recent recordings and their
audio, Live Detect through a station, and the media routes.

  GET /tv/stations         stations Live Detect can listen through
  GET /tv/listen/{id}      a few seconds of a station's live audio (WAV)
"""
import logging
import secrets
import threading
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Device

logger = logging.getLogger(__name__)
router = APIRouter()

TV_TOKEN_DAYS = 180
PAIR_TTL_S = 600
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O, 1/I
CODE_LEN = 6
_MAX_PENDING = 200
_START_PER_IP = 10          # pair/start calls per IP per 10 minutes

_lock = threading.Lock()
_pending: dict = {}         # pair_id → {code, expires, approved: dict|None}
_starts: dict = {}          # ip → [timestamps]


def _now() -> float:
    return time.time()


def _sweep():
    t = _now()
    for k in [k for k, v in _pending.items() if v["expires"] < t]:
        _pending.pop(k, None)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")) or "?"


def normalize_code(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


@router.post("/pair/start")
def pair_start(request: Request):
    ip = _client_ip(request)
    with _lock:
        _sweep()
        recent = [t for t in _starts.get(ip, []) if t > _now() - PAIR_TTL_S]
        if len(recent) >= _START_PER_IP:
            raise HTTPException(429, "Too many sign-in codes. Wait a few minutes and try again.")
        if len(_pending) >= _MAX_PENDING:
            raise HTTPException(503, "Too many sign-ins in progress. Try again shortly.")
        _starts[ip] = recent + [_now()]
        used = {v["code"] for v in _pending.values()}
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LEN))
        while code in used:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LEN))
        pair_id = uuid.uuid4().hex
        _pending[pair_id] = {"code": code, "expires": _now() + PAIR_TTL_S, "approved": None}
    return {"pair_id": pair_id, "code": code, "expires_in": PAIR_TTL_S}


class PollIn(BaseModel):
    pair_id: str


@router.post("/pair/poll")
def pair_poll(body: PollIn):
    with _lock:
        _sweep()
        p = _pending.get(body.pair_id)
        if not p:
            return {"status": "expired"}
        if not p["approved"]:
            return {"status": "pending", "code": p["code"], "expires_in": int(p["expires"] - _now())}
        _pending.pop(body.pair_id, None)      # the token is handed out once
        return {"status": "approved", **p["approved"]}


class ApproveIn(BaseModel):
    code: str


@router.post("/pair/approve")
def pair_approve(body: ApproveIn, request: Request):
    from .auth import create_access_token, verify_token
    auth = request.headers.get("Authorization", "")
    payload = verify_token(auth[7:]) if auth.startswith("Bearer ") else None
    if (not payload or not payload.get("sub")) and not _auth_enabled():
        payload = {"sub": ""}          # sign-in turned off on this server: nothing to scope to
    if not payload or payload.get("sub") is None:
        raise HTTPException(401, "Sign in first, then enter the code from your TV.")
    if payload.get("scope") in ("tv", "watch"):
        raise HTTPException(403, "Approve the TV from your phone or computer.")
    code = normalize_code(body.code)
    if len(code) != CODE_LEN:
        raise HTTPException(400, f"Enter the {CODE_LEN}-character code shown on your TV.")
    claims = {k: payload[k] for k in ("sub", "global_user_id", "active_instance_id", "role") if k in payload}
    claims["scope"] = "tv"
    with _lock:
        _sweep()
        pid = next((k for k, v in _pending.items() if v["code"] == code and not v["approved"]), None)
        if not pid:
            raise HTTPException(404, "That code isn't valid or has expired. Check the TV for a new one.")
        _pending[pid]["approved"] = {
            "access_token": create_access_token(claims, expires_minutes=TV_TOKEN_DAYS * 1440),
            "username": payload.get("sub"),
            "expires_days": TV_TOKEN_DAYS,
        }
    logger.info("Apple TV linked for %s", payload.get("sub"))
    return {"ok": True}


def _auth_enabled() -> bool:
    try:
        from ..config import settings
        from ..database import SessionLocal
        from ..models import AppSettings
        with SessionLocal() as db:
            st = db.query(AppSettings).first()
            return bool(st.auth_enabled) if st and st.auth_enabled is not None else bool(settings.auth_enabled)
    except Exception:
        return True


# ── Live Detect through a station ────────────────────────────────────────────

def pick_bird_mic(mic_names) -> Optional[str]:
    """Same choice as LiveDetect.jsx's pickBirdMicName: the ReSpeaker, else the
    first mic that isn't the AudioMoth bat mic."""
    names = [n for n in (mic_names or []) if n and "audiomoth" not in n.lower()]
    for n in names:
        if "respeaker" in n.lower() or "xvf" in n.lower():
            return n
    return names[0] if names else None


@router.get("/stations")
def stations(db: Session = Depends(get_db)):
    out = []
    for d in db.query(Device).order_by(Device.name).all():
        host = (getattr(d, "hostname", "") or "").lower()
        if host.startswith(("birdbuddy:", "haikubox:")) or getattr(d, "bird_buddy_feeder_id", None):
            continue
        mic = pick_bird_mic(d.mic_names)
        if not mic:
            continue
        out.append({"id": d.id, "name": d.name, "online": bool(d.is_online()), "mic": mic})
    return out


@router.get("/listen/{device_id}")
async def listen(device_id: str, db: Session = Depends(get_db)):
    from .diagnostics import _fetch_device_listen_clip
    dev = db.query(Device).filter(Device.id == device_id).first()
    if not dev:
        raise HTTPException(404, "Station not found")
    mic = pick_bird_mic(dev.mic_names)
    if not mic:
        raise HTTPException(400, f"{dev.name} has no bird microphone to listen through.")
    wav = await _fetch_device_listen_clip(device_id, mic, db)
    return Response(content=wav, media_type="audio/wav", headers={"Cache-Control": "no-store"})


# ── Recent recordings with photos ────────────────────────────────────────────

@router.get("/recent")
def recent(limit: int = 24, db: Session = Depends(get_db)):
    """Newest bird recordings with a detection, for the TV's Recent row: the
    watch list (api/watch.py) plus each bird's photo. Audio comes from
    /watch/audio/{id} (AAC), the spectrogram from /recordings/{id}/spectrogram."""
    import os
    from ..models import BirdProfile
    from .watch import recent_rows
    rows = recent_rows(db, max(1, min(int(limit), 48)))
    names = {r["species"] for r in rows}
    profiles = {p.common_name: p for p in db.query(BirdProfile).filter(BirdProfile.common_name.in_(names)).all()}
    for r in rows:
        p = profiles.get(r["species"])
        photo = None
        if p is not None:
            if p.photo_path and os.path.exists(p.photo_path):
                photo = f"/api/v1/birds/{p.id}/photo"
            elif p.photo_url:
                photo = p.photo_url
        r["photo_url"] = photo
        r["scientific"] = p.scientific_name if p else None
    return rows
