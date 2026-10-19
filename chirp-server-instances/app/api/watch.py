"""
Apple Watch: the five newest recordings and their audio.

The watch signs in with a Live Detect-only token (POST /auth/watch-token);
main.py's _WATCH_OK lets it reach these two routes as well.

  GET /watch/recent           newest bird recordings that show a detection
  GET /watch/audio/{id}       that recording as a small AAC file (.m4a),
                              mono 22 kHz, cached; the watch can't decode
                              FLAC or Opus, and a 30 s WAV is 2.6 MB over
                              Bluetooth
"""
import logging
import os
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import AppSettings, Detection, Recording

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_SECONDS = 60     # the watch plays at most the first minute


@router.get("/recent")
def recent(limit: int = Query(5, ge=1, le=10), db: Session = Depends(get_db)):
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    min_conf = float(getattr(s, "min_confidence_display", 0.0) or 0.0) if s else 0.0
    recs = (
        db.query(Recording)
        .filter(Recording.deleted_at.is_(None))
        .filter(Recording.haikubox_detection_id.is_(None))
        .filter(Recording.is_bat.isnot(True))
        .filter(Recording.is_live_detect_clip.isnot(True))
        .filter(Recording.detections.any(Detection.confidence >= min_conf))
        .order_by(Recording.trigger_timestamp.desc())
        .limit(limit)
        .all()
    )
    out = []
    for r in recs:
        dets = sorted((d for d in r.detections if (d.confidence or 0) >= min_conf),
                      key=lambda d: d.confidence or 0, reverse=True)
        names = []
        for d in dets:
            if d.common_name not in names:
                names.append(d.common_name)
        has_audio = bool(r.wav_path and os.path.exists(r.wav_path))
        out.append({
            "id": r.id,
            "time": r.trigger_timestamp.isoformat() + ("Z" if r.trigger_timestamp.tzinfo is None else ""),
            "duration": round(min(float(r.duration_seconds or 0), MAX_SECONDS), 1),
            "species": names[0] if names else "Recording",
            "others": names[1:3],
            "confidence": round(float(dets[0].confidence), 2) if dets else None,
            "has_audio": has_audio,
        })
    return out


def _watch_audio_path(rec_id: str) -> str:
    d = os.path.join(settings.enhanced_dir, "watch")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{rec_id}.m4a")


@router.get("/audio/{recording_id}")
def audio(recording_id: str, db: Session = Depends(get_db)):
    rec = db.query(Recording).filter(Recording.id == recording_id,
                                     Recording.deleted_at.is_(None)).first()
    if not rec or not rec.wav_path or not os.path.exists(rec.wav_path):
        raise HTTPException(status_code=404, detail="Audio not found")
    out = _watch_audio_path(rec.id)
    if not os.path.exists(out):
        tmp = out + ".part.m4a"
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", rec.wav_path, "-t", str(MAX_SECONDS),
               "-ac", "1", "-ar", "22050", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", tmp]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            logger.warning("Watch audio %s: ffmpeg failed: %s", rec.id, e)
            raise HTTPException(status_code=500, detail="Couldn't prepare the audio")
        if proc.returncode != 0 or not os.path.exists(tmp):
            logger.warning("Watch audio %s: ffmpeg rc=%s %s", rec.id, proc.returncode, proc.stderr.decode()[:200])
            raise HTTPException(status_code=500, detail="Couldn't prepare the audio")
        os.replace(tmp, out)
    return FileResponse(out, media_type="audio/mp4", headers={"Cache-Control": "private, max-age=86400"})
