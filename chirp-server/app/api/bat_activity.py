"""
Chirp Server — Bat Activity Upload & Playback API
=====================================================
Receives uploaded bat-echolocation activity events from the device's
BatDetector (chirp-device/chirp/bat_detector.py) and stores them as a
Recording + single Detection row (common_name="Bat", label="Bat"), the
same tables every bird detection uses — rather than the standalone
BatActivity table this endpoint originally wrote to.

Why the change: a bat detection that lives in its own parallel table never
shows up in RecordingsList, the life list, the field guide, or anywhere
else species data is queried, since all of those query Recording/Detection/
BirdProfile. Routing bat detections through the same tables (with a
sentinel is_bat=True flag and a one-off static "Bat" BirdProfile — see
services/bat_profile_content.py) means a bat detection is automatically
a recording the user can browse, automatically a life-list entry, and
automatically a field-guide entry, with no separate query logic to
maintain for any of those views.

Audio playback keeps the same Original/Enhanced toggle pattern as bird
clips, except here "Enhanced" means frequency-downshifted into human
hearing range, not noise-reduced (see
services/audio_processor.py:downshift_bat_clip for why this is a
fundamentally different operation for this content type).

No species identification — see bat_detector.py's module docstring for
why that isn't claimed here.
"""
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException,
    UploadFile, status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Recording, Detection, Device
from ..services.audio_processor import AudioProcessor

logger = logging.getLogger("chirp.bat_activity")
router = APIRouter()
processor = AudioProcessor()


def _event_out(rec: Recording) -> dict:
    """
    Shape kept identical to the old BatActivity-based response so any
    existing API consumer (the Devices.jsx panel, before its removal, or
    any external script hitting this endpoint directly) doesn't break.
    Pulls pulse-train stats out of Recording.bat_metadata, where they're
    now stored, instead of dedicated BatActivity columns.
    """
    meta = rec.bat_metadata or {}
    det = rec.detections[0] if rec.detections else None
    return {
        "id": rec.id,
        "device_id": rec.device_id,
        "started_at": rec.trigger_timestamp.isoformat() if rec.trigger_timestamp else None,
        "ended_at": (
            (rec.trigger_timestamp.timestamp() + rec.duration_seconds)
            if rec.trigger_timestamp else None
        ),
        "pulse_count": meta.get("pulse_count"),
        "peak_freq_hz": meta.get("peak_freq_hz"),
        "mean_pulse_duration_ms": meta.get("mean_pulse_duration_ms"),
        "swept_fraction": meta.get("swept_fraction"),
        "timing_cv": meta.get("timing_cv"),
        "likely_interference": meta.get("likely_interference", False),
        "sample_rate": rec.sample_rate,
        "has_audio": bool(rec.wav_path and os.path.exists(rec.wav_path)),
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "clip_path_exists": bool(det and det.clip_path),
    }


@router.get("")
def list_bat_activity(
    limit: int = 100,
    device_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> List[dict]:
    """
    List recent bat activity, newest first. Bat activity now lives in the
    Recording table (is_bat=True) rather than a standalone table — this
    endpoint is kept for any caller still pointed at it (e.g. during the
    transition away from the Devices.jsx "Bat Activity" panel), but new
    frontend code should just use GET /api/v1/recordings?is_bat=true,
    which gets the same data plus everything RecordingsList already knows
    how to render.
    """
    q = db.query(Recording).filter(Recording.is_bat == True)  # noqa: E712 — SQLAlchemy filter idiom
    if device_id:
        q = q.filter(Recording.device_id == device_id)
    recs = q.order_by(Recording.trigger_timestamp.desc()).limit(min(limit, 500)).all()
    return [_event_out(r) for r in recs]


@router.post("/upload")
async def upload_bat_activity(
    background_tasks: BackgroundTasks,
    started_at: str = Form(...),
    ended_at: str = Form(...),
    pulse_count: int = Form(...),
    peak_freq_hz: float = Form(...),
    sample_rate: int = Form(...),
    mean_pulse_duration_ms: Optional[float] = Form(None),
    swept_fraction: Optional[float] = Form(None),
    timing_cv: Optional[float] = Form(None),
    likely_interference: Optional[bool] = Form(False),
    device_serial: Optional[str] = Form(None),  # hostname/identifier, not a DB FK directly
    file: Optional[UploadFile] = File(None),
    x_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Device posts a detected bat activity event here. The audio file (if
    provided) should be the RAW captured audio at its true native sample
    rate — NOT pre-downshifted. The server generates the downshifted
    "enhanced" version on demand (and caches it), exactly like bird audio
    enhancement, so the choice of whether to downshift lives in one place.

    Creates one Recording (is_bat=True) + one Detection (common_name="Bat")
    rather than a BatActivity row — see module docstring for why.

    Authenticated the same way as the bird recording upload endpoint:
    Header X-API-Key, validated against Settings → Devices device keys
    (plus the legacy env-var key for backward compatibility).
    """
    from ..models import AppSettings as _AS
    _settings_row = db.query(_AS).filter(_AS.id == 1).first()
    _db_keys = [k.get("key") for k in (_settings_row.device_api_keys or [])] if _settings_row else []
    _env_key = settings.device_api_key
    _valid_keys = [k for k in _db_keys if k] + ([_env_key] if _env_key else [])
    if not x_api_key or x_api_key not in _valid_keys:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing X-API-Key")

    try:
        started = datetime.fromisoformat(started_at.replace("Z", ""))
        ended = datetime.fromisoformat(ended_at.replace("Z", ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="started_at/ended_at must be ISO 8601")
    duration_seconds = max(0.0, (ended - started).total_seconds())

    device_id = None
    if device_serial:
        dev = db.query(Device).filter(Device.hostname == device_serial).first()
        if dev:
            device_id = dev.id

    rec_id = str(uuid.uuid4())

    # Raw audio kept in its own dedicated directory (bat_clips_dir), same
    # convention as before this rewrite — separate from bird recordings_dir
    # since bat clips are a structurally different kind of file (no
    # pre-roll, far shorter, native ultrasonic sample rate).
    wav_path = None
    file_size_bytes = None
    if file is not None:
        data = await file.read()
        if data:
            bat_dir = Path(settings.bat_clips_dir)
            bat_dir.mkdir(parents=True, exist_ok=True)
            raw_path = bat_dir / f"{rec_id}_raw.wav"
            with open(raw_path, "wb") as f:
                f.write(data)
            wav_path = str(raw_path)
            file_size_bytes = raw_path.stat().st_size

    recording = Recording(
        id=rec_id,
        filename=f"bat_{rec_id[:8]}.wav",
        wav_path=wav_path or "",   # empty string, not None — matches Haikubox's
                                     # no-audio convention; downstream code already
                                     # checks truthiness, not None, before using wav_path
        json_path=None,
        spectrogram_path=None,
        trigger_timestamp=started,
        duration_seconds=duration_seconds,
        sample_rate=sample_rate,
        channels=1,
        pre_roll_seconds=0.0,
        file_size_bytes=file_size_bytes,
        device_count=1,
        device_id=device_id,
        is_bat=True,
        bat_metadata={
            "pulse_count": pulse_count,
            "peak_freq_hz": peak_freq_hz,
            "mean_pulse_duration_ms": mean_pulse_duration_ms,
            "swept_fraction": swept_fraction,
            "timing_cv": timing_cv,
            "likely_interference": likely_interference,
        },
        processing_status="pending" if wav_path else "done",  # nothing to process without audio
    )
    db.add(recording)

    det = Detection(
        id=str(uuid.uuid4()),
        recording_id=rec_id,
        common_name="Bat",
        scientific_name="Chiroptera",
        label="Bat",
        confidence=1.0,   # presence/absence detection, not a graded species call —
                          # see bat_detector.py: there's no species classifier to
                          # produce a meaningful confidence score against
        start_time=0.0,
        end_time=duration_seconds,
        source="device",
    )
    db.add(det)

    db.commit()
    db.refresh(recording)

    from ..cache import invalidate_detection_caches
    invalidate_detection_caches()

    logger.info(
        "Bat activity uploaded: %d pulses, peak ~%.0fkHz, clip=%s",
        pulse_count, peak_freq_hz / 1000, bool(wav_path),
    )

    # Queue the same background pipeline as bird recordings (BackgroundTasks,
    # same as the bird /upload endpoint) — it branches internally on is_bat
    # to run the bat-specific path (spectrogram, clip extraction, profile
    # creation; no BirdNET, no compression). Must go through BackgroundTasks
    # rather than a direct synchronous call: spectrogram generation is
    # CPU-bound matplotlib/librosa work, and calling it inline from this
    # async endpoint would block the event loop — and every other request
    # being served by this worker — for however long that takes.
    if wav_path:
        from .recordings import process_recording_bg
        background_tasks.add_task(process_recording_bg, rec_id)

    return {
        "id": rec_id,
        "status": "queued_for_processing" if wav_path else "done",
        "filename": recording.filename,
        "detections": 1,
    }


@router.get("/{event_id}/audio")
def get_bat_audio(event_id: str, db: Session = Depends(get_db)):
    """Raw audio at its true native sample rate — near-silent/inaudible to
    humans for most echolocation calls, since the frequency content is
    above human hearing. This is the "Original" side of the toggle."""
    rec = db.query(Recording).filter(Recording.id == event_id, Recording.is_bat == True).first()  # noqa: E712
    if not rec or not rec.wav_path or not os.path.exists(rec.wav_path):
        raise HTTPException(status_code=404, detail="No audio for this event")
    return FileResponse(
        rec.wav_path, media_type="audio/wav",
        filename=f"bat_{rec.id[:8]}_raw.wav",
        headers={"Cache-Control": "public, max-age=2592000, immutable"},
    )


@router.get("/{event_id}/audio/enhanced")
def get_bat_audio_enhanced(event_id: str, db: Session = Depends(get_db)):
    """
    Frequency-downshifted (time-expanded) audio — the "Enhanced" side of
    the toggle. Generated on first request and cached on disk.

    Uses the exact same cache path and stale-cache detection as the
    canonical /recordings/{id}/audio/enhanced endpoint (see
    api/recordings.py's stream_audio_enhanced and
    _is_stale_bat_enhanced_cache) rather than an independent
    implementation — a real inconsistency found during a pipeline audit:
    this endpoint previously cached to a different directory
    (bat_clips_dir) with no stale-cache detection at all, meaning a
    recording enhanced via this legacy endpoint before the downshift fix
    shipped would keep serving the old, wrong result forever, and
    wouldn't even share a cache with the canonical endpoint — two
    independent copies of the same conceptual cache that could silently
    diverge. Using the same path means both endpoints now genuinely share
    one cache file per recording, not two.
    """
    rec = db.query(Recording).filter(Recording.id == event_id, Recording.is_bat == True).first()  # noqa: E712
    if not rec or not rec.wav_path or not os.path.exists(rec.wav_path):
        raise HTTPException(status_code=404, detail="No audio for this event")

    from .recordings import _is_stale_bat_enhanced_cache
    cache_path = os.path.join(settings.enhanced_dir, f"{rec.id}_enhanced.wav")
    if os.path.exists(cache_path) and _is_stale_bat_enhanced_cache(cache_path, rec.wav_path):
        logger.info("Regenerating stale pre-fix bat-enhanced cache for event %s", event_id)
        try:
            os.remove(cache_path)
        except OSError:
            pass

    if not os.path.exists(cache_path):
        try:
            cache_path = processor.downshift_bat_clip(
                rec.wav_path, settings.enhanced_dir, rec.id,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Downshift failed: {e}")

    return FileResponse(
        cache_path, media_type="audio/wav",
        filename=f"bat_{rec.id[:8]}_enhanced.wav",
        headers={"Cache-Control": "public, max-age=2592000, immutable"},
    )


@router.get("/{event_id}/audio/dewobbled")
def get_bat_audio_dewobbled(event_id: str, db: Session = Depends(get_db)):
    """
    Experimental: the raw audio with the persistent AudioMoth/fan
    interference ridge attenuated (see AudioProcessor.remove_bat_wobble
    for the technique and its known tradeoff). A third option alongside
    Original/Enhanced — combinable with Enhanced, not exclusive with it
    (see /recordings/{id}/audio/dewobbled-enhanced, the canonical
    combined endpoint; this compat router doesn't duplicate that one,
    same as it doesn't duplicate the canonical enhanced endpoint's
    staleness-detection logic either — see get_bat_audio_enhanced above).

    Generated on first request and cached, same convention as
    /audio/enhanced. No staleness check against a prior "wrong" version
    the way /audio/enhanced needs one — this is a new endpoint with no
    pre-existing cached output from an earlier, different implementation
    to invalidate.
    """
    rec = db.query(Recording).filter(Recording.id == event_id, Recording.is_bat == True).first()  # noqa: E712
    if not rec or not rec.wav_path or not os.path.exists(rec.wav_path):
        raise HTTPException(status_code=404, detail="No audio for this event")

    cache_path = os.path.join(settings.enhanced_dir, f"{rec.id}_dewobbled.wav")
    if not os.path.exists(cache_path):
        try:
            cache_path = processor.remove_bat_wobble(
                rec.wav_path, settings.enhanced_dir, rec.id,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Wobble removal failed: {e}")

    return FileResponse(
        cache_path, media_type="audio/wav",
        filename=f"bat_{rec.id[:8]}_dewobbled.wav",
        headers={"Cache-Control": "public, max-age=2592000, immutable"},
    )


@router.delete("/{event_id}")
def delete_bat_activity(
    event_id: str,
    delete_files: bool = False,
    hard_delete: bool = False,
    db: Session = Depends(get_db),
):
    """
    Kept for API compatibility — genuinely calls the real
    DELETE /api/v1/recordings/{id} directly (not a separate
    reimplementation) so the two can never behave differently from each
    other. Defaults match that endpoint exactly: soft-delete
    (deleted_at set, restorable via POST /recordings/{id}/restore), files
    kept on disk unless delete_files=true. New frontend code should just
    call that endpoint directly instead of this one.
    """
    rec = db.query(Recording).filter(Recording.id == event_id, Recording.is_bat == True).first()  # noqa: E712
    if not rec:
        raise HTTPException(status_code=404, detail="Event not found")
    from .recordings import delete_recording
    delete_recording(event_id, delete_files=delete_files, hard_delete=hard_delete, db=db)
    return {"status": "deleted", "hard_delete": hard_delete, "delete_files": delete_files}
