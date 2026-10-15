"""
Night flight calls (Settings → Experimental): stations upload night audio,
Nighthawk lists the calls. See services/nighthawk_service.py.

POST /upload is the station's (X-API-Key, like recordings/upload); the rest
is for the app. Experimental model status lives here too (/status).
"""
import logging
import os
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException,
                     Query, UploadFile, status)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import AppSettings, Device, FlightCall, NightChunk
from ..services import nighthawk_service as nh

logger = logging.getLogger("chirp.night_calls")
router = APIRouter()
MAX_CHUNK_BYTES = 200 * 1024 * 1024


def _valid_key(db: Session, key: Optional[str]) -> bool:
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    keys = [k.get("key") for k in ((s.device_api_keys if s else None) or []) if k.get("key")]
    if settings.device_api_key:
        keys.append(settings.device_api_key)
    return bool(key) and key in keys


@router.get("/accepting")
def night_audio_accepting(x_api_key: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """Asked by stations (device 1.4.0+) every 15 minutes: whether this
    server wants night audio, and when (local time in `timezone`)."""
    if not _valid_key(db, x_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing X-API-Key")
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    return {
        "enabled": bool(s and s.exp_nighthawk_enabled) and nh.available() is None,
        "start": (s.exp_nighthawk_start if s else None) or "21:00",
        "end": (s.exp_nighthawk_end if s else None) or "05:00",
        "timezone": (s.timezone if s else None) or "UTC",
        "sample_rate": 22050,
        "chunk_minutes": 10,
    }


@router.post("/upload", status_code=202)
async def upload_night_audio(
    background_tasks: BackgroundTasks,
    started_at: str = Form(..., description="UTC ISO time the chunk's first sample was recorded"),
    duration_seconds: float = Form(...),
    sample_rate: int = Form(...),
    device_serial: Optional[str] = Form(None),
    file: UploadFile = File(...),
    x_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """One chunk of night audio from a station (device 1.4.0+). 410 when
    night audio is off here, so the station drops the file instead of
    retrying it."""
    if not _valid_key(db, x_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing X-API-Key")
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if not (s and s.exp_nighthawk_enabled):
        raise HTTPException(status_code=410, detail="Night flight calls are off on this server")
    why = nh.available()
    if why:
        raise HTTPException(status_code=503, detail=why)
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        if started.tzinfo:
            started = started.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(status_code=400, detail="started_at must be ISO 8601")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_CHUNK_BYTES:
        raise HTTPException(status_code=413, detail="Chunk too large")
    device_id = None
    if device_serial:
        dev = db.query(Device).filter(Device.hostname == device_serial).first()
        device_id = dev.id if dev else None
    cid = str(uuid.uuid4())
    ext = os.path.splitext(file.filename or "")[1].lower() or ".flac"
    path = nh.audio_dir() / f"{cid}{ext}"
    path.write_bytes(data)
    db.add(NightChunk(id=cid, device_id=device_id, started_at=started, duration_seconds=duration_seconds,
                      sample_rate=sample_rate, path=str(path), status="pending"))
    db.commit()
    background_tasks.add_task(nh.process_chunk, cid)
    return {"chunk_id": cid, "status": "queued"}


def _call_out(c: FlightCall, groups: dict) -> dict:
    name = nh.display_name(c.level, c.category, c.common_name, c.family, c.order)
    return {
        "id": c.id, "detected_at": c.detected_at.isoformat() + "Z", "night": c.night,
        "level": c.level, "category": c.category, "name": name,
        "common_name": c.common_name, "scientific_name": c.scientific_name,
        "family": c.family, "order": c.order, "group": c.group,
        "group_members": groups.get(c.group or "", [])[:6] if c.level == "group" else None,
        "prob": round(c.prob or 0, 3), "duration": round(c.duration or 0, 2),
        "has_clip": bool(c.clip_path and os.path.exists(c.clip_path)),
    }


@router.get("/nights")
def list_nights(limit: int = Query(60, ge=1, le=366), db: Session = Depends(get_db)):
    """Nights with calls, newest first: counts by name."""
    rows = db.query(FlightCall.night, FlightCall.level, FlightCall.common_name, FlightCall.category,
                     FlightCall.family, FlightCall.order).all()
    by = {}
    for night, level, com, cat, fam, order in rows:
        n = by.setdefault(night, {"night": night, "calls": 0, "names": Counter(), "levels": {}})
        n["calls"] += 1
        name = nh.display_name(level, cat, com, fam, order)
        n["names"][name] += 1
        n["levels"][name] = level
    out = []
    for night in sorted(by, reverse=True)[:limit]:
        n = by[night]
        out.append({"night": night, "calls": n["calls"],
                    "top": [{"name": k, "count": v} for k, v in n["names"].most_common(5)],
                    "species": sum(1 for k in n["names"] if n["levels"][k] == "species")})
    return {"nights": out}


@router.get("")
def list_calls(night: Optional[str] = None, limit: int = Query(500, ge=1, le=2000),
               db: Session = Depends(get_db)):
    q = db.query(FlightCall)
    if night:
        q = q.filter(FlightCall.night == night)
    rows = q.order_by(FlightCall.detected_at.desc()).limit(limit).all()
    groups = nh.taxonomy()["groups"] if not nh.available() else {}
    return {"calls": [_call_out(c, groups) for c in rows]}


@router.get("/status")
def experimental_status(db: Session = Depends(get_db)):
    """Experimental models: BirdNET v3 download state, Nighthawk availability
    and the night-audio queue."""
    from ..services import birdnet3
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    chunks = db.query(NightChunk).order_by(NightChunk.created_at.desc()).limit(200).all()
    last = next((c for c in chunks if c.status == "done"), None)
    return {
        "birdnet3": birdnet3.status(),
        "nighthawk": {
            "available": nh.available() is None,
            "why": nh.available(),
            "enabled": bool(s and s.exp_nighthawk_enabled),
            "pending": sum(1 for c in chunks if c.status in ("pending", "processing")),
            "errors": sum(1 for c in chunks if c.status == "error"),
            "last_processed": (last.processed_at.isoformat() + "Z") if last and last.processed_at else None,
            "calls": db.query(FlightCall).count(),
        },
    }


@router.post("/birdnet3/download")
def birdnet3_download():
    from ..services import birdnet3
    return birdnet3.ensure_downloaded()


@router.get("/{call_id}/audio")
def call_audio(call_id: str, db: Session = Depends(get_db)):
    c = db.query(FlightCall).filter(FlightCall.id == call_id).first()
    if not c or not c.clip_path or not os.path.exists(c.clip_path):
        raise HTTPException(status_code=404, detail="No clip for this call")
    return FileResponse(c.clip_path, media_type="audio/flac", filename=f"flight_call_{c.id[:8]}.flac",
                        headers={"Cache-Control": "public, max-age=2592000, immutable"})


@router.get("/{call_id}/spectrogram")
def call_spectrogram(call_id: str, db: Session = Depends(get_db)):
    """Small spectrogram of the clip, made on first request and kept."""
    c = db.query(FlightCall).filter(FlightCall.id == call_id).first()
    if not c or not c.clip_path or not os.path.exists(c.clip_path):
        raise HTTPException(status_code=404, detail="No clip for this call")
    png = Path(c.clip_path).with_suffix(".png")
    if not png.exists():
        _spectrogram(c.clip_path, str(png))
    return FileResponse(str(png), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=2592000, immutable"})


def _spectrogram(src: str, dest: str):
    """Flight calls sit at 2–10 kHz: a linear axis to 11 kHz shows them best."""
    import librosa
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    y, sr = librosa.load(src, sr=None, mono=True)
    S = librosa.amplitude_to_db(np.abs(librosa.stft(y, n_fft=512, hop_length=64)), ref=np.max)
    fig = plt.figure(figsize=(4, 2), dpi=110)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(S, origin="lower", aspect="auto", cmap="magma", vmin=-80, vmax=0,
              extent=[0, len(y) / sr, 0, sr / 2])
    ax.set_ylim(0, min(11000, sr / 2)); ax.axis("off")
    fig.savefig(dest); plt.close(fig)


@router.delete("/{call_id}")
def delete_call(call_id: str, db: Session = Depends(get_db)):
    c = db.query(FlightCall).filter(FlightCall.id == call_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    for p in (c.clip_path, str(Path(c.clip_path).with_suffix(".png")) if c.clip_path else None):
        if p and os.path.exists(p):
            os.remove(p)
    db.delete(c); db.commit()
    return {"ok": True}
