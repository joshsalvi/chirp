"""
Live Detect — a real-time "walk around and see what's calling" mode,
matching the shape of Merlin Bird ID's own Sound ID feature. Genuinely
different from the rest of this app's detection flow, which is always
after the fact: a device (or a manual upload) hands over an already-
complete recording, and BirdNET analyzes the whole thing at once. Here,
short clips (a few seconds each) arrive one at a time while someone is
actively listening, and each one needs an answer back fast enough to
feel live.

Two audio sources, selected by the frontend:
  - "phone": the browser's own microphone, captured client-side and
    uploaded as a short clip per poll — for out-and-about listening,
    away from any deployed chirp-device.
  - "device": pulled server-side from a chirp-device's status_server,
    reusing the exact same `/listen` endpoint (and the same
    _fetch_device_listen_clip() helper) the Listen button already uses
    in Settings' mic check — for listening in through a yard's own,
    presumably better, microphone setup instead of a phone's.

Deliberately reuses the existing, proven pipeline rather than building a
parallel one: _run_server_birdnet() (the same engine the manual
/reanalyze endpoint and every device upload already use) does the
classification, and process_recording_bg() (the same background task
every device-uploaded recording goes through) does spectrogram/clip/
enrichment/notification once something's worth keeping. A
silent or bird-free clip is analyzed and then discarded — its
temp WAV deleted, its bare Recording row deleted — rather than leaving
hundreds of empty recordings behind after one listening session; only a
clip that contains a detection becomes a permanent
Recording, exactly like the feature is meant to work.
"""
import logging
import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Recording, BirdProfile
from .diagnostics import _fetch_device_listen_clip
from .recordings import _run_server_birdnet, process_recording_bg

logger = logging.getLogger(__name__)
router = APIRouter()


def _decode_to_wav(raw_bytes: bytes, dest_stem: Path, hint_ext: str) -> Path:
    """
    Whatever format the audio arrived in (webm/opus from a browser's
    MediaRecorder, or an already-clean WAV from chirp-device's own
    status_server), end up with a 48kHz mono 16-bit WAV file BirdNET
    can read — same normalization _process_manual_upload() and
    _run_server_birdnet() already do for every other entry point into
    this pipeline, applied here too so Live Detect clips get identical
    treatment. ffmpeg auto-detects the container format from the
    file's own content, not the extension, so a wrong/missing hint_ext
    is harmless — it only affects the temp filename, not decoding.

    The raw upload always lands at a name distinct from the final .wav
    path (a "_raw" suffix, unconditionally) — even when hint_ext is
    already ".wav" — specifically so ffmpeg is never asked to read and
    write the same file at once, which it can't do reliably.
    """
    wav_path = dest_stem.with_suffix(".wav")
    raw_path = dest_stem.with_name(dest_stem.name + "_raw").with_suffix(hint_ext or ".webm")
    with open(raw_path, "wb") as f:
        f.write(raw_bytes)

    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(raw_path), "-ar", "48000", "-ac", "1",
             "-sample_fmt", "s16", "-f", "wav", str(wav_path)],
            capture_output=True, timeout=180,
        )
    finally:
        try:
            os.unlink(raw_path)
        except OSError:
            pass

    if result.returncode != 0:
        # Reported directly, with a screenshot: the error shown was
        # entirely ffmpeg's own version/build banner ("ffmpeg version
        # 5.1.9... configuration: --prefix=/usr...") — useless for
        # diagnosing anything. ffmpeg always prints that banner FIRST,
        # before any per-file error, and the banner alone is
        # comfortably longer than 300 characters — so slicing the FIRST
        # 300 characters of stderr, as this did, could only ever show the
        # banner and never the useful message. Confirmed directly against
        # an ffmpeg failure: the error ("Invalid data found
        # when processing input") sits at the END of stderr, not the
        # start — slicing the LAST 300 characters instead reliably
        # captures it.
        stderr_text = result.stderr.decode(errors='replace').strip()
        raise HTTPException(400, f"Could not decode audio clip: {stderr_text[-300:]}")
    return wav_path


def device_location(db, device_id):
    """Where a Chirp device is, for Live Detect through it: the position in
    its most recent upload (devices report GPS with each recording), else
    the coordinates in its pushed config. None leaves BirdNET on the site."""
    from ..models import Device, Recording
    if not device_id:
        return None, None
    r = (db.query(Recording.latitude, Recording.longitude)
         .filter(Recording.device_id == device_id, Recording.latitude.isnot(None), Recording.longitude.isnot(None),
                 Recording.is_live_detect_clip.isnot(True))
         .order_by(Recording.trigger_timestamp.desc()).first())
    if r:
        return r[0], r[1]
    d = db.query(Device).filter(Device.id == device_id).first()
    bn = ((getattr(d, "managed_config", None) or {}).get("detection") or {}).get("birdnet") or {} if d else {}
    if bn.get("latitude") is not None and bn.get("longitude") is not None:
        return float(bn["latitude"]), float(bn["longitude"])
    return None, None


@router.post("/analyze")
async def live_detect_analyze(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(None, description="Short audio clip: required when source='phone'; with source='device', station audio the app already fetched"),
    source: str = Form("phone", description="'phone' (uploaded clip) or 'device' (pull live from a chirp-device mic)"),
    device_id: Optional[str] = Form(None, description="Required when source='device'"),
    mic_name: Optional[str] = Form(None, description="Required when source='device' — exact mic name as shown in mic check"),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    place_name: Optional[str] = Form(None, description="Where the phone is, e.g. a park or town (Chirp Live)"),
    min_confidence: Optional[float] = Form(None, description="Overrides the server's own BirdNET confidence threshold for this clip only — used by Live Detect's sensitivity slider, never persisted, never affects regular recordings"),
    db: Session = Depends(get_db),
):
    """
    Analyze one short clip. If BirdNET finds anything, the clip becomes a
    permanent Recording (spectrogram/clips/enrichment/notification
    all run normally in the background, same as any other recording) and
    its detections are returned immediately. If it finds nothing, nothing
    is kept — the response just says so.
    """
    if source == "device" and file is not None:
        # Station audio an app already fetched and played (Chirp Live): the
        # clip comes with the request, credited to the station.
        if not device_id:
            raise HTTPException(400, "device_id is required when source='device'")
        from ..models import Device
        if not db.query(Device).filter(Device.id == device_id).first():
            raise HTTPException(404, "Station not found")
        audio_bytes = await file.read()
        hint_ext = os.path.splitext(file.filename or "")[1].lower() or ".wav"
    elif source == "device":
        if not device_id or not mic_name:
            raise HTTPException(400, "device_id and mic_name are both required when source='device'")
        audio_bytes = await _fetch_device_listen_clip(device_id, mic_name, db)
        hint_ext = ".wav"  # status_server.py's /listen always returns a WAV
    elif source == "phone":
        if file is None:
            raise HTTPException(400, "file is required when source='phone'")
        audio_bytes = await file.read()
        hint_ext = os.path.splitext(file.filename or "")[1].lower()
    else:
        raise HTTPException(400, f"Unknown source {source!r} — expected 'phone' or 'device'")

    if not audio_bytes:
        raise HTTPException(400, "No audio data received")

    # ffmpeg and BirdNET are blocking; run them in a worker thread so one
    # clip doesn't stall every other request (session saves included).
    return await run_in_threadpool(
        _analyze_clip, background_tasks, audio_bytes, hint_ext, source,
        device_id, latitude, longitude, min_confidence, db, place_name)


def _clean_place(name):
    """A place name from a phone, one short line."""
    name = " ".join((name or "").split())[:120]
    return name or None


def _analyze_clip(background_tasks, audio_bytes, hint_ext, source, device_id,
                  latitude, longitude, min_confidence, db, place_name=None):
    rec_dir = Path(settings.recordings_dir)
    rec_dir.mkdir(parents=True, exist_ok=True)
    rec_id = str(uuid.uuid4())
    dest_stem = rec_dir / f"livedetect_{rec_id}"

    wav_path = _decode_to_wav(audio_bytes, dest_stem, hint_ext)

    try:
        import soundfile as sf
        info = sf.info(str(wav_path))
        duration = info.duration
        sample_rate = info.samplerate
    except Exception:
        duration, sample_rate = 0.0, 48000

    # Phone Live Detect sends the phone's GPS; through a Chirp device, use
    # where that device is.
    if source == "device" and (latitude is None or longitude is None):
        latitude, longitude = device_location(db, device_id)

    recording = Recording(
        id=rec_id,
        filename=wav_path.name,
        wav_path=str(wav_path),
        device_id=device_id if source == "device" else None,
        trigger_timestamp=datetime.utcnow(),
        duration_seconds=duration,
        sample_rate=sample_rate,
        channels=1,
        pre_roll_seconds=0.0,
        device_count=1,
        processing_status="pending",
        latitude=latitude,
        longitude=longitude,
        place_name=_clean_place(place_name),
        is_bat=False,
        is_live_detect_clip=True,
    )
    db.add(recording)
    db.commit()

    # Fast, synchronous BirdNET pass — cheap on a clip this short, and
    # the whole point of Live Detect is an answer back before the next
    # poll cycle, not a "check back later" background job for this part.
    # The phone's slider is on BirdNET 2.4's scale; v3 uses its own threshold.
    det_count = _run_server_birdnet(rec_id, db, replace_device_detections=True, min_confidence_override=min_confidence,
                                    override_applies_to_v3=False)

    if det_count == 0:
        try:
            os.unlink(wav_path)
        except OSError:
            pass
        db.delete(recording)
        db.commit()
        return {"detected": False, "detections": []}

    # A detection — finish the normal pipeline (spectrogram, clips,
    # enrichment, live-notification broadcast) in the background, exactly
    # like any device-uploaded recording. Re-runs BirdNET a second time
    # internally (its own Step 0) — a deliberate, accepted redundancy in
    # exchange for reusing this pipeline completely unmodified rather
    # than threading a "skip re-analysis, I already did it" flag through
    # code every other recording type also depends on; the cost is
    # negligible for a clip this short.
    background_tasks.add_task(process_recording_bg, rec_id)

    db.refresh(recording)

    # Photo + profile_id per species — looked up in one batched query
    # rather than per-detection, and resolved the exact same way
    # profile_to_out() (birds.py) already resolves a profile's photo_url,
    # so a species shown here looks identical to how it's shown
    # everywhere else in the app (local upload takes priority over a
    # cached remote URL). A brand-new species with no BirdProfile row
    # yet (enrichment hasn't created/populated one) simply has no photo
    # here — the frontend already has an icon fallback for that.
    names = {d.common_name for d in recording.detections}
    profiles = db.query(BirdProfile).filter(BirdProfile.common_name.in_(names)).all() if names else []
    profile_by_name = {}
    for p in profiles:
        if p.common_name in profile_by_name:
            continue  # multiple profile rows can share a common_name in edge cases — first one wins, matching dict-building patterns elsewhere in this codebase
        photo_url = None
        if p.photo_path and os.path.exists(p.photo_path):
            photo_url = f"/api/v1/birds/{p.id}/photo"
        elif p.photo_url:
            photo_url = p.photo_url
        profile_by_name[p.common_name] = {"profile_id": p.id, "photo_url": photo_url}

    return {
        "detected": True,
        "recording_id": rec_id,
        "detections": [
            {
                "common_name": d.common_name,
                "scientific_name": d.scientific_name,
                "confidence": d.confidence,
                **profile_by_name.get(d.common_name, {"profile_id": None, "photo_url": None}),
            }
            for d in recording.detections
        ],
    }


def _process_live_session_bg(rec_id: str):
    """
    Spectrogram-only background step for a saved Live Detect session —
    deliberately NOT the full process_recording_bg(). That function's
    own first step re-runs BirdNET on the whole file with
    replace_device_detections=True, which would delete the exact
    detections save_session() just carefully re-parented from each
    original small clip and replace them with a fresh, from-scratch
    re-analysis of the combined audio. Every species here was already
    detected, enriched, and (if applicable) already triggered a
    notification during the live session itself — this step only needs
    to give the new combined recording a spectrogram to look at,
    with the moved detections' now-session-relative timestamps
    overlaid on it.
    """
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        rec = db.query(Recording).filter(Recording.id == rec_id).first()
        if not rec:
            return
        rec.processing_status = "processing"
        db.commit()
        try:
            from .recordings import processor
            from ..models import AppSettings
            _live_settings = db.query(AppSettings).filter(AppSettings.id == 1).first()
            _live_palette = getattr(_live_settings, "detection_color_palette", None) or "vivid"
            dets_as_dicts = [
                {"common_name": d.common_name, "confidence": d.confidence,
                 "start_time": d.start_time, "end_time": d.end_time}
                for d in rec.detections
            ]
            spec_path = processor.generate_spectrogram(
                rec.wav_path, settings.spectrograms_dir, rec_id,
                detections=dets_as_dicts or None,
                color_palette=_live_palette,
            )
            rec.spectrogram_path = spec_path
            # Ready to view now; the thumbnail and enhanced audio follow.
            rec.processing_status = "done"
            db.commit()
            try:
                processor.generate_spectrogram(
                    rec.wav_path, settings.spectrograms_dir, rec_id,
                    detections=dets_as_dicts or None, thumb=True,
                    color_palette=_live_palette,
                )
            except Exception as e_thumb:
                logger.warning("Live session thumbnail spectrogram failed for %s: %s", rec_id, e_thumb)
            # Pre-generates the same enhanced (bandpass + noise-reduced)
            # audio the "Enhanced" toggle on the recording page already
            # produces on-demand for any recording — see
            # stream_audio_enhanced() in recordings.py, completely
            # unchanged here. A Live Detect session can run several
            # minutes, several times longer than the short clips that
            # toggle usually runs against, so generating it now means
            # it's instantly ready the first time it's clicked,
            # rather than making that click wait on spectral-gating
            # noise reduction over the whole file. Best-effort: if this
            # fails, the endpoint's own on-demand generation is still
            # there as a fallback, so a failure here isn't fatal to the
            # session save itself.
            try:
                # Same cache id and scope as /audio/enhanced (noise reduction only)
                from ..services.audio_processor import DSP_VERSION
                processor.enhance_audio(rec.wav_path, settings.enhanced_dir, f"{rec_id}_{DSP_VERSION}",
                                        apply_bandpass=False)
            except Exception as e_enh:
                logger.warning("Live session enhanced-audio pre-generation failed for %s: %s", rec_id, e_enh)
        except Exception as e:
            logger.warning("Live session spectrogram failed for %s: %s", rec_id, e)
        # "done", not "completed" — processing_status is a DB enum
        # (models.py's proc_status: pending/processing/done/error only).
        # Caught this directly via a test: an invalid value here doesn't
        # fail at write time, only the NEXT time the row is read back,
        # which would have meant a working save followed by a broken
        # Recordings list or detail page the moment anyone looked at it.
        rec.processing_status = "done"
        db.commit()
    finally:
        db.close()


@router.post("/save-session")
def save_session(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The full continuous session audio, start to stop"),
    recording_ids: str = Form(..., description="JSON array of the small per-detection Recording ids created during this session"),
    session_start: str = Form(..., description="ISO datetime the session (and this audio file) began"),
    device_id: Optional[str] = Form(None),
    latitude: Optional[float] = Form(None, description="Phone location when Live Detect started, if the person allowed it"),
    longitude: Optional[float] = Form(None),
    place_name: Optional[str] = Form(None, description="Where the phone was, e.g. a park or town (Chirp Live)"),
    db: Session = Depends(get_db),
):
    """
    Consolidates a Live Detect session into one Recording, on request
    when the person stops listening (only offered client-side if at
    least one detection happened) — replacing the scatter of tiny
    per-detection clips the session created with a single continuous
    recording covering the whole walk, detections included.

    Each original small clip's own detections are re-parented onto the
    new combined recording with their timestamps shifted by that clip's
    offset into the session (derived from its own trigger_timestamp
    relative to session_start — not something the frontend needs to
    track and send separately), then the small clips themselves are
    deleted so this is one recording per session, not an
    additional summary sitting alongside them.
    """
    import json
    try:
        ids = json.loads(recording_ids)
        if not isinstance(ids, list) or not ids:
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(400, "recording_ids must be a non-empty JSON array of recording ids")

    try:
        session_start_dt = datetime.fromisoformat(session_start.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(400, "session_start must be a valid ISO datetime")

    old_recordings = db.query(Recording).filter(Recording.id.in_(ids)).all()
    if not old_recordings:
        # Sent again after it was saved (the phone lost the reply, e.g. it
        # went to sleep): the clips are gone and the session recording
        # starting at this moment is the answer.
        done = (db.query(Recording)
                .filter(Recording.is_live_session.is_(True), Recording.trigger_timestamp == session_start_dt,
                        Recording.deleted_at.is_(None))
                .first())
        if done:
            return {"recording_id": done.id, "duration_seconds": done.duration_seconds,
                    "detections_moved": 0, "already_saved": True}
        raise HTTPException(404, "None of the given recording_ids were found")

    # Plain def (worker thread): the ffmpeg decode and file deletes below
    # are blocking.
    audio_bytes = file.file.read()
    if not audio_bytes:
        raise HTTPException(400, "No audio data received")

    rec_dir = Path(settings.recordings_dir)
    rec_dir.mkdir(parents=True, exist_ok=True)
    rec_id = str(uuid.uuid4())
    dest_stem = rec_dir / f"livedetect_session_{rec_id}"
    hint_ext = os.path.splitext(file.filename or "")[1].lower() or ".webm"
    wav_path = _decode_to_wav(audio_bytes, dest_stem, hint_ext)

    try:
        import soundfile as sf
        info = sf.info(str(wav_path))
        duration = info.duration
        sample_rate = info.samplerate
    except Exception:
        duration, sample_rate = 0.0, 48000

    if device_id and (latitude is None or longitude is None):
        latitude, longitude = device_location(db, device_id)

    new_recording = Recording(
        id=rec_id,
        filename=wav_path.name,
        wav_path=str(wav_path),
        device_id=device_id,
        trigger_timestamp=session_start_dt,
        duration_seconds=duration,
        sample_rate=sample_rate,
        channels=1,
        pre_roll_seconds=0.0,
        device_count=1,
        processing_status="pending",
        is_bat=False,
        is_live_session=True,
        latitude=latitude,
        longitude=longitude,
        place_name=_clean_place(place_name) or next((r.place_name for r in old_recordings if getattr(r, "place_name", None)), None),
    )
    db.add(new_recording)
    db.flush()  # new_recording.id needs to exist before detections reference it below

    moved = 0
    for old_rec in old_recordings:
        # Clamped to 0 rather than allowed negative — clock skew between
        # when a clip's own trigger_timestamp got stamped and the
        # session's own start could otherwise push a detection to a
        # timestamp before the combined audio even begins, which
        # nothing downstream expects or can sensibly display.
        offset = max(0.0, (old_rec.trigger_timestamp - session_start_dt).total_seconds())
        for det in list(old_rec.detections):
            det.recording_id = new_recording.id
            det.start_time = (det.start_time or 0.0) + offset
            det.end_time = (det.end_time or det.start_time or 0.0) + offset
        moved += 1
    db.commit()

    # Every detection has been moved onto the new combined recording —
    # the old per-clip recordings are now empty shells; remove them and
    # their (now-redundant) files.
    from ..services.file_cleanup import delete_recordings
    delete_recordings(db, list(old_recordings))

    background_tasks.add_task(_process_live_session_bg, rec_id)

    db.refresh(new_recording)
    return {
        "recording_id": new_recording.id,
        "duration_seconds": duration,
        "detections_moved": moved,
    }
