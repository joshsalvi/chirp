"""
Chirp Server — Recordings API
Handles upload from Pi devices and retrieval for the WebGUI.
"""
import re
import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form,
                     Header, HTTPException, Query, Request, Response, UploadFile, status)
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..database import get_db
from ..models import Detection, Recording, BirdProfile, AppSettings, Comment
from ..services.audio_processor import AudioProcessor, recommended_high_pass_hz, DSP_VERSION, compute_snr_db
from ..services import ai_enhance
from ..services.recorded_time import parse_recorded_at, time_from_filename
from ..services.call_reanalysis import tidy_stored_note, overall_rating, species_ratings

logger = logging.getLogger("chirp.api.recordings")

# BirdNET runs go through services/birdnet_pass (one Analyzer, one lock,
# owl-aware location filter and band-limited owl scoring).
from ..services.birdnet_pass import (run_birdnet as _run_birdnet_pass,
                                     NIGHT_SPECIES_MIN_CONF, NIGHT_CALLER_RE,
                                     night_rules, species_required, uses_night_floor)

from . import moderation as _mod
from .auth import get_current_user as _current_user

router = APIRouter()
processor = AudioProcessor()


def _nr_cache_id(recording_id: str, is_bat: bool = False) -> str:
    """Cache id for a recording's Enhanced audio. Versioned with DSP_VERSION
    so an algorithm change regenerates it; bats keep the plain id since
    their Enhanced is a frequency downshift that DSP_VERSION doesn't touch."""
    return recording_id if is_bat else f"{recording_id}_{DSP_VERSION}"


# Which recordings with nothing shown (no detection at the display
# threshold) survive the empty-recording purge. Only an owl the server pass
# kept under its owl rules (OWL_MIN_CONF plus a hoot at the owl's pitch):
# that's checked evidence. Everything else under the display threshold
# goes, including night callers the server kept at its 0.10 night floor and
# device-only owls: at night, background noise scores as Common Nighthawk
# or several owls at 0.10-0.18 in window after window (0.5.10.i).
_PURGE_PROTECTED_RE = NIGHT_CALLER_RE
_OWL_NAME_RE = re.compile(r"\bOwl\b")


def _night_caller_protects(name: str, conf: float, source: str, server_near: dict = None,
                           night: Optional[dict] = None) -> bool:
    """Does this detection (under the display threshold) keep its recording
    out of the empty-recording purge? Only an owl the server kept under its
    owl rules, and only while owls use the night-caller floor (night: the
    night_rules() of the settings; None means the default rule)."""
    from ..services.birdnet_pass import OWL_MIN_CONF, is_low_owl
    if source != "server" or not is_low_owl(name or "") or conf < OWL_MIN_CONF:
        return False
    return uses_night_floor(name, **(night or {}))


def _purge_protected_species(rec, db=None) -> Optional[str]:
    night = None
    if db is not None:
        from ..models import AppSettings as _ASp
        night = night_rules(db.query(_ASp).filter(_ASp.id == 1).first())
    for d in getattr(rec, "detections", None) or []:
        if _night_caller_protects(d.common_name, float(d.confidence or 0),
                                  getattr(d, "source", "device") or "device", night=night):
            return d.common_name
    return None


# Audio formats that change BirdNET scores slightly on re-analysis. The
# upload pass runs on the original WAV; compression (Opus by default) comes
# after it, so a later re-analysis reads different audio.
_LOSSY_EXTS = (".opus", ".ogg", ".mp3", ".m4a", ".aac")


def _prior_server_detections(db, rec_id: str) -> list:
    """This recording's current server detections, as run_birdnet's prior."""
    return [{"common_name": d.common_name, "scientific_name": d.scientific_name,
             "label": d.label, "confidence": float(d.confidence or 0),
             "start_time": float(d.start_time or 0), "end_time": float(d.end_time or 0)}
            for d in db.query(Detection).filter(Detection.recording_id == rec_id,
                                                Detection.source == "server").all()]


def _drop_superseded_device_detections(db, rec_id: str, raw: list, v3: bool = False) -> None:
    """With server_reanalyze_delete_device on, after a server pass: device
    owls go unless the server pass found that owl too (its owl rules are
    checked against field recordings; the device's aren't: in two weeks at
    Natick, 1,367 of 1,376 device owls the server didn't reproduce were
    daytime noise). When the pass found something, the other device
    detections go too, except night callers it didn't reproduce, so a found
    Blue Jay doesn't erase a device nightjar.

    v3: the pass was BirdNET v3. Then every station detection v3 didn't
    reproduce goes, found something or not, night callers included: the
    station runs BirdNET 2.4 at its own lower threshold (its 38% Mourning
    Dove, its 35% daytime Common Nighthawk in October), and v3 has its own
    night and owl handling."""
    from ..models import AppSettings as _AS2
    _s2 = db.query(_AS2).filter(_AS2.id == 1).first()
    if not (bool(getattr(_s2, "server_reanalyze_delete_device", True)) if _s2 else True):
        return
    server_names = {d.get("common_name", "") for d in raw}
    for dd in db.query(Detection).filter(Detection.recording_id == rec_id,
                                         Detection.source == "device").all():
        if _OWL_NAME_RE.search(dd.common_name or ""):
            db.delete(dd)
            continue
        if not raw and not v3:
            continue
        if (not v3 and _PURGE_PROTECTED_RE.search(dd.common_name or "")
                and dd.common_name not in server_names
                and float(dd.confidence or 0) >= (
                    NIGHT_SPECIES_MIN_CONF if uses_night_floor(dd.common_name, **night_rules(_s2))
                    else float(getattr(_s2, "birdnet_min_confidence", 0.05) or 0.05) if _s2 else 0.05)):
            continue
        db.delete(dd)
    db.commit()


def _normalized_48k(src: str) -> Optional[str]:
    """48 kHz mono 16-bit WAV copy of src in a temp file (caller deletes), or None."""
    fd, out = tempfile.mkstemp(suffix="_48k.wav", prefix="chirp_analysis_")
    os.close(fd)
    try:
        r = subprocess.run(["ffmpeg", "-y", "-i", src, "-ac", "1", "-ar", "48000",
                            "-sample_fmt", "s16", "-f", "wav", out],
                           capture_output=True, timeout=120)
        if r.returncode == 0 and os.path.getsize(out) > 0:
            return out
    except Exception as e:
        logger.warning("ffmpeg normalisation failed for %s: %s", src, e)
    try:
        os.unlink(out)
    except OSError:
        pass
    return None


_AUDIO_TYPES = {".wav": "audio/wav", ".flac": "audio/flac", ".opus": "audio/ogg",
                ".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac"}


def _merge_with_original_pass(raw: list, original_path: str, diag: dict, *, lat, lon, when,
                              min_conf, sensitivity, overlap, rec_id: str,
                              rules: Optional[dict] = None) -> list:
    """raw (from AI-Enhanced audio) merged with a pass on the original audio:
    every detection either pass found, at the higher score per species and
    window. diag's best scores are merged the same way."""
    wav = _normalized_48k(original_path)
    if not wav:
        return raw
    try:
        d2: dict = {}
        orig = _run_birdnet_pass(wav, lat=lat, lon=lon, when=when, min_conf=min_conf,
                                 sensitivity=sensitivity, overlap=overlap, diag=d2,
                                 **(rules or {}))
    except Exception as e:
        logger.warning("Original-audio pass failed for %s: %s", rec_id, e)
        return raw
    finally:
        try:
            os.unlink(wav)
        except OSError:
            pass
    merged = {(d.get("common_name"), round(float(d.get("start_time", 0.0)), 2)): d for d in raw}
    added = 0
    for d in orig:
        key = (d.get("common_name"), round(float(d.get("start_time", 0.0)), 2))
        have = merged.get(key)
        if have is None:
            merged[key] = d
            added += 1
        elif float(d.get("confidence", 0)) > float(have.get("confidence", 0)):
            merged[key] = d
    for name, v in (d2.get("best") or {}).items():
        diag.setdefault("best", {})[name] = max(v, diag.get("best", {}).get(name, 0.0))
    diag["not_expected"] = set(diag.get("not_expected") or ()) & set(d2.get("not_expected") or ())
    nm = {(n["common_name"]): n for n in (d2.get("near_misses") or [])}
    for n in diag.get("near_misses") or []:
        if n["common_name"] not in nm or n["confidence"] > nm[n["common_name"]]["confidence"]:
            nm[n["common_name"]] = n
    diag["near_misses"] = sorted(nm.values(), key=lambda n: -n["confidence"])[:10]
    logger.info("Re-analysis of %s: AI-Enhanced pass %d, original pass %d, %d only on the original",
                rec_id, len(raw), len(orig), added)
    return sorted(merged.values(), key=lambda d: (float(d.get("start_time", 0.0)),
                                                  -float(d.get("confidence", 0.0))))


def _log_reanalysis_changes(rec_id: str, before: list, after: list, diag: dict,
                            min_conf: float, display_min: float = 0.0,
                            thresholds: Optional[dict] = None, night: Optional[dict] = None) -> list:
    """Log one line per species a re-analysis removed, with the reason, and a
    summary; return the per-species changes for the recording's history.
    before: (name, source, confidence, start); after: the rows the
    recording has now (new server rows plus any device rows kept)."""
    thresholds = thresholds or {}
    now_best: dict = {}
    for d in after:
        now_best[d["common_name"]] = max(now_best.get(d["common_name"], 0.0), d.get("confidence", 0.0))
    now = set(now_best)
    was_best: dict = {}
    for name, _src, conf, _start in before:
        was_best[name] = max(was_best.get(name, 0.0), conf)
    gone: dict = {}
    for name, source, conf, start in before:
        if name not in now and conf > gone.get(name, (None, -1))[1]:
            gone[name] = (source, conf, start)
    best = diag.get("best", {})
    changes = []
    for name, (source, conf, start) in sorted(gone.items()):
        if name in diag.get("not_expected", ()):
            why = "not expected at this location and week"
        elif name in best:
            need = species_required(name, min_conf, thresholds or {}, **(night or {}))
            why = f"best score now {best[name]:.2f}, needs {need:.2f}"
            if best[name] >= need:
                why += " (owl without a matching hoot, or outscored in its window)"
        elif name in (diag.get("owl_no_hoot") or {}):
            why = (f"no hoot at an owl pitch (full-band score "
                   f"{diag['owl_no_hoot'][name]:.2f})")
        else:
            why = f"no score above {diag.get('floor', min_conf):.2f}"
        logger.warning("Re-analysis of %s removed %s (%s detection, was %.2f at %.1f s): %s",
                       rec_id, name, source, conf, start, why)
        changes.append({"species": name, "change": "removed", "was": round(conf, 3),
                        "now": round(best[name], 3) if name in best else None,
                        "source": source, "reason": why})
    before_names = set(was_best)
    for name in sorted(before_names & now):
        entry = {"species": name, "change": "kept", "was": round(was_best[name], 3),
                 "now": round(now_best[name], 3)}
        if now_best[name] < display_min <= was_best[name]:
            logger.warning("Re-analysis of %s kept %s at %.2f, under the %.2f display threshold, "
                           "so it no longer shows", rec_id, name, now_best[name], display_min)
            entry["change"] = "hidden"
            entry["reason"] = f"under the {display_min:.2f} display threshold"
        changes.append(entry)
    for name in sorted(now - before_names):
        changes.append({"species": name, "change": "added", "was": None,
                        "now": round(now_best[name], 3),
                        **({"reason": f"under the {display_min:.2f} display threshold"}
                           if now_best[name] < display_min else {})})
    logger.info("Re-analysis of %s: %d species kept, %d added, %d removed",
                rec_id, len(before_names & now), len(now - before_names), len(gone))
    return changes


def _bn_rules(app_s) -> dict:
    """run_birdnet keyword arguments from AppSettings: per-species scores
    and the night-caller rule (Settings → Detection)."""
    r = night_rules(app_s)
    return {"species_min_conf": _species_thresholds(app_s),
            "night_mode": r["mode"], "night_species": r["per_species"]}


def _species_thresholds(app_s) -> dict:
    """AppSettings.birdnet_species_thresholds as {name: float}."""
    raw = getattr(app_s, "birdnet_species_thresholds", None) if app_s else None
    out = {}
    for k, v in (raw or {}).items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            pass
    return out


def _store_near_misses(db, rec_id: str, diag: dict, raw: list) -> None:
    """Replace this recording's near-miss rows with the latest pass's."""
    from ..models import NearMiss
    try:
        kept = {(d.get("common_name"), round(float(d.get("start_time", 0.0)), 2)) for d in raw}
        db.query(NearMiss).filter(NearMiss.recording_id == rec_id).delete(synchronize_session=False)
        for nm in diag.get("near_misses") or []:
            if (nm["common_name"], round(float(nm["start_time"]), 2)) in kept:
                continue
            db.add(NearMiss(recording_id=rec_id, common_name=nm["common_name"],
                            scientific_name=nm.get("scientific_name"), label=nm.get("label"),
                            confidence=float(nm["confidence"]), start_time=float(nm["start_time"]),
                            end_time=float(nm["end_time"]), threshold=nm.get("threshold"),
                            reason=nm.get("reason"), band=nm.get("pass")))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("Near-miss logging failed for %s: %s", rec_id, e)


def _detection_snapshot(db, rec_id: str) -> list:
    """Every column of a recording's detections, for Undo re-analysis."""
    return [{"id": d.id, "common_name": d.common_name, "scientific_name": d.scientific_name,
             "label": d.label, "confidence": float(d.confidence or 0),
             "start_time": float(d.start_time or 0), "end_time": float(d.end_time or 0),
             "clip_path": d.clip_path, "source": d.source or "device"}
            for d in db.query(Detection).filter(Detection.recording_id == rec_id).all()]


def _sweep_enhanced(rec) -> int:
    """Remove a recording's (and its detections') Enhanced / AI Enhance /
    rumble-removed caches from enhanced_dir. Caches regenerate on demand."""
    try:
        from ..services.storage_manager import sweep_recording_derived
        return sweep_recording_derived(rec, settings.enhanced_dir)
    except Exception as e:
        logger.debug("Enhanced cache sweep failed for %s: %s", getattr(rec, "id", "?"), e)
        return 0


def _low_pitch_view(rec, scale: str) -> bool:
    """Spectrogram frequency spacing for the app's view: scale=mel or
    linear as asked; auto (the default) uses mel spacing when the recording
    has an owl or another low caller, so their calls aren't a thin line at
    the bottom of a 0-8 kHz image."""
    if scale == "mel":
        return True
    if scale == "linear":
        return False
    from ..services.audio_processor import LOW_FREQUENCY_CALLERS
    return any(d.common_name in LOW_FREQUENCY_CALLERS for d in (rec.detections or []))


def _low_suffix(path: str, low: bool) -> str:
    return path[:-4] + "_low.png" if low else path


def _enhanced_spec_path(recording_id: str) -> str:
    return os.path.join(settings.spectrograms_dir,
                        f"{recording_id}_spectrogram_enhanced_{DSP_VERSION}.png")


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class DetectionOut(BaseModel):
    id: str
    common_name: str
    scientific_name: Optional[str]
    label: str
    confidence: float
    start_time: float
    end_time: float
    clip_path: Optional[str]
    clip_url: Optional[str]
    source: str = "device"   # "device" | "server"
    # Bird profile enrichment (optional, populated if profile exists)
    bird_photo_url: Optional[str] = None
    bird_profile_id: Optional[str] = None

    class Config:
        from_attributes = True


class RecordingOut(BaseModel):
    id: str
    filename: str
    trigger_timestamp: datetime
    duration_seconds: float
    sample_rate: int
    channels: int
    pre_roll_seconds: float
    energy_db: Optional[float]
    snr_db: Optional[float]
    device_count: int
    label: Optional[str]
    notes: Optional[str]
    processing_status: str
    processing_error: Optional[str]
    top_species: Optional[str]
    top_species_photo_url: Optional[str] = None   # photo of the top-confidence species
    max_confidence: float
    spectrogram_url: Optional[str]
    audio_url: str
    detections: List[DetectionOut]
    created_at: datetime
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    place_name: Optional[str] = None        # phone recordings: where it was made
    deleted_at: Optional[datetime] = None   # None = active; set = soft-deleted
    archived_at: Optional[datetime] = None  # None = audio intact; set = audio deleted, everything else preserved
    file_size_bytes: Optional[int] = None   # current on-disk file size
    audio_format: Optional[str] = None      # 'wav', 'flac', 'opus' etc.
    is_bat: Optional[bool] = False           # True for bat-echolocation recordings (no species ID — see BirdProfile "Bat")
    bat_metadata: Optional[dict] = None       # pulse_count/peak_freq_hz/etc — only present when is_bat
    is_live_session: Optional[bool] = False   # True for a Live Detect session saved as one recording (see live_detect.py's save_session())
    ai_reanalysis_note: Optional[str] = None
    ai_reanalysis_rating: Optional[dict] = None   # overall_rating(): one rating from the AI's read and the audio check
    ai_reanalysis_species: List[dict] = []        # species_ratings(): one row per flagged species, primary first
    low_pitch_view: bool = False                  # auto spectrogram spacing is mel (an owl or other low caller is here)
    ai_reanalysis_enabled: Optional[bool] = False
    ai_reanalysis_error: Optional[str] = None
    ai_reanalysis_generated_at: Optional[datetime] = None
    ai_reanalysis_running: bool = False
    bat_profile_id: Optional[str] = None     # BirdProfile.id of the static "Bat" profile, for linking
    top_species_profile_id: Optional[str] = None  # BirdProfile.id of the top-confidence species profile
    device_id: Optional[str] = None         # API key id of the source device
    device_name: Optional[str] = None       # resolved device display name
    inat_observation_id:  Optional[str] = None   # iNaturalist observation integer ID
    inat_observation_url: Optional[str] = None   # full iNat observation URL
    has_audio: bool = True  # False for Haikubox detections (no WAV available)
    is_saved: bool = False  # kept out of automatic cleanup
    # Detection rows under min_confidence_display (detail view only), so the
    # page can say what's stored but hidden instead of showing nothing.
    hidden_detections: List[dict] = []
    display_min_confidence: float = 0.0

    class Config:
        from_attributes = True


def recording_to_out(rec: Recording, db=None, _app_settings=None, _profile_map: dict = None, _device_map: dict = None) -> RecordingOut:
    """Convert ORM Recording to Pydantic output schema.
    
    Performance: pass _app_settings, _profile_map, and _device_map when serializing
    multiple recordings in a list view to avoid redundant per-recording DB queries.
    """
    # Same "fetch it ourselves for a single-recording call, expect the
    # caller to pre-fetch for a batch/list" pattern as _profile_map below —
    # needed so ai_reanalysis_enabled resolves correctly even for callers
    # (like get_recording, the single-recording detail endpoint) that
    # don't pass _app_settings explicitly.
    if _app_settings is None and db is not None:
        from ..models import AppSettings as _AS_local
        _app_settings = db.query(_AS_local).filter(_AS_local.id == 1).first()
    # Use pre-fetched profile map, or build one for single-recording calls.
    # IMPORTANT: check `_profile_map is None` (was a map passed at all?), not
    # `not profile_map` (is the map non-empty?) — an empty dict is a valid
    # result from the caller's batch pre-fetch (e.g. a page of recordings
    # whose species haven't finished enrichment yet, so nothing matches).
    # Checking truthiness instead defeats the N+1 fix this shared-map
    # pattern exists for: every recording on the page would re-run its own
    # BirdProfile query, since an
    # empty dict is falsy just like "no map was ever passed."
    profile_map = _profile_map if _profile_map is not None else {}
    if _profile_map is None and db and rec.detections:
        labels = list({d.label for d in rec.detections if d.label})
        profiles = db.query(BirdProfile).filter(BirdProfile.label.in_(labels)).all() if labels else []
        profile_map = {p.label: p for p in profiles}

    # Use pre-fetched device map, or look up this one recording's device for
    # single-recording calls. Same is-None-vs-falsy fix as profile_map above.
    device_map = _device_map if _device_map is not None else {}
    if _device_map is None and db and rec.device_id:
        from ..models import Device
        d = db.query(Device).filter(Device.id == rec.device_id).first()
        if d:
            device_map = {d.id: d}

    # Use pre-fetched settings, or fetch once for single-recording calls
    app_s_disp = _app_settings
    if app_s_disp is None and db:
        try:
            app_s_disp = db.query(AppSettings).filter(AppSettings.id == 1).first()
        except Exception:
            pass
    display_min_conf = float(app_s_disp.min_confidence_display or 0.0) if app_s_disp else 0.0

    detections_out = []
    hidden_out = []
    for d in rec.detections:
        if d.confidence < display_min_conf:
            if _profile_map is None:
                hidden_out.append({"common_name": d.common_name, "confidence": float(d.confidence),
                                   "start_time": float(d.start_time or 0), "end_time": float(d.end_time or 0),
                                   "source": d.source or "device"})
            continue
        clip_url = None
        if d.clip_path and os.path.exists(d.clip_path):
            clip_url = f"/api/v1/recordings/{rec.id}/clip/{d.id}"
        # Look up bird profile for photo
        bird_photo_url = None
        bird_profile_id = None
        bp = profile_map.get(d.label)
        if bp:
            bird_profile_id = bp.id
            if bp.photo_path and os.path.exists(bp.photo_path):
                bird_photo_url = f"/api/v1/birds/{bp.id}/photo"
            elif bp.photo_url:
                bird_photo_url = bp.photo_url

        detections_out.append(DetectionOut(
            id=d.id,
            common_name=d.common_name,
            scientific_name=d.scientific_name,
            label=d.label,
            confidence=d.confidence,
            start_time=d.start_time,
            end_time=d.end_time,
            clip_path=d.clip_path,
            clip_url=clip_url,
            source=d.source or "device",
            bird_photo_url=bird_photo_url,
            bird_profile_id=bird_profile_id,
        ))
    # Sort by confidence
    detections_out.sort(key=lambda x: x.confidence, reverse=True)

    spectrogram_url = None
    if rec.spectrogram_path and os.path.exists(rec.spectrogram_path):
        spectrogram_url = f"/api/v1/recordings/{rec.id}/spectrogram"

    return RecordingOut(
        id=rec.id,
        filename=rec.filename,
        trigger_timestamp=rec.trigger_timestamp,
        duration_seconds=rec.duration_seconds,
        sample_rate=rec.sample_rate,
        channels=rec.channels,
        pre_roll_seconds=rec.pre_roll_seconds,
        energy_db=rec.energy_db,
        snr_db=rec.snr_db,
        device_count=rec.device_count,
        label=rec.label,
        notes=rec.notes,
        processing_status=rec.processing_status,
        processing_error=rec.processing_error,
        # From visible detections only: the card's title and badge used to
        # come from rows the count and the detail page hide.
        top_species=(max(detections_out, key=lambda d: d.confidence).common_name
                     if detections_out else None),
        top_species_photo_url=(
            max(detections_out, key=lambda d: d.confidence).bird_photo_url
            if detections_out else None
        ),
        max_confidence=max((d.confidence for d in detections_out), default=0.0),
        spectrogram_url=spectrogram_url,
        audio_url=f"/api/v1/recordings/{rec.id}/audio",
        detections=detections_out,
        created_at=rec.created_at,
        latitude=rec.latitude,
        longitude=rec.longitude,
        place_name=getattr(rec, "place_name", None),
        deleted_at=rec.deleted_at,
        archived_at=getattr(rec, 'archived_at', None),
        device_id=rec.device_id,
        device_name=(lambda d: (d.name or d.hostname or rec.device_id) if d else None)(device_map.get(rec.device_id)) if rec.device_id else None,
        file_size_bytes=_get_file_size(rec.wav_path),
        audio_format=os.path.splitext(rec.wav_path)[1].lstrip('.').lower() if rec.wav_path else None,
        is_bat=bool(rec.is_bat),
        bat_metadata=rec.bat_metadata or None,
        is_live_session=bool(getattr(rec, 'is_live_session', False)),
        ai_reanalysis_note=tidy_stored_note(rec.ai_reanalysis_note),
        ai_reanalysis_rating=overall_rating(rec.ai_reanalysis_note, getattr(rec, "ai_reanalysis_verdict", None),
                                            max(detections_out, key=lambda d: d.confidence).common_name if detections_out else None),
        ai_reanalysis_species=_second_opinion_rows(rec, detections_out),
        low_pitch_view=(not rec.is_bat) and _low_pitch_view(rec, "auto"),
        ai_reanalysis_error=getattr(rec, "ai_reanalysis_error", None),
        ai_reanalysis_generated_at=getattr(rec, "ai_reanalysis_generated_at", None),
        ai_reanalysis_running=rec.id in _AI_RECHECK_RUNNING,
        ai_reanalysis_enabled=bool((getattr(_app_settings, 'ai_feature_providers', None) or {}).get('call_reanalysis')) if _app_settings else False,
        bat_profile_id=(
            next((d.bird_profile_id for d in detections_out if d.label == "Bat" and d.bird_profile_id), None)
            if rec.is_bat else None
        ),
        top_species_profile_id=(
            max(detections_out, key=lambda d: d.confidence).bird_profile_id
            if detections_out else None
        ),
        inat_observation_id=getattr(rec, 'inat_observation_id', None),
        inat_observation_url=getattr(rec, 'inat_observation_url', None),
        has_audio=bool(rec.wav_path),
        is_saved=bool(getattr(rec, "is_saved", False)),
        hidden_detections=sorted(hidden_out, key=lambda x: -x["confidence"])[:30],
        display_min_confidence=display_min_conf,
    )


# ── Device Upload Endpoint ────────────────────────────────────────────────────



@router.get("/auth-test")
def auth_test(
    x_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Test endpoint — returns whether the provided X-API-Key is valid.
    Use from the Pi: curl -H "X-API-Key: YOUR_KEY" https://YOUR-SERVER-ADDRESS/api/v1/recordings/auth-test
    """
    from ..models import AppSettings as _AS
    _settings_row = db.query(_AS).filter(_AS.id == 1).first()
    _db_keys = [k.get("key") for k in (_settings_row.device_api_keys or [])] if _settings_row else []
    _env_key = settings.device_api_key
    _valid_keys = [k for k in _db_keys if k] + ([_env_key] if _env_key else [])

    key_received = x_api_key or "(none)"
    valid = x_api_key in _valid_keys if x_api_key else False

    return {
        "authenticated": valid,
        "key_received_length": len(x_api_key) if x_api_key else 0,
        "key_received_preview": f"{x_api_key[:8]}...{x_api_key[-4:]}" if x_api_key and len(x_api_key) > 12 else key_received,
        "valid_key_count": len(_valid_keys),
        "valid_key_previews": [f"{k[:8]}...{k[-4:]} (len={len(k)})" for k in _valid_keys],
        "hint": "If authenticated=false, ensure key in config.yaml matches exactly (no extra spaces/quotes).",
    }

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_recording(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="WAV audio recording"),
    metadata: str = Form(..., description="JSON metadata string"),
    x_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Receive a recording from a Chirp device.
    Called by the device uploader with:
      - multipart/form-data: file (WAV) + metadata (JSON string)
      - Header X-API-Key: <device_api_key>
    """
    # Validate API key against DB device_api_keys table (set in Settings → Devices)
    # Also accepts the legacy env-var key for backward compatibility
    from ..models import AppSettings as _AS
    _settings_row = db.query(_AS).filter(_AS.id == 1).first()
    _db_keys = [k.get("key") for k in (_settings_row.device_api_keys or [])] if _settings_row else []
    _env_key = settings.device_api_key  # legacy env-var fallback
    _valid_keys = [k for k in _db_keys if k] + ([_env_key] if _env_key else [])
    if not x_api_key or x_api_key not in _valid_keys:
        logger.warning(
            "Upload rejected: key received='%s' (len=%d), valid keys=[%s]",
            x_api_key or "(none)",
            len(x_api_key) if x_api_key else 0,
            ", ".join(f"'{k[:6]}...{k[-4:]}' (len={len(k)})" for k in _valid_keys),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key. Generate one in Settings → Devices, or set DEVICE_API_KEY env var.",
        )

    # Resolve which real Device row this upload belongs to, from the same
    # api_key_id link /devices/pair uses to create/find that Device row —
    # this endpoint previously skipped that lookup entirely, so
    # Recording.device_id was NULL for every real-device recording
    # regardless of how many devices were paired or which key each one
    # used. That's why the Recordings-page device filter (dropdown)
    # returned zero results for a device that clearly had recordings — they
    # were never linked to it in the database.
    # Falls back to None only for the legacy env-var key (settings.device_api_key),
    # which has no corresponding device_api_keys entry/id to look up — the
    # exact same "unlinkable" case this always silently produced before.
    upload_device_id = None
    try:
        from ..models import Device
        _matching_key_entry = next(
            (k for k in (_settings_row.device_api_keys or []) if k.get("key") == x_api_key),
            None,
        ) if _settings_row else None
        if _matching_key_entry:
            _device_row = db.query(Device).filter(Device.api_key_id == _matching_key_entry["id"]).first()
            if _device_row:
                upload_device_id = _device_row.id
    except Exception as e:
        logger.warning("Could not resolve device_id for upload (key valid, lookup failed): %s", e)

    # Parse metadata
    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid metadata JSON: {e}")

    # Save WAV file
    rec_dir = Path(settings.recordings_dir)
    rec_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = Path(file.filename).name if file.filename else f"recording_{uuid.uuid4()}.wav"
    wav_path = rec_dir / safe_filename

    try:
        with open(wav_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    file_size_mb = wav_path.stat().st_size / (1024 * 1024)
    if file_size_mb > settings.max_upload_mb:
        wav_path.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail=f"File too large: {file_size_mb:.1f} MB")

    # Cross-check the device-reported duration against the actual WAV file
    # rather than trusting the metadata sidecar blindly. Root cause of a
    # real reported bug: the device computes duration_seconds from
    # wall-clock elapsed time, which can diverge from the real number of
    # samples actually written to the file (rolling-buffer underrun right
    # after startup, or per-channel buffer drift on multi-device setups) —
    # fixed at the source on the device side, but this is real
    # defense-in-depth so the server self-corrects even if a future device
    # bug reintroduces the same class of mismatch, instead of silently
    # propagating a wrong value to the title card.
    device_reported_duration = float(meta.get("duration_seconds", 0))
    real_duration = device_reported_duration
    try:
        import soundfile as _sf
        real_duration = float(_sf.info(str(wav_path)).duration)
        if abs(real_duration - device_reported_duration) > 0.05:
            logger.warning(
                "Recording %s: device-reported duration %.2fs differs from "
                "actual WAV file duration %.2fs — using the real file duration",
                safe_filename, device_reported_duration, real_duration,
            )
    except Exception as e:
        logger.warning(
            "Recording %s: could not verify duration against the real WAV "
            "file (%s) — falling back to device-reported value %.2fs",
            safe_filename, e, device_reported_duration,
        )

    # Save JSON sidecar if provided
    json_path = None
    json_str = json.dumps(meta, indent=2)
    jp = rec_dir / (wav_path.stem + ".json")
    with open(jp, "w") as f:
        f.write(json_str)
    json_path = str(jp)

    # Parse trigger timestamp — always normalize to naive UTC for storage
    ts_raw = meta.get("trigger_timestamp_utc") or meta.get("trigger_timestamp_local")
    try:
        from dateutil.parser import parse as parse_dt
        _ts = parse_dt(ts_raw) if ts_raw else datetime.utcnow()
        # If timezone-aware, convert to UTC and strip tzinfo
        if _ts.tzinfo is not None:
            import calendar
            _ts = datetime.utcfromtimestamp(calendar.timegm(_ts.utctimetuple()))
        # Sanity check: if local time was sent without tz and appears in the past by >12h,
        # check if it was actually local time from the server's TZ
        # Best-effort: just store what we got stripped of tz
        trigger_ts = _ts.replace(tzinfo=None)
    except Exception:
        trigger_ts = datetime.utcnow()

    # Create Recording row
    rec_id = str(uuid.uuid4())
    recording = Recording(
        id=rec_id,
        filename=safe_filename,
        wav_path=str(wav_path),
        json_path=json_path,
        trigger_timestamp=trigger_ts,
        duration_seconds=real_duration,
        sample_rate=int(meta.get("sample_rate", 48000)),
        channels=int(meta.get("channels", 2)),
        pre_roll_seconds=float(meta.get("pre_roll_seconds", 5.0)),
        file_size_bytes=wav_path.stat().st_size,
        energy_db=float(meta.get("energy_db", 0)) if meta.get("energy_db") else None,
        device_count=int(meta.get("device_count", 1)),
        device_id=upload_device_id,
        processing_status="pending",
    )
    db.add(recording)

    # Create Detection rows
    raw_detections = meta.get("detections", [])
    for det_data in raw_detections:
        det = Detection(
            id=str(uuid.uuid4()),
            recording_id=rec_id,
            common_name=det_data.get("common_name", "Unknown"),
            scientific_name=det_data.get("scientific_name"),
            label=det_data.get("label", ""),
            confidence=float(det_data.get("confidence", 0)),
            start_time=float(det_data.get("start_time", 0)),
            end_time=float(det_data.get("end_time", 3)),
            source="device",
        )
        db.add(det)

    db.commit()
    db.refresh(recording)

    from ..cache import invalidate_detection_caches
    invalidate_detection_caches()

    logger.info(
        "Received recording %s: %.1fs, %d detections",
        safe_filename, recording.duration_seconds, len(raw_detections)
    )

    # Queue background processing (spectrogram + clip extraction + enrichment)
    background_tasks.add_task(process_recording_bg, rec_id)

    # NOTE: WebSocket broadcast fires AFTER server BirdNET confirms detections,
    # inside process_recording_bg. We do NOT broadcast device-only detections.

    return {
        "id": rec_id,
        "status": "queued_for_processing",
        "filename": safe_filename,
        "detections": len(raw_detections),
    }


async def _broadcast_new_recording(rec_id: str, species: str, confidence: float):
    try:
        from ..main import manager
        await manager.broadcast({
            "type": "new_recording",
            "data": {"id": rec_id, "species": species, "confidence": confidence}
        })
    except Exception:
        pass



def _second_opinion_rows(rec, detections_out) -> list:
    """AI Second Opinion rows: each flagged species once, highest-confidence
    first, with its rating and photo."""
    if not rec.ai_reanalysis_note or not detections_out:
        return []
    top = max(detections_out, key=lambda d: d.confidence or 0)
    names, photos = [top.common_name], {}
    for d in sorted(detections_out, key=lambda d: d.start_time or 0):
        if d.common_name not in names:
            names.append(d.common_name)
    for d in detections_out:
        if d.bird_photo_url and d.common_name not in photos:
            photos[d.common_name] = d.bird_photo_url
    rows = species_ratings(rec.ai_reanalysis_note, getattr(rec, "ai_reanalysis_verdict", None), names)
    for r in rows:
        r["photo_url"] = photos.get(r["name"])
    return rows


def _get_file_size(wav_path: Optional[str]) -> Optional[int]:
    """Return current file size in bytes, or None if file doesn't exist."""
    if not wav_path:
        return None
    try:
        return os.path.getsize(wav_path)
    except OSError:
        return None


def _bn3_main(app_s) -> bool:
    """BirdNET v3 is the detection model unless Settings → Detection says 2.4."""
    return (getattr(app_s, "detection_model", None) or "birdnet3") == "birdnet3"


def _bn3_shadow(app_s) -> bool:
    """With BirdNET 2.4 as the model, optionally also score with v3 to compare."""
    return bool(app_s and getattr(app_s, "exp_birdnet3_shadow", False)) and not _bn3_main(app_s)


def _store_shadow(db, rec_id: str, wav_path: str, lat, lon, when, app_s, start_utc=None) -> int:
    """BirdNET v3 comparison pass (Settings → Detection, with 2.4): stored apart from
    the detections, for comparison only. Never raises."""
    try:
        from ..services import birdnet3
        from ..models import ShadowDetection
        if not birdnet3.installed():
            birdnet3.ensure_downloaded()
            return 0
        conf = float(getattr(app_s, "exp_birdnet3_min_conf", None) or birdnet3.DEFAULT_MIN_CONF)
        dets = birdnet3.analyze(wav_path, lat=lat, lon=lon, when=when, min_conf=conf, start_utc=start_utc)
        db.query(ShadowDetection).filter(ShadowDetection.recording_id == rec_id,
                                         ShadowDetection.model == "birdnet3").delete(synchronize_session=False)
        for d in dets:
            db.add(ShadowDetection(recording_id=rec_id, model="birdnet3", common_name=d["common_name"],
                                   scientific_name=d["scientific_name"], label=d["label"],
                                   confidence=d["confidence"], start_time=d["start_time"],
                                   end_time=d["end_time"]))
        rec = db.query(Recording).filter(Recording.id == rec_id).first()
        if rec:
            rec.shadow_checked_at = datetime.utcnow()
        db.commit()
        return len(dets)
    except Exception as e:
        db.rollback()
        logger.warning("BirdNET v3 shadow pass failed for %s: %s", rec_id, e)
        return 0


def _run_server_birdnet(rec_id: str, db, replace_device_detections: bool = True, min_confidence_override: float = None,
                        override_applies_to_v3: bool = True) -> int:
    """
    Run BirdNET analysis on the server using full settings (lat/lon + week-of-year filter,
    sensitivity, overlap). Optionally replaces device-sourced detections.
    Returns number of detections found.

    This is the same engine used by the manual /reanalyze endpoint, extracted so it
    can be called from the upload background task.

    min_confidence_override: for Live Detect's own sensitivity slider only — lets
    a single clip be analyzed at a lower bar than the server's own permanent-recording
    threshold, without touching that setting or affecting anything else. A live,
    disposable "did I hear something" check is much lower-stakes than a permanently
    saved Detection row, so it can reasonably tolerate more false positives in exchange
    for missing fewer real, brief calls.
    """
    import tempfile, subprocess, os
    from datetime import date as _date
    from ..models import AppSettings, Detection, Recording

    rec = db.query(Recording).filter(Recording.id == rec_id).first()
    if not rec:
        return 0

    wav_path = rec.wav_path
    if not wav_path or not os.path.exists(wav_path):
        logger.warning("_run_server_birdnet: wav file not found for %s: %s", rec_id, wav_path)
        return 0

    app_s = db.query(AppSettings).filter(AppSettings.id == 1).first()

    # Location: prefer recording GPS, fall back to server settings
    lat = rec.latitude or (app_s.latitude if app_s else None)
    lon = rec.longitude or (app_s.longitude if app_s else None)

    min_conf   = float(min_confidence_override) if min_confidence_override is not None else (float(app_s.birdnet_min_confidence or 0.05) if app_s else 0.05)
    overlap    = float(app_s.birdnet_overlap or 2.5) if app_s else 2.5
    sensitivity= float(app_s.birdnet_sensitivity or 1.5) if app_s else 1.5

    # Week-of-year filter follows the recording, not the day it's analysed
    rec_date = rec.trigger_timestamp.date() if rec.trigger_timestamp else _date.today()

    if lat and lon:
        logger.info(
            "Server BirdNET: lat=%.4f lon=%.4f date=%s min_conf=%.2f for %s",
            lat, lon, rec_date, min_conf, rec_id,
        )
    else:
        logger.info(
            "Server BirdNET: no location set (configure in Settings for species filtering) "
            "min_conf=%.2f for %s", min_conf, rec_id,
        )

    # Normalise audio to 48kHz mono PCM (birdnetlib requirement)
    analysis_wav = wav_path
    tmp_wav = None
    try:
        fd, tmp_wav = tempfile.mkstemp(suffix="_48k.wav", prefix="chirp_analysis_")
        os.close(fd)
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", wav_path,
             "-ac", "1", "-ar", "48000", "-sample_fmt", "s16", tmp_wav],
            capture_output=True, timeout=60,
        )
        if r.returncode == 0 and os.path.exists(tmp_wav) and os.path.getsize(tmp_wav) > 0:
            analysis_wav = tmp_wav
        else:
            logger.warning("ffmpeg normalisation failed for %s — using original", rec_id)
    except Exception as e:
        logger.warning("ffmpeg error for %s: %s — using original", rec_id, e)

    try:
        raw = None
        ran_bn3 = False
        if _bn3_main(app_s):
            # BirdNET v3, the default model (Settings → Detection). BirdNET
            # 2.4's owl rules and near-miss log don't apply to its scores.
            try:
                from ..services import birdnet3
                bn3_conf = float(min_confidence_override) \
                    if (min_confidence_override is not None and override_applies_to_v3) \
                    else float(getattr(app_s, "exp_birdnet3_min_conf", None) or birdnet3.DEFAULT_MIN_CONF)
                raw = birdnet3.analyze(wav_path, lat=lat, lon=lon, when=rec_date, min_conf=bn3_conf,
                                       start_utc=rec.trigger_timestamp)
                ran_bn3 = True
                logger.info("Server BirdNET v3 (main): %d detection(s) for %s", len(raw), rec_id)
            except Exception as e:
                logger.warning("BirdNET v3 unavailable for %s (%s) — using BirdNET 2.4", rec_id, e)
                raw = None
        if raw is None:
            prior = (_prior_server_detections(db, rec_id)
                     if wav_path.lower().endswith(_LOSSY_EXTS) else None)
            _diag: dict = {}
            raw = _run_birdnet_pass(analysis_wav, lat=lat, lon=lon, when=rec_date,
                                    min_conf=min_conf, sensitivity=sensitivity, overlap=overlap,
                                    prior=prior, diag=_diag, **_bn_rules(app_s))
            logger.info("Server BirdNET: %d detection(s) for %s", len(raw), rec_id)
            _store_near_misses(db, rec_id, _diag, raw)
            if _bn3_shadow(app_s) and not rec.is_live_detect_clip:
                _store_shadow(db, rec_id, wav_path, lat, lon, rec_date, app_s, rec.trigger_timestamp)

        # Remove stale server detections from any previous re-analysis
        db.query(Detection).filter(
            Detection.recording_id == rec_id,
            Detection.source == "server",
        ).delete(synchronize_session=False)
        db.commit()

        if replace_device_detections:
            _drop_superseded_device_detections(db, rec_id, raw, v3=ran_bn3)

        import uuid as _uuid
        for d in raw:
            label = d.get("label", "")
            det = Detection(
                id=str(_uuid.uuid4()),
                recording_id=rec_id,
                common_name=d.get("common_name", label.split("_")[0] if "_" in label else label),
                scientific_name=d.get("scientific_name", ""),
                label=label,
                confidence=float(d.get("confidence", 0.0)),
                start_time=float(d.get("start_time", 0.0)),
                end_time=float(d.get("end_time", 3.0)),
                source="server",
            )
            db.add(det)
        db.commit()
        from ..cache import invalidate_detection_caches
        invalidate_detection_caches()
        return len(raw)

    except Exception as e:
        logger.error("Server BirdNET analysis error for %s: %s", rec_id, e)
        return 0
    finally:
        if tmp_wav and os.path.exists(tmp_wav):
            try:
                os.unlink(tmp_wav)
            except OSError:
                pass


def process_recording_bg(rec_id: str):
    """Background task: generate spectrogram, extract clips, enrich species."""
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        rec = db.query(Recording).filter(Recording.id == rec_id).first()
        if not rec:
            return

        rec.processing_status = "processing"
        db.commit()

        # Compute the SNR quality signal for every recording, bat or bird —
        # see compute_snr_db's own docstring for the full reasoning. Cheap
        # (a few hundred ms even for a long recording) and best-effort: a
        # failure here logs and leaves it None, never blocks the rest of
        # this recording's real processing.
        try:
            rec.snr_db = compute_snr_db(rec.wav_path)
            db.commit()
        except Exception as e:
            logger.warning("compute_snr_db failed for %s: %s", rec_id, e)

        # Bat recordings get a separate, much simpler pipeline: no BirdNET
        # (there's no bird call to analyze), no species-specific spectrogram
        # overlay (no species ID exists to overlay), and no lossy compression
        # (Opus targets human hearing range and would either resample away or
        # silently discard everything above ~24kHz — see
        # services/storage_manager.py COMPRESS_PRESETS — destroying the only
        # thing that makes the recording worth keeping). Bat clips are tiny
        # pulse-train bursts anyway, so skipping compression costs negligible
        # storage. See generate_bat_spectrogram() for why the spectrogram
        # itself also can't reuse the bird code path unchanged.
        if rec.is_bat:
            _process_bat_recording_bg(rec, db, rec_id)
            return

        # 0. Server-side BirdNET re-analysis (if enabled in Settings)
        # Runs BEFORE spectrogram so the spectrogram shows server detections.
        # Uses full server BirdNET settings (lat/lon, week-of-year, sensitivity)
        # and replaces device detections with higher-quality server detections.
        # Capture device confidence BEFORE server BirdNET runs (it may delete device detections)
        _device_max_conf_pre = max(
            (d.confidence for d in rec.detections if d.source != "server"),
            default=0.0,
        )
        _server_det_count = 0
        try:
            from ..models import AppSettings as _AS
            _s = db.query(_AS).filter(_AS.id == 1).first()
            _reanalyze = getattr(_s, 'server_reanalyze_on_upload', True) if _s else True
            if _reanalyze:
                logger.info("Server re-analysis enabled — running BirdNET on %s", rec_id)
                _server_det_count = _run_server_birdnet(rec_id, db, replace_device_detections=True)
                # Refresh rec object after detections were modified
                db.expire(rec)
                rec = db.query(Recording).filter(Recording.id == rec_id).first()
        except Exception as _re:
            logger.warning("Server re-analysis failed for %s: %s — using device detections", rec_id, _re)

        # Broadcast to WebSocket clients ONLY when server BirdNET confirms a real bird.
        # process_recording_bg runs in a thread pool (sync), so we must schedule
        # the async broadcast back onto the main uvicorn event loop via
        # run_coroutine_threadsafe — NOT a new event loop (WS connections are
        # bound to the main loop and break on a foreign loop).
        if _server_det_count > 0:
            try:
                import asyncio as _asyncio
                from ..main import manager as _ws_mgr, _main_loop as _ml
                db.expire(rec)
                _rec_fresh = db.query(Recording).filter(Recording.id == rec_id).first()
                _top = _rec_fresh.top_species if _rec_fresh else "Unknown"
                _conf = _rec_fresh.max_confidence if _rec_fresh else 0.0
                if _ml is not None:
                    fut = _asyncio.run_coroutine_threadsafe(
                        _ws_mgr.broadcast({
                            "type": "new_recording",
                            "data": {"id": rec_id, "species": _top, "confidence": _conf},
                        }),
                        _ml,
                    )
                    fut.result(timeout=5)
            except Exception as _be:
                logger.debug("WS broadcast failed for %s: %s", rec_id, _be)


        try:
            # Apply display threshold so cached spectrogram matches what the user sees
            _spec_s = db.query(AppSettings).filter(AppSettings.id == 1).first()
            _spec_min_conf = float(getattr(_spec_s, 'min_confidence_display', 0.0) or 0.0) if _spec_s else 0.0
            _spec_palette = getattr(_spec_s, 'detection_color_palette', None) or 'vivid'
            dets_as_dicts = [
                {"common_name": d.common_name, "confidence": d.confidence,
                 "start_time": d.start_time, "end_time": d.end_time}
                for d in rec.detections
                if d.confidence >= _spec_min_conf
            ]
            spec_path = processor.generate_spectrogram(
                rec.wav_path,
                settings.spectrograms_dir,
                rec_id,
                detections=dets_as_dicts or None,
                color_palette=_spec_palette,
            )
            rec.spectrogram_path = spec_path
            # Also pre-build the thumbnail variant now, at upload time —
            # the recordings list grid view should never need to generate
            # one lazily on first view.
            try:
                processor.generate_spectrogram(
                    rec.wav_path,
                    settings.spectrograms_dir,
                    rec_id,
                    detections=dets_as_dicts or None,
                    thumb=True,
                    color_palette=_spec_palette,
                )
            except Exception as e_thumb:
                logger.warning("Thumbnail spectrogram failed for %s: %s", rec_id, e_thumb)
        except Exception as e:
            logger.warning("Spectrogram failed for %s: %s", rec_id, e)

        # 2. Extract clips for each detection
        for det in rec.detections:
            try:
                clip_path = processor.extract_clip(
                    rec.wav_path,
                    settings.clips_dir,
                    det.id,
                    det.start_time,
                    det.end_time,
                    padding=settings.clip_padding_seconds,
                )
                det.clip_path = clip_path
                db.add(det)
            except Exception as e:
                logger.debug("Clip extraction failed for %s: %s", det.id, e)

        rec.processing_status = "done"
        db.commit()

        # 3. Compress audio if enabled (WAV → FLAC/Opus in background)
        try:
            from ..models import AppSettings as _AS
            _s = db.query(_AS).filter(_AS.id == 1).first()
            if _s and getattr(_s, 'storage_compress_on_upload', True):
                _quality = getattr(_s, 'storage_compress_quality', 'lossless') or 'lossless'
                from ..services.storage_manager import compress_recording
                _new_path = compress_recording(rec.wav_path, _quality)
                if _new_path and _new_path != rec.wav_path:
                    # Delete original WAV after successful compression
                    try:
                        os.unlink(rec.wav_path)
                    except OSError:
                        pass
                    rec.wav_path = _new_path
                    try:
                        rec.file_size_bytes = os.path.getsize(_new_path)
                    except OSError:
                        pass
                    db.commit()
                    logger.info("Compressed recording %s → %s (size: %d bytes)", rec_id, _new_path, rec.file_size_bytes or 0)
        except Exception as _ce:
            logger.warning("Compression step failed for %s: %s", rec_id, _ce)

        # 4. Enrich bird profiles in background
        if settings.enrich_on_upload:
            labels = list({d.label for d in rec.detections})
            if labels:
                # Check which labels are genuinely new (no existing BirdProfile) BEFORE enrichment
                existing_labels = {
                    bp.label
                    for bp in db.query(BirdProfile.label).filter(BirdProfile.label.in_(labels)).all()
                }
                new_labels = set(labels) - existing_labels

                # Create enricher once, not per label
                from ..services.bird_enricher import BirdEnricher
                enricher = BirdEnricher(db)

                for label in labels:
                    try:
                        profile = enricher.ensure_profile(label)
                        # Only notify for genuinely new species (not previously in DB)
                        # Only email when this detection was server-confirmed
                        # (source == "server") to avoid emailing on device-only detections
                        if label in new_labels and profile:
                            _det = next(
                                (d for d in rec.detections
                                 if d.label == label and getattr(d, 'source', 'device') == 'server'),
                                None
                            )
                            if _det and _server_det_count > 0:
                                try:
                                    from ..services.email_service import notify_new_bird as _nb
                                    _nb(db,
                                        profile.common_name,
                                        profile.scientific_name or "",
                                        float(_det.confidence),
                                        photo_url=profile.photo_url)
                                except Exception as _ne:
                                    logger.debug("notify_new_bird failed: %s", _ne)
                                try:
                                    from ..services.push_notifications import send_push_to_all
                                    send_push_to_all(
                                        db,
                                        title=f"New bird: {profile.common_name}",
                                        body=f"Detected at {round(float(_det.confidence) * 100)}% confidence",
                                        url=f"/recordings/{rec.id}",
                                        tag="new-bird",
                                        user_filter=lambda u: getattr(u, "notify_new_bird_push", True) is not False,
                                    )
                                except Exception as _pe:
                                    logger.debug("push notify_new_bird failed: %s", _pe)
                    except Exception as e:
                        logger.debug("Enrichment failed for %s: %s", label, e)

        # 5. Auto-purge if enabled and recording has 0 server-side detections
        try:
            from ..models import AppSettings as _APurge
            _ps = db.query(_APurge).filter(_APurge.id == 1).first()
            if _ps and getattr(_ps, 'auto_purge_empty_recordings', False):
                # Use pre-captured device confidence (before server may have deleted detections)
                # and the server's return count. Purge only when:
                #   - server found 0 birds  AND
                #   - device's original confidence was low (< 0.65)
                # This correctly purges engine/noise recordings while keeping
                # any recording where the device was reasonably confident.
                _purge_threshold  = float(getattr(_ps, 'auto_purge_min_confidence', 0.65) or 0.65)
                _purge_all_device = bool(getattr(_ps, 'auto_purge_all_device', False))
                # Purge when: server found 0 birds AND (purge-all is on OR device was low-confidence)
                # Defensive haikubox_detection_id check: this code path is
                # confirmed to never run for Haikubox-imported recordings
                # today (haikubox_sync.py never calls process_recording_bg,
                # which is what contains this block), but excluding them
                # explicitly costs nothing and prevents a future change
                # from silently reintroducing the exact class of bug that
                # caused real Haikubox data loss elsewhere in this codebase.
                # Nothing shown: no detection at the display threshold (what
                # the list calls "Unknown"), from the server or the device.
                _display_min = float(getattr(_ps, 'min_confidence_display', 0.0) or 0.0)
                _shown = sum(1 for d in rec.detections if float(d.confidence or 0) >= _display_min)
                _do_purge = (
                    not getattr(rec, 'haikubox_detection_id', None)
                    and _shown == 0
                    and (_purge_all_device or _device_max_conf_pre < _purge_threshold)
                )
                _protected = _purge_protected_species(rec, db) if _do_purge else None
                if _protected:
                    logger.info("Auto-purge skipped for %s: the server pass kept %s under its owl rules", rec_id, _protected)
                    _do_purge = False
                if _do_purge:
                    logger.info(
                        "Auto-purge: deleting recording %s — nothing at the %.2f display threshold "
                        "(%d server detections under it), device conf %.2f (purge_all=%s, threshold=%.2f)",
                        rec_id, _display_min, _server_det_count, _device_max_conf_pre, _purge_all_device, _purge_threshold
                    )
                    from ..services.file_cleanup import collect_files, remove_files
                    _job = collect_files([rec])
                    db.delete(rec)
                    db.commit()
                    remove_files(_job)   # after the commit: no lock held
        except Exception as _pe:
            logger.warning("Auto-purge step failed for %s: %s", rec_id, _pe)

        # 6. Watched birds: push people who tagged a species heard here
        try:
            from ..services.bird_watch import notify_watchers
            notify_watchers(db, rec_id)
        except Exception as _we:
            logger.warning("Bird watch alerts failed for %s: %s", rec_id, _we)

    except Exception as e:
        logger.error("Background processing error for %s: %s", rec_id, e)
        try:
            rec = db.query(Recording).filter(Recording.id == rec_id).first()
            if rec:
                rec.processing_status = "error"
                rec.processing_error = str(e)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


def _process_bat_recording_bg(rec, db, rec_id: str):
    """
    Background processing for a bat-echolocation recording. Separated from
    process_recording_bg() rather than interleaved with `if rec.is_bat`
    branches throughout, since the two pipelines diverge almost entirely
    after the initial DB fetch — keeping them as two linear, readable
    functions beats one function with bat-shaped detours scattered through
    bird-shaped logic.

    Does NOT own the db session — process_recording_bg() opened it and
    closes it in its own finally block after this function returns (even
    on the early-return path). This function only commits/rolls back state
    on it, the same division of responsibility as any other helper that
    takes a session parameter.
    """
    try:
        # 1. Bat-specific spectrogram — see generate_bat_spectrogram()'s
        # docstring for why this can't reuse the bird spectrogram path.
        try:
            spec_path = processor.generate_bat_spectrogram(
                rec.wav_path, settings.spectrograms_dir, rec_id,
            )
            rec.spectrogram_path = spec_path
        except Exception as e:
            logger.warning("Bat spectrogram failed for %s: %s", rec_id, e)

        # 2. Clip extraction — a bat Recording has exactly one Detection
        # (common_name="Bat", spanning the full recording), so there's one
        # clip to extract rather than per-detection extraction like birds.
        for det in rec.detections:
            try:
                clip_path = processor.extract_clip(
                    rec.wav_path, settings.clips_dir, det.id,
                    det.start_time, det.end_time,
                    padding=0.0,   # no pre/post padding — already the full clip
                    is_bat=True,
                )
                det.clip_path = clip_path
                db.add(det)
            except Exception as e:
                logger.debug("Bat clip extraction failed for %s: %s", det.id, e)

        # 2.5. Bat species classification — off by default (Settings →
        # Detection → "Identify bat species"). A previous version of this
        # step never ran at all: it imported a services/bat_species_id.py
        # module that didn't exist, and read bat_species_id_enabled from
        # an AppSettings attribute that wasn't declared as a Column on the
        # model — so any stored value silently fell back to the Python
        # default regardless of what was actually set.
        #
        # Uses a two-stage BirdNET-embedding + NABat-trained classifier
        # (see bat_species_classifier.py's module docstring for technical
        # detail and known accuracy limits, including a case of
        # misclassifying pure silence as a specific species with high
        # confidence). A species is only assigned when the result clears
        # bat_species_id_min_confidence AND scores higher than the
        # classifier's own noise/cricket/silence classes — a
        # species-shaped confidence number alone isn't sufficient.
        try:
            from ..models import AppSettings as _AS_bat
            _s_bat = db.query(_AS_bat).filter(_AS_bat.id == 1).first()
            if _s_bat and _s_bat.bat_species_id_enabled and rec.wav_path:
                # Filters only degenerate, near-zero-duration clips (a
                # literal 0-second recording), not a general "long enough
                # for multiple windows" gate — the classifier zero-pads
                # any clip into at least one valid window regardless of
                # length, and the confidence threshold below, not
                # duration, is what decides whether a result gets
                # asserted. Previously 1.5s; lowered to 0.3s since plenty
                # of well-formed bat calls run shorter than that and were
                # being skipped before ever being attempted.
                MIN_DURATION_FOR_SPECIES_ID = 0.3  # seconds
                if (rec.duration_seconds or 0) >= MIN_DURATION_FOR_SPECIES_ID:
                    from ..services.bat_species_classifier import (
                        classify_bat_wav_file, BatClassifierUnavailable,
                    )
                    try:
                        result = classify_bat_wav_file(rec.wav_path)
                        top_species = result["species"][0] if result["species"] else None
                        top_non_species = result["non_species"][0] if result["non_species"] else None

                        # Stored regardless of whether a species is
                        # asserted below — keeps full visibility into what
                        # the classifier saw, not just a pass/fail bit.
                        meta = dict(rec.bat_metadata or {})
                        meta["species_guess"] = {
                            "model": "BattyBirdNET-USA-EAST-256kHz",
                            "model_trained_on": "NABat (North American Bat Monitoring Program)",
                            "top_species": top_species,
                            "top_non_species": top_non_species,
                            "all_species": result["species"],
                            "all_non_species": result["non_species"],
                            "num_windows": result["num_windows"],
                            "validated": False,
                        }
                        rec.bat_metadata = meta

                        min_conf = _s_bat.bat_species_id_min_confidence
                        if min_conf is None:
                            min_conf = 0.75
                        confident_species = (
                            top_species is not None
                            and top_species["confidence"] >= min_conf
                            and (top_non_species is None or top_species["confidence"] > top_non_species["confidence"])
                        )
                        if confident_species:
                            for det in rec.detections:
                                det.common_name = top_species["common_name"]
                                det.scientific_name = top_species["scientific_name"]
                                det.label = top_species["label"]
                                # Real fix for "overall confidence should
                                # update": once a species is confidently
                                # identified, the more honest and useful
                                # confidence to show everywhere (the
                                # recording detail header's "TOP CONFIDENCE"
                                # stat, the per-detection row, etc.) is the
                                # classifier's own confidence in THIS
                                # species — not the original pulse-detection
                                # confidence, which stays near 100% for any
                                # genuine echolocation call regardless of
                                # which species it turns out to be. A
                                # recording classified as "Big brown bat"
                                # at 94.3% previously still showed 100% in
                                # the header, since confidence was never
                                # touched here.
                                det.confidence = top_species["confidence"]
                                db.add(det)
                            logger.info(
                                "Bat species identified for %s: %s (%.1f%% confidence, %d window%s)",
                                rec_id, top_species["common_name"], top_species["confidence"] * 100,
                                result["num_windows"], "" if result["num_windows"] == 1 else "s",
                            )
                        else:
                            logger.info(
                                "Bat species classification for %s: no confident match "
                                "(top species %.1f%%, top non-species %.1f%%, threshold %.1f%%) — "
                                "kept as generic 'Bat'",
                                rec_id,
                                top_species["confidence"] * 100 if top_species else 0.0,
                                top_non_species["confidence"] * 100 if top_non_species else 0.0,
                                min_conf * 100,
                            )
                    except BatClassifierUnavailable as e:
                        logger.debug("Bat species classifier unavailable for %s: %s", rec_id, e)
                else:
                    logger.debug(
                        "Bat species classification skipped for %s — recording too short "
                        "(%.2fs < %.2fs minimum for a fair multi-window classification)",
                        rec_id, rec.duration_seconds or 0, MIN_DURATION_FOR_SPECIES_ID,
                    )
        except Exception as e:
            logger.warning("Bat species ID step failed for %s: %s", rec_id, e)

        # 2.6. Auto de-wobble pre-generation — off by default (Settings →
        # bat_auto_remove_wobble). Queried fresh rather than reusing the
        # _s_bat row from step 2.5 above: that variable may not exist at
        # all if step 2.5's own try block raised before assigning it, and
        # this step should work independently of whether species ID ran.
        # Only pre-generates the cache file so it's instant when someone
        # later requests it — does not change what plays by default; see
        # the AppSettings column's own docstring for that distinction.
        try:
            from ..models import AppSettings as _AS_wobble
            _s_wobble = db.query(_AS_wobble).filter(_AS_wobble.id == 1).first()
            if _s_wobble and _s_wobble.bat_auto_remove_wobble and rec.wav_path:
                cache_path = os.path.join(settings.enhanced_dir, f"{rec_id}_dewobbled.wav")
                if not os.path.exists(cache_path):
                    processor.remove_bat_wobble(rec.wav_path, settings.enhanced_dir, rec_id)
        except Exception as e:
            logger.warning("Bat auto-dewobble pre-generation failed for %s: %s", rec_id, e)

        rec.processing_status = "done"
        db.commit()

        # 3. Ensure BirdProfile(s) exist for whatever ended up assigned to
        # this recording's detection(s) above — almost always still the
        # generic "Bat" pseudo-species (idempotent, see
        # BirdEnricher._ensure_bat_profile()), but if step 2.5 confidently
        # identified a specific real species, ensure ITS profile exists
        # too. ensure_profile() dispatches correctly either way: "Bat"
        # routes to the dedicated static-content/photo handling (no real
        # taxonomy entry to look up), anything else goes through the
        # same generic Wikipedia/iNaturalist enrichment pipeline any bird
        # species uses — that pipeline isn't bird-specific in any way
        # that would break for a mammal name (eBird-specific steps just
        # find nothing and move on), it just happens to mostly see bird
        # names today.
        #
        # Passes det.label, not det.common_name: a bare common name like
        # "Big brown bat" has no "_" separator for _create_profile() to
        # split on, so it fell through to creating the profile with
        # scientific_name=None. Without a scientific name, the
        # enrichment pipeline's iNaturalist/Wikipedia photo lookup has a
        # much weaker, more ambiguous starting point — the cause of a
        # reported missing/wrong photo for a confidently-classified
        # species. det.label is already the correctly-formatted
        # "Scientific_Common" string (e.g. "Eptesicus fuscus_Big brown
        # bat") for anything confidently classified, and stays exactly
        # "Bat" for the generic pseudo-species case, so this routes
        # correctly either way.
        try:
            from ..services.bird_enricher import BirdEnricher
            enricher = BirdEnricher(db)
            seen_labels = set()
            for det in rec.detections:
                if det.label not in seen_labels:
                    seen_labels.add(det.label)
                    enricher.ensure_profile(det.label, is_bat=True)
        except Exception as e:
            logger.warning("Bat profile ensure failed for %s: %s", rec_id, e)

        # NOTE: no compression step (see process_recording_bg's comment for
        # why), no BirdNET re-analysis, no auto-purge — none of those apply
        # to a recording with no species call to analyze or purge against.

    except Exception as e:
        logger.error("Bat background processing error for %s: %s", rec_id, e)
        try:
            rec_fresh = db.query(Recording).filter(Recording.id == rec_id).first()
            if rec_fresh:
                rec_fresh.processing_status = "error"
                rec_fresh.processing_error = str(e)
                db.commit()
        except Exception:
            pass


# ── List & Get Recordings ─────────────────────────────────────────────────────

@router.get("", response_model=List[RecordingOut])
def list_recordings(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    species: Optional[str] = Query(None, description="Filter by common name (partial match)"),
    min_confidence: Optional[float] = Query(None, ge=0, le=1),
    status_filter: Optional[str] = Query(None, alias="status"),
    include_deleted: bool = Query(False, description="Include soft-deleted recordings"),
    device_id: Optional[str] = Query(None, description="Filter to recordings from a specific device (real or virtual, e.g. Haikubox)"),
    is_bat: Optional[bool] = Query(None, description="Filter to bat-echolocation recordings only (true) or bird recordings only (false)"),
    no_detections: Optional[bool] = Query(None, description="Filter to recordings that show nothing at the display threshold (true) or show at least one detection (false). Left out, device recordings that show nothing are hidden."),
    flag_interference: Optional[bool] = Query(None, description="Filter to bat recordings flagged as likely electrical/mechanical interference (true) or not flagged (false)"),
    is_live_session: Optional[bool] = Query(None, description="Filter to recordings saved from a Live Detect session (true) or not (false)"),
    multi_species: Optional[bool] = Query(None, description="Filter to recordings with more than one distinct species detected (true) or at most one (false)"),
    start: Optional[datetime] = Query(None, description="ISO 8601 — only recordings at or after this time"),
    end: Optional[datetime] = Query(None, description="ISO 8601 — only recordings at or before this time"),
    time_from: Optional[str] = Query(None, description="HH:MM, site time: only recordings made at or after this time of day"),
    time_to: Optional[str] = Query(None, description="HH:MM, site time: only recordings made before this time of day (wraps midnight when earlier than time_from)"),
    saved: Optional[bool] = Query(None, description="Only saved recordings (true) or only unsaved (false)"),
    db: Session = Depends(get_db),
):
    """List recordings, most recent first."""
    from ..models import AppSettings as _AS
    _s = db.query(_AS).filter(_AS.id == 1).first()
    _show_del = include_deleted or (bool(getattr(_s, "show_deleted_detections", False)) if _s else False)

    q = db.query(Recording)
    if not _show_del:
        q = q.filter(Recording.deleted_at.is_(None))

    # Hard-hide Haikubox rows from the main feed, unconditionally — per
    # explicit direction, Haikubox detections belong only on their own
    # dedicated page (see list_haikubox_recordings below), never mixed
    # into the main Pi-recordings feed, regardless of whether the
    # Haikubox toggle is currently on or off. This used to be
    # conditional on the toggle being OFF (to satisfy a separate, earlier
    # requirement that disabling Haikubox should make its data
    # "disappear as if it never existed" from every page) — but that
    # left a real gap: with the toggle ON, this endpoint had no
    # Haikubox-exclusion logic at all, so synced Haikubox rows could
    # appear in the main feed depending on sort order or scroll
    # position, contradicting the "always kept separate" requirement.
    # Unconditional exclusion here satisfies both requirements correctly:
    # off → Haikubox data invisible everywhere (nothing to exclude, since
    # nothing syncs); on → still always excluded from this specific feed,
    # only ever visible via the dedicated Haikubox page and the
    # species-scoped links on bird/bat profile pages.
    q = q.filter(Recording.haikubox_detection_id.is_(None))

    # Hard-hide individual, unsaved Live Detect poll clips too, same
    # unconditional treatment as Haikubox rows just above — these are
    # meant to be transient (either consolidated into one
    # is_live_session=True recording when a session gets saved, or
    # discarded immediately if a poll found nothing), never a
    # permanent, standalone entry in their own right. Confirmed
    # directly from a real deployment: leaving a Live Detect page open
    # for a couple of minutes created hundreds of these with no session
    # ever saved, burying every real recording underneath them with no
    # way to filter them back out before this existed.
    q = q.filter(Recording.is_live_detect_clip.isnot(True))

    # One detection has to match every detection filter (species and
    # confidence together, as the JOIN did). IN (subquery) instead of
    # JOIN + DISTINCT: same rows, and the page count no longer
    # de-duplicates every column of every matching recording.
    _det_conds = []
    if species:
        _det_conds.append(Detection.common_name.ilike(f"%{species}%"))
    if min_confidence is not None:
        _det_conds.append(Detection.confidence >= min_confidence)
    if _det_conds:
        q = q.filter(Recording.id.in_(db.query(Detection.recording_id).filter(*_det_conds)))

    if status_filter:
        q = q.filter(Recording.processing_status == status_filter)

    if device_id:
        q = q.filter(Recording.device_id == device_id)

    if is_bat is not None:
        q = q.filter(Recording.is_bat == is_bat)

    # "Shows nothing" = no detection at the display threshold, the list's
    # "Unknown" cards. Hidden by default for finished device recordings;
    # bats, manual uploads, recordings still processing and ones someone
    # labeled stay. The "No detections" filter lists exactly these.
    _display_min = float(getattr(_s, "min_confidence_display", 0.0) or 0.0) if _s else 0.0
    _shows_something = Recording.detections.any(Detection.confidence >= _display_min)
    if no_detections is True:
        q = q.filter(~_shows_something)
    elif no_detections is False:
        q = q.filter(_shows_something)
    elif not species and min_confidence is None:
        from sqlalchemy import and_ as _and, or_ as _or
        q = q.filter(_or(
            _shows_something,
            Recording.device_id.is_(None),
            Recording.is_bat.is_(True),
            Recording.processing_status.notin_(["done", "error"]),
            _and(Recording.label.isnot(None), Recording.label != ""),
        ))

    if flag_interference is not None:
        # bat_metadata is a JSON column — likely_interference lives inside
        # it (set by the device's BatDetector, see bat_detector.py's
        # _finalize_event), not a dedicated column, so this needs a real
        # JSON extraction rather than a plain field filter. SQLite's
        # json_extract() of a JSON boolean returns an integer (1 or 0),
        # not a Python bool — comparing against a mixed bool/int/str list
        # via .in_() breaks SQLAlchemy's type binding, so this compares
        # against the integer form directly instead.
        from sqlalchemy import func as _func
        interference_expr = _func.json_extract(Recording.bat_metadata, "$.likely_interference")
        if flag_interference:
            q = q.filter(interference_expr == 1)
        else:
            q = q.filter(_func.coalesce(interference_expr, 0) != 1)

    if is_live_session is not None:
        q = q.filter(Recording.is_live_session == is_live_session)

    if multi_species is not None:
        # "Multiple birds in one recording" means more than one DISTINCT
        # species within the same recording, not just more than one
        # detection (three American Robin calls in one recording isn't
        # what someone filtering for this is looking for). Grouped by
        # recording_id with a DISTINCT common_name count in the HAVING
        # clause, then joined back by id — the .any()-based pattern used
        # for no_detections above doesn't extend to "count of distinct
        # values across related rows", which needs a GROUP BY.
        from sqlalchemy import func as _func3
        multi_species_recording_ids = (
            db.query(Detection.recording_id)
            .group_by(Detection.recording_id)
            .having(_func3.count(_func3.distinct(Detection.common_name)) > 1)
            .subquery()
        )
        if multi_species:
            q = q.filter(Recording.id.in_(db.query(multi_species_recording_ids.c.recording_id)))
        else:
            q = q.filter(~Recording.id.in_(db.query(multi_species_recording_ids.c.recording_id)))

    if saved is not None:
        q = q.filter(Recording.is_saved.is_(True) if saved else Recording.is_saved.isnot(True))
    if time_from or time_to:
        q = _filter_time_of_day(q, db, time_from or "00:00", time_to or "24:00")
    if start:
        # Incoming datetimes may be tz-aware (a browser's toISOString()
        # always includes one) while trigger_timestamp is stored
        # naive-UTC throughout this codebase — same conversion used on
        # list_haikubox_recordings.
        start_naive = start.astimezone(timezone.utc).replace(tzinfo=None) if start.tzinfo else start
        q = q.filter(Recording.trigger_timestamp >= start_naive)
    if end:
        end_naive = end.astimezone(timezone.utc).replace(tzinfo=None) if end.tzinfo else end
        q = q.filter(Recording.trigger_timestamp <= end_naive)

    recordings_list = (
        q.options(selectinload(Recording.detections))
        .order_by(Recording.trigger_timestamp.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    # Batch-fetch AppSettings once and build a global profile map for all recordings
    # This eliminates O(N) AppSettings + O(N) BirdProfile queries in list views.
    # The selectinload above eliminates a further O(N) lazy-load on rec.detections
    # itself — recording_to_out() accesses that relationship twice per recording
    # (a len() and a full iteration), which without eager-loading meant one extra
    # SELECT per recording on the single most-visited page in the app (up to 200
    # extra round trips per page load at the max page size).
    try:
        _shared_settings = db.query(AppSettings).filter(AppSettings.id == 1).first()
    except Exception:
        _shared_settings = None
    all_labels = list({d.label for r in recordings_list for d in r.detections if d.label})
    _shared_profiles = {}
    if all_labels:
        try:
            _shared_profiles = {
                p.label: p
                for p in db.query(BirdProfile).filter(BirdProfile.label.in_(all_labels)).all()
            }
        except Exception:
            pass

    all_device_ids = list({r.device_id for r in recordings_list if r.device_id})
    _shared_devices = {}
    if all_device_ids:
        try:
            from ..models import Device
            _shared_devices = {
                dv.id: dv
                for dv in db.query(Device).filter(Device.id.in_(all_device_ids)).all()
            }
        except Exception:
            pass

    total_count = q.count()
    from fastapi.responses import JSONResponse
    items = [recording_to_out(r, db, _app_settings=_shared_settings, _profile_map=_shared_profiles, _device_map=_shared_devices)
             for r in recordings_list]
    # Serialize using Pydantic
    from fastapi.encoders import jsonable_encoder
    response = JSONResponse(
        content=jsonable_encoder(items),
        headers={"X-Total-Count": str(total_count), "Access-Control-Expose-Headers": "X-Total-Count"}
    )
    return response


# ── Haikubox detections — dedicated listing, deliberately separate from
# the main /recordings feed (see haikubox_sync.py for why these rows have
# no audio: the Haikubox cloud API never provides a WAV file, only a
# species/timestamp record). Kept on its own page rather than mixed into
# the main Recordings list per explicit product direction: Haikubox data
# supplements the Pi-based detections, it shouldn't dilute or distract
# from them in the primary feed. This endpoint also backs the "N Haikubox
# detections" link on bird/bat profile pages (via the species filter) and
# the device card's detection count on the Devices page. ─────────────────

@router.get("/haikubox", response_model=List[RecordingOut])
def list_haikubox_recordings(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    species: Optional[str] = Query(None, description="Filter to a single common name — used by bird/bat profile pages"),
    start: Optional[datetime] = Query(None, description="ISO 8601 — only detections at or after this time"),
    end: Optional[datetime] = Query(None, description="ISO 8601 — only detections at or before this time"),
    db: Session = Depends(get_db),
):
    """
    List Haikubox-sourced recordings only (Recording.haikubox_detection_id
    IS NOT NULL), most recent first. Same RecordingOut shape and the same
    batched-query pattern as list_recordings, so the frontend can reuse
    its existing recording-card rendering with no special-casing beyond
    knowing these rows have no audio (already true for any recording with
    has_audio=False, e.g. older device recordings whose WAV was deleted).

    start/end are plain ISO 8601 timestamps rather than a "period" enum
    (e.g. "24h", "7d") — the frontend's quick presets (last N hours/days/
    weeks/months) and its custom date-range picker both just compute a
    start/end pair and pass them here, so this endpoint stays generic and
    doesn't need to know about every preset the UI offers.

    Hard-hidden when AppSettings.haikubox_enabled is False — per explicit
    product direction, disabling the feature should hide pre-existing
    Haikubox data immediately, not just pause new syncing. Returns an
    empty result (not 403): this is a visibility toggle, not an auth
    boundary, and every calling UI surface (the dedicated page, the
    Recordings-list banner, the bird/bat profile link) already renders
    correctly — i.e. renders nothing — on an empty/zero result.
    """
    _hb_settings = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if not (_hb_settings and getattr(_hb_settings, "haikubox_enabled", False)):
        from fastapi.responses import JSONResponse
        return JSONResponse(content=[], headers={"X-Total-Count": "0", "Access-Control-Expose-Headers": "X-Total-Count"})

    q = db.query(Recording).filter(
        Recording.haikubox_detection_id.isnot(None),
        Recording.deleted_at.is_(None),
    )
    if species:
        q = q.join(Recording.detections).filter(
            Detection.common_name == species
        ).distinct()
    if start:
        # Incoming datetimes may be tz-aware (e.g. "...Z" or "+00:00" from
        # the browser's toISOString()) while trigger_timestamp is stored
        # naive-UTC throughout this codebase — strip tzinfo after any
        # conversion rather than compare aware-to-naive, which SQLAlchemy/
        # SQLite would otherwise either error on or silently mishandle.
        start_naive = start.astimezone(timezone.utc).replace(tzinfo=None) if start.tzinfo else start
        q = q.filter(Recording.trigger_timestamp >= start_naive)
    if end:
        end_naive = end.astimezone(timezone.utc).replace(tzinfo=None) if end.tzinfo else end
        q = q.filter(Recording.trigger_timestamp <= end_naive)

    recordings_list = (
        q.options(selectinload(Recording.detections))
        .order_by(Recording.trigger_timestamp.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    try:
        _shared_settings = db.query(AppSettings).filter(AppSettings.id == 1).first()
    except Exception:
        _shared_settings = None
    all_labels = list({d.label for r in recordings_list for d in r.detections if d.label})
    _shared_profiles = {}
    if all_labels:
        try:
            _shared_profiles = {
                p.label: p
                for p in db.query(BirdProfile).filter(BirdProfile.label.in_(all_labels)).all()
            }
        except Exception:
            pass

    all_device_ids = list({r.device_id for r in recordings_list if r.device_id})
    _shared_devices = {}
    if all_device_ids:
        try:
            from ..models import Device
            _shared_devices = {
                dv.id: dv
                for dv in db.query(Device).filter(Device.id.in_(all_device_ids)).all()
            }
        except Exception:
            pass

    total_count = q.count()
    from fastapi.responses import JSONResponse
    items = [recording_to_out(r, db, _app_settings=_shared_settings, _profile_map=_shared_profiles, _device_map=_shared_devices)
             for r in recordings_list]
    from fastapi.encoders import jsonable_encoder
    return JSONResponse(
        content=jsonable_encoder(items),
        headers={"X-Total-Count": str(total_count), "Access-Control-Expose-Headers": "X-Total-Count"}
    )


@router.get("/haikubox/summary")
def haikubox_summary(db: Session = Depends(get_db)):
    """
    Lightweight summary for surfaces that just need counts, not full
    recording data: the Devices page's Haikubox device card (total count
    + most recent detection time) and a quick existence check for whether
    the "View Haikubox Detections" link should appear on the Recordings
    list at all (per-species counts power the same link on bird/bat
    profile pages, via the species_counts map below).

    Hard-hidden when disabled — see list_haikubox_recordings's docstring
    for the reasoning. Returns an all-zero/empty summary, which every
    calling surface already correctly renders as "nothing to show."
    """
    _hb_settings = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if not (_hb_settings and getattr(_hb_settings, "haikubox_enabled", False)):
        return {"total": 0, "most_recent": None, "species_counts": {}}

    q = db.query(Recording).filter(
        Recording.haikubox_detection_id.isnot(None),
        Recording.deleted_at.is_(None),
    )
    total = q.count()
    most_recent = None
    if total:
        latest = q.order_by(Recording.trigger_timestamp.desc()).first()
        most_recent = latest.trigger_timestamp.isoformat() if latest and latest.trigger_timestamp else None

    from sqlalchemy import func
    species_counts = dict(
        db.query(Detection.common_name, func.count(Detection.id))
        .join(Recording, Detection.recording_id == Recording.id)
        .filter(Recording.haikubox_detection_id.isnot(None), Recording.deleted_at.is_(None))
        .group_by(Detection.common_name)
        .all()
    )

    return {
        "total": total,
        "most_recent": most_recent,
        "species_counts": species_counts,
    }


@router.get("/stats")
def recording_stats(
    period: str = Query("24h", description="Detection chart window: 6h,24h,48h,7d,30d"),
    db: Session = Depends(get_db),
):
    """Dashboard statistics."""
    # This endpoint loads on every Dashboard visit (not once-per-visit
    # like the Statistics page) and does several joined/aggregated
    # queries including a distinct-species subquery — the same
    # "Dashboard-facing, no caching at all" gap yard_pulse() above was
    # already fixed for, confirmed still present here by the absence of
    # any statistics_cache usage in this function. Keyed on period since
    # that's the only parameter (period has a small, fixed set of
    # valid values — see _valid_period below — so this can't grow into
    # an unbounded cache).
    from ..cache import statistics_cache
    _stats_cache_key = f"dashboard_stats:{period}"
    _stats_cached = statistics_cache.get(_stats_cache_key)
    if _stats_cached is not None:
        return _stats_cached

    from sqlalchemy import func
    from ..models import AppSettings as _AS
    _s = db.query(_AS).filter(_AS.id == 1).first()
    _show_deleted = bool(getattr(_s, "show_deleted_detections", False)) if _s else False

    # Base recording query — exclude soft-deleted unless show_deleted is on
    _rec_q = db.query(Recording)
    if not _show_deleted:
        _rec_q = _rec_q.filter(Recording.deleted_at.is_(None))
    # Individual, unsaved Live Detect poll clips are never meant to be
    # a permanent, countable recording in their own right — same
    # exclusion and same reasoning as list_recordings' own filter
    # above this function in this file.
    _rec_q = _rec_q.filter(Recording.is_live_detect_clip.isnot(True))
    total_recordings = _rec_q.count()

    # Detection queries — join to recordings and apply same filter
    _det_base = db.query(Detection).join(Recording, Detection.recording_id == Recording.id)
    if not _show_deleted:
        _det_base = _det_base.filter(Recording.deleted_at.is_(None))
    _det_base = _det_base.filter(Recording.is_live_detect_clip.isnot(True))

    # Apply display confidence threshold to ALL stat queries so counts match what the
    # user actually sees — species/detections below the threshold are invisible.
    _s2 = db.query(AppSettings).filter(AppSettings.id == 1).first() if _s is None else _s
    _min_conf = float(getattr(_s2, 'min_confidence_display', 0.0) or 0.0) if _s2 else 0.0
    if _min_conf > 0:
        _det_base = _det_base.filter(Detection.confidence >= _min_conf)

    # Exclude species detected ONLY via Haikubox from the headline "Species" stat,
    # for the same reason get_life_list() in birds.py excludes them: a species with
    # zero real Pi/device detections was never actually heard by this Chirp install,
    # so it shouldn't count toward "species detected" — and disabling the Haikubox
    # toggle doesn't delete these rows, so without this exclusion the dashboard
    # would keep counting them even with the feature turned off. This previously
    # caused the Dashboard's species/detection counts to disagree with the Life
    # List's by exactly the number of Haikubox-only species (e.g. 88 vs 80).
    # total_detections deliberately still counts every detection (Pi + Haikubox)
    # for species that have at least one real detection — only fully-Haikubox-only
    # species are dropped, matching get_life_list()'s exact semantic.
    from ..services.species_filters import exclude_haikubox_only
    _det_base = exclude_haikubox_only(_det_base, db)

    total_species = _det_base.with_entities(
        func.count(Detection.common_name.distinct())).scalar()
    total_detections = _det_base.with_entities(
        func.count(Detection.id)).scalar()

    # Latest recording that shows a bird: the Dashboard's Live card and "Last
    # detection" link to it. Live Detect poll clips (deleted moments later
    # when they hold nothing), Haikubox rows and recordings with nothing at
    # the display threshold are skipped; any of them could leave the card
    # showing "Unidentified" or linking to a recording that no longer exists.
    _latest_q = (db.query(Recording)
                 .filter(Recording.is_live_detect_clip.isnot(True))
                 .filter(Recording.haikubox_detection_id.is_(None))
                 .filter(Recording.detections.any(Detection.confidence >= _min_conf))
                 # Finished: the server pass can still purge a recording it
                 # finds empty, so an unfinished one may vanish moments later.
                 .filter(Recording.processing_status == "done")
                 .order_by(Recording.trigger_timestamp.desc()))
    if not _show_deleted:
        _latest_q = _latest_q.filter(Recording.deleted_at.is_(None))
    latest = _latest_q.first()

    # Detections chart — real-timestamp bucketing, period-aware
    from datetime import datetime, timedelta

    _PERIOD_MAP = {
        "6h":  (timedelta(hours=6),   "%Y-%m-%dT%H:00",  "hour",  6,   1),
        "24h": (timedelta(hours=24),  "%Y-%m-%dT%H:00",  "hour",  24,  1),
        "48h": (timedelta(hours=48),  "%Y-%m-%dT%H:00",  "hour",  48,  2),
        "7d":  (timedelta(days=7),    "%Y-%m-%dT%H:00",  "hour",  168, 12),
        "30d": (timedelta(days=30),   "%Y-%m-%d",        "day",   30,  3),
    }
    _valid_period = period if period in _PERIOD_MAP else "24h"
    _delta, _fmt, _unit, _n_buckets, _tick_every = _PERIOD_MAP[_valid_period]
    cutoff = datetime.utcnow() - _delta

    # Top species — same time window as the chart
    top_species_query = (
        _det_base
        .filter(Recording.trigger_timestamp >= cutoff)
        .with_entities(Detection.common_name, func.count(Detection.id).label("count"))
        .group_by(Detection.common_name)
        .order_by(func.count(Detection.id).desc())
        .limit(30)
        .all()
    )

    # SQLite strftime bucket expression
    if _unit == "day":
        _bucket_expr = func.strftime("%Y-%m-%d", Recording.trigger_timestamp)
    else:
        _bucket_expr = func.strftime("%Y-%m-%dT%H:00", Recording.trigger_timestamp)

    # Built from _det_base (not a fresh query) so the chart inherits exactly
    # the same filters as top_species/total_detections above: soft-delete
    # exclusion, the confidence threshold, and — critically — the
    # Haikubox-only-species exclusion. A fresh query here previously had to
    # manually re-apply soft-delete and confidence filtering by hand and
    # never applied the Haikubox exclusion at all, so with Haikubox sync on,
    # the chart could show higher counts than top_species/total_detections
    # for the same time window — the two halves of this same dashboard card
    # silently disagreeing with each other.
    hour_q = (
        _det_base
        .filter(Recording.trigger_timestamp >= cutoff)
        .with_entities(_bucket_expr.label("bucket"), func.count(Detection.id).label("count"))
        .group_by("bucket")
        .order_by("bucket")
    )
    hour_rows = hour_q.all()
    by_bucket = {r.bucket: r.count for r in hour_rows}

    # Build complete bucket sequence including current bucket
    detections_by_hour = []
    now = datetime.utcnow()
    if _unit == "day":
        # Generate day buckets from cutoff date up to and including today
        day_start = cutoff.replace(hour=0, minute=0, second=0, microsecond=0)
        today_str = now.strftime("%Y-%m-%d")
        for i in range(_n_buckets + 1):
            t = day_start + timedelta(days=i)
            key = t.strftime("%Y-%m-%d")
            if key > today_str:
                break
            detections_by_hour.append({"bucket": key, "count": by_bucket.get(key, 0), "unit": "day"})
    else:
        # Generate hour buckets from cutoff (truncated to hour) up to and including now
        cutoff_h = cutoff.replace(minute=0, second=0, microsecond=0)
        now_h_key = now.strftime("%Y-%m-%dT%H:00")
        for i in range(_n_buckets + 2):   # +2 ensures we always reach now_h
            t = cutoff_h + timedelta(hours=i)
            key = t.strftime("%Y-%m-%dT%H:00")
            detections_by_hour.append({"bucket": key, "count": by_bucket.get(key, 0), "unit": "hour",
                                        "hour_of_day": t.hour})
            if key >= now_h_key:
                break   # stop once we've included the current hour

    result = {
        "total_recordings": total_recordings,
        "total_species": total_species,
        "total_detections": total_detections,
        "latest_recording": latest.trigger_timestamp.isoformat() if latest else None,
        "latest_recording_id": latest.id if latest else None,
        "top_species": (lambda: (
            # Batch lookup: one query for all species names instead of N queries
            lambda profiles_map: [
                {"name": s, "common_name": s, "count": c,
                 "bird_profile_id": profiles_map.get(s)}
                for s, c in top_species_query
            ]
        )({
            bp.common_name: str(bp.id)
            for bp in db.query(BirdProfile.common_name, BirdProfile.id).filter(
                BirdProfile.common_name.in_([s for s, _ in top_species_query])
            ).all()
        }))(),
        "detections_by_hour": detections_by_hour,
        "period": _valid_period,
    }
    statistics_cache.set(_stats_cache_key, result)
    return result


@router.get("/{recording_id}", response_model=RecordingOut)
def get_recording(recording_id: str, db: Session = Depends(get_db)):
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    return recording_to_out(rec, db)


# Recordings with an AI Second Opinion in progress (this process).
_AI_RECHECK_RUNNING: set = set()
_AI_RECHECK_LOCK = threading.Lock()


def _ai_recheck_bg(recording_id: str) -> None:
    from ..database import SessionLocal
    from ..services.call_reanalysis import reanalyze_call
    db = SessionLocal()
    try:
        rec = db.query(Recording).filter(Recording.id == recording_id).first()
        if rec:
            reanalyze_call(db, rec)
    except Exception as e:
        logger.warning("AI Second Opinion for %s failed: %s", recording_id, e)
        try:
            rec = db.query(Recording).filter(Recording.id == recording_id).first()
            if rec:
                rec.ai_reanalysis_error = str(e)[:500]
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
        with _AI_RECHECK_LOCK:
            _AI_RECHECK_RUNNING.discard(recording_id)


@router.post("/ai-warm", status_code=202)
def ai_warm(db: Session = Depends(get_db)):
    """Recording pages call this when they open: with a local (Ollama) AI
    Second Opinion provider, load the model now so the second opinion
    doesn't also wait for the model to load. Nothing to do for hosted
    providers."""
    from ..services.ai_providers import get_feature_config, warm_ollama
    fc = get_feature_config("call_reanalysis", db)
    if not fc or fc[0] != "ollama":
        return {"status": "not_needed"}
    import json as _json
    return {"status": warm_ollama(_json.loads(fc[1]))}


@router.post("/{recording_id}/ai-recheck", status_code=202)
def ai_recheck_recording(recording_id: str, background_tasks: BackgroundTasks,
                         db: Session = Depends(get_db)):
    """Manual, on-demand AI call re-analysis (a vision-based second opinion,
    see services/call_reanalysis.py) — distinct from POST /{recording_id}/reanalyze
    above, which re-runs the BirdNET detection pipeline.

    Runs in the background and returns at once: a long answer from a hosted
    model, or any answer from a local one, can take minutes, longer than a
    browser, the iOS app or a proxy waits on one request. The page polls
    the recording until ai_reanalysis_generated_at changes or
    ai_reanalysis_error is set."""
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    from ..services.ai_providers import get_feature_config
    if get_feature_config("call_reanalysis", db) is None:
        raise HTTPException(status_code=400,
                            detail="AI Second Opinion isn't set up: choose a provider in Settings → AI Features.")
    with _AI_RECHECK_LOCK:
        already = recording_id in _AI_RECHECK_RUNNING
        _AI_RECHECK_RUNNING.add(recording_id)
    if not already:
        rec.ai_reanalysis_error = None
        db.commit()
        background_tasks.add_task(_ai_recheck_bg, recording_id)
    return {"status": "running", "started": not already,
            "previous_generated_at": rec.ai_reanalysis_generated_at}


@router.get("/{recording_id}/audio")
def stream_audio(recording_id: str, db: Session = Depends(get_db)):
    """Stream the recording's audio as stored (WAV, FLAC or Opus after
    compression), with its type and a filename that match the file."""
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec or not rec.wav_path or not os.path.exists(rec.wav_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    ext = os.path.splitext(rec.wav_path)[1].lower() or ".wav"
    stem = os.path.splitext(rec.filename or rec.id)[0]
    return FileResponse(
        rec.wav_path,
        media_type=_AUDIO_TYPES.get(ext, "application/octet-stream"),
        filename=stem + ext,
    )


def _is_stale_bat_enhanced_cache(cache_path: str, original_wav_path: str) -> bool:
    """
    True if a cached "enhanced" file for a bat recording looks like it was
    actually produced by the OLD, wrong bird-enhance function rather than
    the correct downshift — i.e. it doesn't have a materially lower sample
    rate than the original. Real fix for "enhancing doesn't always work":
    any bat recording that was enhanced even once before this fix deployed
    has a stale cache sitting at the same path, and a cache-hit check alone
    can't tell the difference — it would be served forever regardless of
    which function originally produced it. downshift_bat_clip() always
    lowers the sample rate (that's the whole mechanism); enhance_audio()
    never resamples at all, so a cached file at the original rate is a
    reliable signal the cache predates this fix.
    """
    import soundfile as sf
    try:
        orig_info = sf.info(original_wav_path)
        cached_info = sf.info(cache_path)
        # A real downshift meaningfully lowers the rate (10x by default) —
        # anything not clearly lower (allowing generous margin) is stale.
        return cached_info.samplerate >= orig_info.samplerate * 0.9
    except Exception:
        # Can't tell — safer to treat as stale and regenerate than to keep
        # serving a file we can't actually verify is correct.
        return True


@router.get("/{recording_id}/audio/enhanced")
def stream_audio_enhanced(recording_id: str, db: Session = Depends(get_db)):
    """
    Stream an enhanced version of the full recording.

    For bird recordings: bandpass filtered to the bird-vocalization
    frequency range plus spectral-gating noise reduction, as an alternate
    "isolate the bird calls" playback option.

    For bat recordings: a fundamentally different transform — frequency
    downshift (time expansion) via downshift_bat_clip(), not noise
    reduction. Bat echolocation runs ~15-120kHz, inaudible or barely
    perceptible to humans at native sample rate; there's nothing to
    "clean up" the way there is for bird calls, the signal itself needs
    to be shifted into hearing range. This endpoint previously always
    called the bird-only enhance_audio() regardless of recording type,
    so "Enhance" was a no-op for bat clips — silent audio stayed silent.
    downshift_bat_clip() already existed, correctly implemented, just
    never actually invoked from anywhere.

    Generated on first request and cached on disk; subsequent requests are
    served directly from the cache file with no reprocessing — EXCEPT for
    bat recordings, where a stale pre-fix cache (see
    _is_stale_bat_enhanced_cache) is detected and regenerated rather than
    served forever, which is exactly why "enhancing doesn't always work"
    was reported: recordings enhanced even once before this fix deployed
    would otherwise keep serving their old, wrong cached result
    indefinitely regardless of any code fix.
    """
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec or not os.path.exists(rec.wav_path):
        raise HTTPException(status_code=404, detail="Audio file not found")

    cache_path = os.path.join(settings.enhanced_dir, f"{_nr_cache_id(recording_id, rec.is_bat)}_enhanced.wav")
    if os.path.exists(cache_path):
        if rec.is_bat and _is_stale_bat_enhanced_cache(cache_path, rec.wav_path):
            logger.info("Regenerating stale pre-fix bat-enhanced cache for recording %s", recording_id)
            try:
                os.remove(cache_path)
            except OSError:
                pass
        else:
            return FileResponse(
                cache_path, media_type="audio/wav",
                filename=f"enhanced_{rec.filename}",
                headers={"Cache-Control": "public, max-age=2592000, immutable"},
            )

    try:
        if rec.is_bat:
            generated = processor.downshift_bat_clip(rec.wav_path, settings.enhanced_dir, recording_id)
        else:
            # apply_bandpass=False: rumble removal is now its own separate
            # toggle (see /audio/rumble-removed below), requested directly
            # as an independent option from noise reduction rather than
            # bundled into "Enhanced" — a person may want just one or the
            # other, or both. "Enhanced" alone is back to pure spectral-
            # gating noise reduction, its original scope before the
            # rumble filter was folded in here.
            generated = processor.enhance_audio(rec.wav_path, settings.enhanced_dir, _nr_cache_id(recording_id), apply_bandpass=False)
        return FileResponse(
            generated, media_type="audio/wav",
            filename=f"enhanced_{rec.filename}",
            headers={"Cache-Control": "public, max-age=2592000, immutable"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audio enhancement failed: {e}")


@router.get("/{recording_id}/audio/rumble-removed")
def stream_audio_rumble_removed(recording_id: str, hz: Optional[int] = None, db: Session = Depends(get_db)):
    """
    Stream a rumble-cleaned version of the full recording — a plain
    high-pass filter only, no noise reduction. Requested directly
    as its own separate, independent option from Enhanced (noise
    reduction) — combinable with it via /audio/rumble-removed-enhanced
    below, mirroring how De-wobbled and Enhanced already combine for bat
    recordings.

    `hz` (optional query param): manual cutoff frequency, matching
    LiveDetect.jsx's own "Cut low rumble" slider (0-2000Hz range) —
    requested directly, since the species-aware automatic cutoff alone
    wasn't giving a person the same direct control Live Detect already
    has. Omitted or None falls back to the automatic species-aware
    cutoff (recommended_high_pass_hz), unchanged default behavior.

    Bird only — a bat recording's own "rumble" isn't really analogous
    (its issue is being inaudible altogether, which downshift_bat_clip()
    already exists to solve; a plain high-pass on inaudible ultrasonic
    content wouldn't accomplish anything a person could hear).
    """
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec or not os.path.exists(rec.wav_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    if rec.is_bat:
        raise HTTPException(status_code=404, detail="Rumble removal not available for bat recordings")

    cache_id = f"{recording_id}_rumbleremoved_hz{hz}_{DSP_VERSION}" if hz is not None else f"{recording_id}_rumbleremoved_{DSP_VERSION}"
    cache_path = os.path.join(settings.enhanced_dir, f"{cache_id}_enhanced.wav")
    if os.path.exists(cache_path):
        return FileResponse(
            cache_path, media_type="audio/wav",
            filename=f"rumble_removed_{rec.filename}",
            headers={"Cache-Control": "public, max-age=2592000, immutable"},
        )

    try:
        low_hz = float(hz) if hz is not None else recommended_high_pass_hz([d.common_name for d in rec.detections])
        generated = processor.enhance_audio(
            rec.wav_path, settings.enhanced_dir, cache_id,
            low_hz=low_hz, apply_noise_reduction=False,
        )
        return FileResponse(
            generated, media_type="audio/wav",
            filename=f"rumble_removed_{rec.filename}",
            headers={"Cache-Control": "public, max-age=2592000, immutable"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rumble removal failed: {e}")


@router.get("/{recording_id}/audio/rumble-removed-enhanced")
def stream_audio_rumble_removed_enhanced(recording_id: str, hz: Optional[int] = None, db: Session = Depends(get_db)):
    """
    Both /audio/rumble-removed and /audio/enhanced at once — the
    high-pass AND spectral-gating noise reduction together, for
    when both toggles are on simultaneously. Same bird-only scope, and
    same `hz` manual-cutoff override, as /audio/rumble-removed above.
    """
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec or not os.path.exists(rec.wav_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    if rec.is_bat:
        raise HTTPException(status_code=404, detail="Rumble removal not available for bat recordings")

    cache_id = f"{recording_id}_rumbleremoved_enhanced_hz{hz}_{DSP_VERSION}" if hz is not None else f"{recording_id}_rumbleremoved_enhanced_{DSP_VERSION}"
    cache_path = os.path.join(settings.enhanced_dir, f"{cache_id}_enhanced.wav")
    if os.path.exists(cache_path):
        return FileResponse(
            cache_path, media_type="audio/wav",
            filename=f"rumble_removed_enhanced_{rec.filename}",
            headers={"Cache-Control": "public, max-age=2592000, immutable"},
        )

    try:
        low_hz = float(hz) if hz is not None else recommended_high_pass_hz([d.common_name for d in rec.detections])
        generated = processor.enhance_audio(
            rec.wav_path, settings.enhanced_dir, cache_id,
            low_hz=low_hz, apply_bandpass=True, apply_noise_reduction=True,
        )
        return FileResponse(
            generated, media_type="audio/wav",
            filename=f"rumble_removed_enhanced_{rec.filename}",
            headers={"Cache-Control": "public, max-age=2592000, immutable"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rumble removal failed: {e}")


@router.get("/{recording_id}/audio/ai-enhanced")
def stream_audio_ai_enhanced(recording_id: str, db: Session = Depends(get_db)):
    """
    Stream an AI Enhance (neural-network denoised) version of the full
    recording — a separate, independent alternative to /audio/enhanced's
    classical bandpass+spectral-gating pipeline, using the pretrained
    model in services/ai_enhance.py. See that module's own docstring for
    the real 16kHz-model bandwidth limitation and why this is bird-only.

    Requires AppSettings.ai_enhance_enabled (off by default — the model
    needs torch/torchaudio installed, an optional heavy dependency, see
    requirements.txt) — a disabled/unavailable feature returns 400 with
    a clear message rather than a confusing 500 mid-processing.

    Generated on first request and cached on disk, same convention as
    every other endpoint in this cluster.
    """
    app_s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if not app_s or not app_s.ai_enhance_enabled:
        raise HTTPException(status_code=400, detail="AI Enhance is not enabled in Settings")

    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec or not os.path.exists(rec.wav_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    if rec.is_bat:
        raise HTTPException(status_code=404, detail="AI Enhance is not available for bat recordings")

    cache_path = os.path.join(settings.enhanced_dir, f"{recording_id}_{ai_enhance.AI_ENHANCE_VERSION}_aienhanced.wav")
    if os.path.exists(cache_path):
        return FileResponse(
            cache_path, media_type="audio/wav",
            filename=f"ai_enhanced_{rec.filename}",
            headers={"Cache-Control": "public, max-age=2592000, immutable"},
        )

    if not ai_enhance.is_available():
        raise HTTPException(
            status_code=400,
            detail="AI Enhance is enabled but not usable on this server — "
                   "torch/torchaudio isn't installed or the model failed to "
                   "load, check server logs (see requirements.txt)",
        )

    try:
        dry = app_s.ai_enhance_dry if app_s.ai_enhance_dry is not None else 0.1
        low_hz = recommended_high_pass_hz([d.common_name for d in rec.detections])
        generated = ai_enhance.enhance_wav(rec.wav_path, settings.enhanced_dir, f"{recording_id}_{ai_enhance.AI_ENHANCE_VERSION}", dry=dry, low_hz=low_hz)
        return FileResponse(
            generated, media_type="audio/wav",
            filename=f"ai_enhanced_{rec.filename}",
            headers={"Cache-Control": "public, max-age=2592000, immutable"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Enhance failed: {e}")

@router.get("/{recording_id}/audio/dewobbled")
def stream_audio_dewobbled(recording_id: str, db: Session = Depends(get_db)):
    """
    Experimental, bat recordings only: the original native-rate audio
    with the persistent AudioMoth/fan interference ridge attenuated (see
    AudioProcessor.remove_bat_wobble for the technique and its measured
    tradeoffs). A third playback option alongside Original/Enhanced —
    combinable with Enhanced (see /audio/dewobbled-enhanced below), not
    exclusive with it; this endpoint specifically serves the de-wobbled
    audio at its ORIGINAL native rate, not time-expanded. This is the
    canonical endpoint RecordingDetail.jsx actually calls; bat_activity.py
    has its own equivalent for API-compatibility callers still pointed at
    that router directly, same relationship as the two /audio/enhanced
    endpoints.

    Generated on first request and cached, same convention as
    /audio/enhanced — no staleness check needed here, since there's no
    pre-existing older implementation's cached output to invalidate.
    """
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec or not rec.wav_path or not os.path.exists(rec.wav_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    if not rec.is_bat:
        raise HTTPException(status_code=400, detail="Wobble removal only applies to bat recordings")

    cache_path = os.path.join(settings.enhanced_dir, f"{recording_id}_dewobbled.wav")
    if not os.path.exists(cache_path):
        try:
            cache_path = processor.remove_bat_wobble(rec.wav_path, settings.enhanced_dir, recording_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Wobble removal failed: {e}")

    return FileResponse(
        cache_path, media_type="audio/wav",
        filename=f"dewobbled_{rec.filename}",
        headers={"Cache-Control": "public, max-age=2592000, immutable"},
    )


@router.get("/{recording_id}/audio/dewobbled-enhanced")
def stream_audio_dewobbled_enhanced(recording_id: str, db: Session = Depends(get_db)):
    """
    Both De-wobbled AND Enhanced together — the two toggles are
    independently combinable in the UI, not mutually exclusive, so this
    fourth combination needs its own endpoint/cache file rather than
    picking one when both are on.

    Order matters and is fixed: de-wobble FIRST (on the original native
    sample rate, where remove_bat_wobble's band_hz assumes ultrasonic
    frequencies), THEN time-expand the already-cleaned audio. Doing it
    in the other order would require also scaling band_hz down to match
    the already-downshifted rate, which is unnecessary complexity when
    de-wobble-then-shift produces the same audible result more directly.

    Reuses AudioProcessor.remove_bat_wobble and .downshift_bat_clip as-is
    rather than a third, separate implementation — chains the existing
    de-wobbled cache (generating it first if it doesn't exist yet) into
    downshift_bat_clip using a distinct cache_id so the result lands at
    its own {recording_id}_dewobbled_enhanced.wav rather than colliding
    with either single-toggle cache file.
    """
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec or not rec.wav_path or not os.path.exists(rec.wav_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    if not rec.is_bat:
        raise HTTPException(status_code=400, detail="Wobble removal only applies to bat recordings")

    combined_path = os.path.join(settings.enhanced_dir, f"{recording_id}_dewobbled_enhanced.wav")
    if not os.path.exists(combined_path):
        try:
            dewobbled_path = os.path.join(settings.enhanced_dir, f"{recording_id}_dewobbled.wav")
            if not os.path.exists(dewobbled_path):
                dewobbled_path = processor.remove_bat_wobble(rec.wav_path, settings.enhanced_dir, recording_id)
            combined_path = processor.downshift_bat_clip(
                dewobbled_path, settings.enhanced_dir, f"{recording_id}_dewobbled",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Combined de-wobble + enhance failed: {e}")

    return FileResponse(
        combined_path, media_type="audio/wav",
        filename=f"dewobbled_enhanced_{rec.filename}",
        headers={"Cache-Control": "public, max-age=2592000, immutable"},
    )


@router.get("/{recording_id}/spectrogram/enhanced")
def get_spectrogram_enhanced(recording_id: str, scale: str = "auto", db: Session = Depends(get_db)):
    """
    Return a spectrogram PNG generated from the noise-reduced "Enhanced"
    audio (see enhance_audio()'s docstring and the sibling
    /audio/enhanced endpoint) rather than the original recording — the
    spectrogram counterpart to the Enhanced playback toggle already on
    the recording detail page, which previously only swapped the audio
    source while the spectrogram image stayed the original regardless of
    which playback mode was selected.

    Same two-layer caching strategy as the original /spectrogram
    endpoint (per-file disk cache + immutable HTTP cache headers), with
    one additional optimization: if the enhanced WAV was already
    generated and cached by a prior /audio/enhanced request (the common
    case — a person typically toggles audio playback before or instead
    of caring about the spectrogram), this reuses that cached file
    rather than re-running noise reduction from scratch. Measured
    directly against a representative ~9s recording: enhancement alone
    is ~900ms, spectrogram generation from already-enhanced audio is
    ~180ms — so the common case (enhanced audio already cached) comfortably
    clears a 1-second budget, and even the worst case (nothing cached yet,
    both steps run back to back) lands right around it rather than well
    past it.
    """
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")

    if rec.is_bat:
        # Bat enhancement is a frequency downshift (see
        # downshift_bat_clip()), a fundamentally different transform from
        # bird noise-reduction with no enhanced-spectrogram counterpart
        # built — and bat spectrograms are already plotted at native
        # sample rate with a linear Hz axis specifically so nothing above
        # the recorded ultrasonic range gets lost, which a downshifted
        # version would defeat the purpose of visualizing anyway.
        raise HTTPException(status_code=404, detail="Enhanced spectrogram not available for bat recordings")

    spec_dir = settings.spectrograms_dir
    low = _low_pitch_view(rec, scale)
    enhanced_spec_path = _low_suffix(_enhanced_spec_path(recording_id), low)

    if os.path.exists(enhanced_spec_path):
        return FileResponse(
            enhanced_spec_path, media_type="image/png",
            headers={"Cache-Control": "public, max-age=2592000, immutable", "Vary": "Accept-Encoding"},
        )

    if not rec.wav_path or not os.path.exists(rec.wav_path):
        raise HTTPException(status_code=404, detail="WAV file not found")

    try:
        # Reuse the enhanced WAV if /audio/enhanced already generated and
        # cached it; only run noise reduction ourselves on a genuine
        # cold-cache first request.
        enhanced_wav_path = os.path.join(settings.enhanced_dir, f"{_nr_cache_id(recording_id)}_enhanced.wav")
        if not os.path.exists(enhanced_wav_path):
            # apply_bandpass=False, matching /audio/enhanced's own updated
            # scope (pure noise reduction now — rumble removal moved to
            # its own separate endpoint/cache) — this path can be the
            # FIRST to generate the shared cache, so it needs to match.
            enhanced_wav_path = processor.enhance_audio(rec.wav_path, settings.enhanced_dir, _nr_cache_id(recording_id), apply_bandpass=False)

        # Display threshold + visible detections, same as the original
        # spectrogram endpoint, so the enhanced view's detection-box
        # overlay matches what the person currently sees elsewhere on
        # the page rather than showing every detection regardless of the
        # confidence filter they've configured.
        from ..models import AppSettings
        app_s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        display_min_conf = float(getattr(app_s, "min_confidence_display", 0.0) or 0.0) if app_s else 0.0
        visible_dets = [
            {"common_name": d.common_name, "confidence": d.confidence,
             "start_time": d.start_time, "end_time": d.end_time}
            for d in rec.detections
            if d.confidence >= display_min_conf
        ]

        generated = processor.generate_spectrogram(
            enhanced_wav_path, spec_dir, recording_id,
            detections=visible_dets or None,
            conf_key=f"enhanced_{DSP_VERSION}" + ("_low" if low else ""), low_pitch=low,
            color_palette=getattr(app_s, "detection_color_palette", None) or "vivid",
        )
        logger.debug(
            "Enhanced spectrogram generated for %s from %s (size=%d bytes)",
            recording_id, enhanced_wav_path, os.path.getsize(enhanced_wav_path) if os.path.exists(enhanced_wav_path) else -1,
        )
        return FileResponse(
            generated, media_type="image/png",
            headers={"Cache-Control": "public, max-age=2592000, immutable", "Vary": "Accept-Encoding"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Enhanced spectrogram generation failed: {e}")


@router.get("/{recording_id}/spectrogram/ai-enhanced")
def get_spectrogram_ai_enhanced(recording_id: str, scale: str = "auto", db: Session = Depends(get_db)):
    """
    AI Enhance's spectrogram counterpart — mirrors /spectrogram/enhanced
    above exactly, but from the neural-denoised audio (services/
    ai_enhance.py) instead of the classical noisereduce pipeline.
    Reported directly: toggling "AI Enhance" changed the audio but the
    spectrogram image stayed the original, same gap the classical
    Enhanced toggle had before /spectrogram/enhanced existed.

    Reuses the /audio/ai-enhanced WAV if already cached rather than
    re-running the neural-net pass — same "reuse the sibling endpoint's
    cache" optimization /spectrogram/enhanced already uses.
    """
    app_s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if not app_s or not app_s.ai_enhance_enabled:
        raise HTTPException(status_code=400, detail="AI Enhance is not enabled in Settings")

    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    if rec.is_bat:
        raise HTTPException(status_code=404, detail="AI Enhance is not available for bat recordings")

    spec_dir = settings.spectrograms_dir
    low = _low_pitch_view(rec, scale)
    ai_spec_path = _low_suffix(os.path.join(spec_dir, f"{recording_id}_spectrogram_aienhanced_{ai_enhance.AI_ENHANCE_VERSION}.png"), low)
    if os.path.exists(ai_spec_path):
        return FileResponse(
            ai_spec_path, media_type="image/png",
            headers={"Cache-Control": "public, max-age=2592000, immutable", "Vary": "Accept-Encoding"},
        )

    if not rec.wav_path or not os.path.exists(rec.wav_path):
        raise HTTPException(status_code=404, detail="WAV file not found")

    if not ai_enhance.is_available():
        raise HTTPException(
            status_code=400,
            detail="AI Enhance is enabled but not usable on this server — "
                   "torch/torchaudio isn't installed or the model failed to "
                   "load, check server logs (see requirements.txt)",
        )

    try:
        low_hz = recommended_high_pass_hz([d.common_name for d in rec.detections])
        ai_wav_path = os.path.join(settings.enhanced_dir, f"{recording_id}_{ai_enhance.AI_ENHANCE_VERSION}_aienhanced.wav")
        if not os.path.exists(ai_wav_path):
            dry = app_s.ai_enhance_dry if app_s.ai_enhance_dry is not None else 0.1
            ai_wav_path = ai_enhance.enhance_wav(rec.wav_path, settings.enhanced_dir, f"{recording_id}_{ai_enhance.AI_ENHANCE_VERSION}", dry=dry, low_hz=low_hz)

        display_min_conf = float(getattr(app_s, "min_confidence_display", 0.0) or 0.0)
        visible_dets = [
            {"common_name": d.common_name, "confidence": d.confidence,
             "start_time": d.start_time, "end_time": d.end_time}
            for d in rec.detections
            if d.confidence >= display_min_conf
        ]

        generated = processor.generate_spectrogram(
            ai_wav_path, spec_dir, recording_id,
            detections=visible_dets or None,
            conf_key="aienhanced" + ("_low" if low else ""), low_pitch=low,
            color_palette=getattr(app_s, "detection_color_palette", None) or "vivid",
        )
        return FileResponse(
            generated, media_type="image/png",
            headers={"Cache-Control": "public, max-age=2592000, immutable", "Vary": "Accept-Encoding"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Enhance spectrogram generation failed: {e}")

@router.get("/{recording_id}/spectrogram/rumble-removed")
def get_spectrogram_rumble_removed(recording_id: str, scale: str = "auto", db: Session = Depends(get_db)):
    """
    Spectrogram counterpart to the Rumble Removed playback toggle —
    mirrors /spectrogram/enhanced above exactly, but from the plain
    high-pass-filtered audio (see /audio/rumble-removed) instead of
    the noise-reduced one. Reported directly: toggling Rumble Removed
    changed the audio but the spectrogram image stayed the original,
    the same gap /spectrogram/enhanced and /spectrogram/ai-enhanced
    already had fixed for their own toggles.

    Reuses the /audio/rumble-removed WAV if already cached rather than
    re-running the filter.
    """
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    if rec.is_bat:
        raise HTTPException(status_code=404, detail="Rumble removal is not available for bat recordings")

    spec_dir = settings.spectrograms_dir
    low = _low_pitch_view(rec, scale)
    spec_path = _low_suffix(os.path.join(spec_dir, f"{recording_id}_spectrogram_rumbleremoved_{DSP_VERSION}.png"), low)
    if os.path.exists(spec_path):
        return FileResponse(
            spec_path, media_type="image/png",
            headers={"Cache-Control": "public, max-age=2592000, immutable", "Vary": "Accept-Encoding"},
        )

    if not rec.wav_path or not os.path.exists(rec.wav_path):
        raise HTTPException(status_code=404, detail="WAV file not found")

    try:
        wav_path = os.path.join(settings.enhanced_dir, f"{recording_id}_rumbleremoved_{DSP_VERSION}_enhanced.wav")
        if not os.path.exists(wav_path):
            low_hz = recommended_high_pass_hz([d.common_name for d in rec.detections])
            wav_path = processor.enhance_audio(
                rec.wav_path, settings.enhanced_dir, f"{recording_id}_rumbleremoved_{DSP_VERSION}",
                low_hz=low_hz, apply_noise_reduction=False,
            )

        from ..models import AppSettings
        app_s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        display_min_conf = float(getattr(app_s, "min_confidence_display", 0.0) or 0.0) if app_s else 0.0
        visible_dets = [
            {"common_name": d.common_name, "confidence": d.confidence,
             "start_time": d.start_time, "end_time": d.end_time}
            for d in rec.detections
            if d.confidence >= display_min_conf
        ]

        generated = processor.generate_spectrogram(
            wav_path, spec_dir, recording_id,
            detections=visible_dets or None,
            conf_key=f"rumbleremoved_{DSP_VERSION}" + ("_low" if low else ""), low_pitch=low,
            color_palette=getattr(app_s, "detection_color_palette", None) or "vivid",
        )
        return FileResponse(
            generated, media_type="image/png",
            headers={"Cache-Control": "public, max-age=2592000, immutable", "Vary": "Accept-Encoding"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rumble-removed spectrogram generation failed: {e}")


@router.get("/{recording_id}/spectrogram/rumble-removed-enhanced")
def get_spectrogram_rumble_removed_enhanced(recording_id: str, scale: str = "auto", db: Session = Depends(get_db)):
    """
    Spectrogram counterpart to Rumble Removed + Enhanced combined —
    same reasoning as get_spectrogram_rumble_removed above, from the
    combined high-pass + noise-reduction audio (/audio/rumble-removed-enhanced).
    """
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    if rec.is_bat:
        raise HTTPException(status_code=404, detail="Rumble removal is not available for bat recordings")

    spec_dir = settings.spectrograms_dir
    low = _low_pitch_view(rec, scale)
    spec_path = _low_suffix(os.path.join(spec_dir, f"{recording_id}_spectrogram_rumbleremovedenhanced_{DSP_VERSION}.png"), low)
    if os.path.exists(spec_path):
        return FileResponse(
            spec_path, media_type="image/png",
            headers={"Cache-Control": "public, max-age=2592000, immutable", "Vary": "Accept-Encoding"},
        )

    if not rec.wav_path or not os.path.exists(rec.wav_path):
        raise HTTPException(status_code=404, detail="WAV file not found")

    try:
        wav_path = os.path.join(settings.enhanced_dir, f"{recording_id}_rumbleremoved_enhanced_{DSP_VERSION}_enhanced.wav")
        if not os.path.exists(wav_path):
            low_hz = recommended_high_pass_hz([d.common_name for d in rec.detections])
            wav_path = processor.enhance_audio(
                rec.wav_path, settings.enhanced_dir, f"{recording_id}_rumbleremoved_enhanced_{DSP_VERSION}",
                low_hz=low_hz, apply_bandpass=True, apply_noise_reduction=True,
            )

        from ..models import AppSettings
        app_s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        display_min_conf = float(getattr(app_s, "min_confidence_display", 0.0) or 0.0) if app_s else 0.0
        visible_dets = [
            {"common_name": d.common_name, "confidence": d.confidence,
             "start_time": d.start_time, "end_time": d.end_time}
            for d in rec.detections
            if d.confidence >= display_min_conf
        ]

        generated = processor.generate_spectrogram(
            wav_path, spec_dir, recording_id,
            detections=visible_dets or None,
            conf_key=f"rumbleremovedenhanced_{DSP_VERSION}" + ("_low" if low else ""), low_pitch=low,
            color_palette=getattr(app_s, "detection_color_palette", None) or "vivid",
        )
        return FileResponse(
            generated, media_type="image/png",
            headers={"Cache-Control": "public, max-age=2592000, immutable", "Vary": "Accept-Encoding"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rumble-removed+Enhanced spectrogram generation failed: {e}")


@router.get("/{recording_id}/spectrogram")
def get_spectrogram(recording_id: str, thumb: bool = False, scale: str = "auto", db: Session = Depends(get_db)):
    """
    Return the spectrogram PNG for a recording.

    Caching strategy (two layers):
      1. Per-threshold file cache: each confidence threshold gets its own PNG file
         named  {id}_spectrogram_{threshold_key}.png  so we never regenerate an
         already-computed file for a given threshold.
      2. HTTP cache headers: immutable 30-day cache once a file exists on disk.
         The frontend cache-busts via the threshold query-param when settings change.

    Pass ?thumb=true for a small, fast-loading thumbnail variant — used by
    the recordings list grid view, which previously fetched the exact same
    full-resolution PNG used on the detail page for what's displayed as a
    small grid cell. Cached under its own `_thumb` filename suffix so it
    never collides with or gets confused for the full-resolution version.
    """
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")

    # Bat recordings have no confidence threshold to bucket by (one
    # Detection, confidence=1.0, no per-species filtering applies) and use
    # a structurally different spectrogram (native sample rate, linear Hz
    # axis, no mel scale or detection-box overlay — see
    # generate_bat_spectrogram()'s docstring). Branch here rather than
    # falling through to the conf_key logic below, which builds a filename
    # this recording's actual spectrogram was never saved under, and would
    # — on a cache miss — call the BIRD generator against ultrasonic audio,
    # resampling away everything above ~11kHz and producing a useless image.
    # Bat recordings have no separate thumbnail variant — `thumb` is
    # ignored for these, since they aren't shown in the grid-thumbnail
    # context that motivated adding thumbnails in the first place.
    if rec.is_bat:
        bat_spec_path = os.path.join(settings.spectrograms_dir, f"{recording_id}_spectrogram_bat.png")
        if os.path.exists(bat_spec_path):
            return FileResponse(
                bat_spec_path, media_type="image/png",
                headers={"Cache-Control": "public, max-age=2592000, immutable", "Vary": "Accept-Encoding"},
            )
        if not rec.wav_path or not os.path.exists(rec.wav_path):
            raise HTTPException(status_code=404, detail="WAV file not found")
        try:
            generated = processor.generate_bat_spectrogram(rec.wav_path, settings.spectrograms_dir, recording_id)
            rec.spectrogram_path = generated
            db.commit()
            return FileResponse(
                generated, media_type="image/png",
                headers={"Cache-Control": "public, max-age=2592000, immutable", "Vary": "Accept-Encoding"},
            )
        except Exception as e:
            fallback = rec.spectrogram_path
            if fallback and os.path.exists(fallback):
                return FileResponse(fallback, media_type="image/png",
                                    headers={"Cache-Control": "public, max-age=300"})
            raise HTTPException(status_code=500, detail=f"Bat spectrogram generation failed: {e}")

    # Current display threshold
    from ..models import AppSettings
    app_s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    display_min_conf = float(getattr(app_s, "min_confidence_display", 0.0) or 0.0) if app_s else 0.0

    # Stable cache key: e.g. "0", "25", "50", "75"
    conf_key = str(int(round(display_min_conf * 100)))
    low = _low_pitch_view(rec, scale)
    view_key = conf_key + ("_low" if low else "")

    # Check whether the per-threshold file already exists (the name includes
    # the colour palette, as generate_spectrogram saves it).
    from ..services.audio_processor import spectrogram_filename
    _palette = getattr(app_s, "detection_color_palette", None) or "vivid"
    spec_dir  = settings.spectrograms_dir
    spec_path = os.path.join(spec_dir, spectrogram_filename(recording_id, view_key, thumb, _palette))

    # Fast path: file already on disk → serve with immutable cache headers
    if os.path.exists(spec_path):
        return FileResponse(
            spec_path, media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=2592000, immutable",
                "Vary": "Accept-Encoding",
            },
        )

    # Need to generate — filter detections to current threshold
    if not rec.wav_path or not os.path.exists(rec.wav_path):
        # No audio to regenerate from — this is the normal, expected case
        # for an archived recording (see Recording.archived_at) once a
        # confidence-threshold change invalidates the per-threshold cache
        # key above. The spectrogram is supposed to be permanently
        # preserved for an archived recording, so rather than 404 outright,
        # fall back to ANY other cached threshold variant that still
        # exists on disk — a slightly-different-threshold spectrogram
        # (just a different set of detection-box overlays on the same
        # underlying image) is far better than showing nothing at all.
        # Probe likely names instead of globbing: the folder holds hundreds
        # of thousands of files, and a glob lists all of them per request.
        _keys = ([view_key] if low else []) + [conf_key, "0"] + [str(k) for k in range(101) if str(k) not in (conf_key, "0")]
        _pals = [_palette] + (["vivid"] if _palette != "vivid" else [])
        fallback_candidates = []
        for _k in _keys:
            for _p in _pals:
                _names = [spectrogram_filename(recording_id, _k, thumb, _p)]
                if thumb:   # thumbnails from before "_thumb2"
                    _names.append(spectrogram_filename(recording_id, _k, False, _p).replace(".png", "_thumb.png")
                                  if _p == "vivid" else f"{recording_id}_spectrogram_{_k}_thumb_pal-{_p}.png")
                for _n in _names:
                    _cand = os.path.join(spec_dir, _n)
                    if os.path.exists(_cand):
                        fallback_candidates.append(_cand)
            if fallback_candidates:
                break
        if fallback_candidates:
            logger.debug(
                "Spectrogram cache miss for %s at threshold %s%s, no audio to regenerate "
                "(likely archived) — serving fallback %s instead",
                recording_id, conf_key, " (thumb)" if thumb else "", fallback_candidates[0],
            )
            return FileResponse(
                fallback_candidates[0], media_type="image/png",
                headers={"Cache-Control": "public, max-age=2592000, immutable", "Vary": "Accept-Encoding"},
            )
        raise HTTPException(status_code=404, detail="WAV file not found")

    visible_dets = [
        {"common_name": d.common_name, "confidence": d.confidence,
         "start_time": d.start_time, "end_time": d.end_time}
        for d in rec.detections
        if d.confidence >= display_min_conf
    ]

    try:
        generated = processor.generate_spectrogram(
            rec.wav_path, spec_dir, recording_id,
            detections=visible_dets or None,
            conf_key=view_key,
            thumb=thumb,
            low_pitch=low,
            color_palette=getattr(app_s, "detection_color_palette", None) or "vivid",
        )
        # Update DB pointer to the threshold=0 file (canonical cached path)
        # — only for the full-resolution version; the thumb variant has no
        # corresponding DB column to point at.
        if view_key == "0" and not thumb:
            rec.spectrogram_path = generated
            db.commit()
        return FileResponse(
            generated, media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=2592000, immutable",
                "Vary": "Accept-Encoding",
            },
        )
    except Exception as e:
        # Serve any existing cached version rather than returning 500
        fallback = rec.spectrogram_path if not thumb else None
        if fallback and os.path.exists(fallback):
            return FileResponse(fallback, media_type="image/png",
                                headers={"Cache-Control": "public, max-age=300"})
        raise HTTPException(status_code=500, detail=f"Spectrogram generation failed: {e}")


@router.get("/{recording_id}/clip/{detection_id}")
def get_clip(recording_id: str, detection_id: str, db: Session = Depends(get_db)):
    """Return a short audio clip around a specific detection."""
    det = db.query(Detection).filter(
        Detection.id == detection_id,
        Detection.recording_id == recording_id,
    ).first()
    if not det:
        raise HTTPException(status_code=404, detail="Detection not found")

    if not det.clip_path or not os.path.exists(det.clip_path):
        # Extract on demand
        rec = db.query(Recording).filter(Recording.id == recording_id).first()
        if not rec:
            raise HTTPException(status_code=404, detail="Recording not found")
        try:
            clip_path = processor.extract_clip(
                rec.wav_path, settings.clips_dir, det.id,
                det.start_time, det.end_time, padding=settings.clip_padding_seconds,
                is_bat=rec.is_bat,
            )
            det.clip_path = clip_path
            db.commit()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Clip extraction failed: {e}")

    # extract_clip() writes new clips as MP3 for birds, FLAC for bats (see
    # its own docstring — bats need lossless, MP3's ultrasonic content
    # loss was caught and fixed directly), so .wav/.mp3/.flac clips can
    # all exist depending on when and what kind a detection was — media
    # type and the download filename's own extension need to match
    # whichever this detection actually has, not assume one format.
    ext = det.clip_path.rsplit(".", 1)[-1].lower() if "." in det.clip_path else "wav"
    clip_media_types = {"mp3": "audio/mpeg", "flac": "audio/flac", "wav": "audio/wav"}
    media_type = clip_media_types.get(ext, "audio/wav")
    return FileResponse(
        det.clip_path,
        media_type=media_type,
        filename=f"chirp_clip_{det.common_name.replace(' ', '_')}_{det.id[:8]}.{ext}",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/{recording_id}/clip/{detection_id}/enhanced")
def get_clip_enhanced(recording_id: str, detection_id: str, db: Session = Depends(get_db)):
    """
    Enhanced version of a single detection's clip.

    For bird detections: same bandpass + spectral-gating pipeline as the
    full-recording enhanced endpoint, scoped to just the short clip around
    this detection.

    For bat detections: frequency downshift via downshift_bat_clip(), same
    real bug fix and rationale as the full-recording /audio/enhanced
    endpoint — this previously always called the bird-only enhance_audio()
    regardless of recording type, so "Enhance" was a no-op for bat clips.

    Generated from the (already-extracted) raw clip on first request and
    cached on disk.
    """
    det = db.query(Detection).filter(
        Detection.id == detection_id,
        Detection.recording_id == recording_id,
    ).first()
    if not det:
        raise HTTPException(status_code=404, detail="Detection not found")

    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")

    if not det.clip_path or not os.path.exists(det.clip_path):
        # Extract the raw clip first (same on-demand logic as get_clip) —
        # done before the cache check below since a valid clip_path is
        # needed as the reference "original" for stale-cache detection.
        try:
            clip_path = processor.extract_clip(
                rec.wav_path, settings.clips_dir, det.id,
                det.start_time, det.end_time, padding=settings.clip_padding_seconds,
                is_bat=rec.is_bat,
            )
            det.clip_path = clip_path
            db.commit()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Clip extraction failed: {e}")

    cache_path = os.path.join(settings.enhanced_dir, f"{det.id}_{DSP_VERSION}_enhanced.wav")
    if os.path.exists(cache_path):
        if rec.is_bat and _is_stale_bat_enhanced_cache(cache_path, det.clip_path):
            logger.info("Regenerating stale pre-fix bat-enhanced cache for detection %s", det.id)
            try:
                os.remove(cache_path)
            except OSError:
                pass
        else:
            return FileResponse(
                cache_path, media_type="audio/wav",
                filename=f"enhanced_clip_{det.common_name.replace(' ', '_')}_{det.id[:8]}.wav",
                headers={"Cache-Control": "public, max-age=2592000, immutable"},
            )

    try:
        # extract_clip() writes new bird clips as MP3 and new bat clips as
        # FLAC (see its own docstring) — sf.read() inside
        # enhance_audio/downshift_bat_clip is libsndfile-backed, which
        # reads WAV and FLAC natively but can't read MP3 at all. Only
        # decode when the clip is actually MP3; FLAC (and existing WAV
        # clips) pass straight through unmodified — confirmed FLAC is a
        # native libsndfile read format, so this isn't a case of "works
        # but slow", it's simply unnecessary for that format.
        clip_for_enhance = det.clip_path
        tmp_decoded_wav = None
        if det.clip_path.lower().endswith(".mp3"):
            tmp_decoded_wav = os.path.join(settings.enhanced_dir, f"{det.id}_srcdecode_tmp.wav")
            decode_result = subprocess.run(
                ["ffmpeg", "-y", "-i", det.clip_path, tmp_decoded_wav],
                capture_output=True, timeout=30,
            )
            if decode_result.returncode != 0 or not os.path.exists(tmp_decoded_wav):
                raise RuntimeError(
                    f"Could not decode clip for enhancement: "
                    f"{decode_result.stderr.decode(errors='replace')[-300:]}"
                )
            clip_for_enhance = tmp_decoded_wav

        try:
            if rec.is_bat:
                generated = processor.downshift_bat_clip(clip_for_enhance, settings.enhanced_dir, f"{det.id}_{DSP_VERSION}")
            else:
                # The clip was extracted with `padding` seconds before/after the
                # detection's actual start/end (clamped at the recording's edges), so
                # within the clip file itself the call spans roughly
                # [padding, padding + (end_time - start_time)]. Passing this lets
                # enhance_audio derive a frequency band from the call's own spectral
                # content instead of a fixed range for every species.
                clip_duration = processor.get_audio_duration(clip_for_enhance)
                call_len = max(0.0, det.end_time - det.start_time)
                call_start_in_clip = min(settings.clip_padding_seconds, max(0.0, clip_duration - call_len))
                call_end_in_clip = min(clip_duration, call_start_in_clip + call_len)

                generated = processor.enhance_audio(
                    clip_for_enhance, settings.enhanced_dir, f"{det.id}_{DSP_VERSION}",
                    call_start=call_start_in_clip, call_end=call_end_in_clip,
                )
        finally:
            if tmp_decoded_wav and os.path.exists(tmp_decoded_wav):
                os.unlink(tmp_decoded_wav)
        return FileResponse(
            generated, media_type="audio/wav",
            filename=f"enhanced_clip_{det.common_name.replace(' ', '_')}_{det.id[:8]}.wav",
            headers={"Cache-Control": "public, max-age=2592000, immutable"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audio enhancement failed: {e}")





@router.get("/{recording_id}/clip/{detection_id}/rumble-removed")
def get_clip_rumble_removed(recording_id: str, detection_id: str, nr: bool = False, db: Session = Depends(get_db)):
    """
    Rumble-removed version of a single detection's clip — mirrors
    /audio/rumble-removed above (plain species-aware high-pass, no
    bandpass, no noise-reduction boost — see enhance_audio()'s own
    docstring for the bug that fixed), scoped to just the short clip
    around this detection, the same way /clip/{detection_id}/enhanced
    scopes the classical Enhanced pipeline.

    Added directly in response to "rumble removal doesn't seem to do
    anything" — this endpoint never existed at all before now, so
    anyone checking rumble removal via an individual clip (rather than
    the full-recording player) had no way to hear it, full stop, not a
    bug in the filter itself. Bird-only, same as the full-recording
    endpoint (bats have no equivalent rumble concept — see that
    endpoint's own 404 for bat recordings).

    Generated from the (already-extracted) raw clip on first request
    and cached on disk.
    """
    det = db.query(Detection).filter(
        Detection.id == detection_id,
        Detection.recording_id == recording_id,
    ).first()
    if not det:
        raise HTTPException(status_code=404, detail="Detection not found")
    if det.common_name == "Bat":
        raise HTTPException(status_code=404, detail="Rumble removal is not available for bat detections")

    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")

    if not det.clip_path or not os.path.exists(det.clip_path):
        try:
            clip_path = processor.extract_clip(
                rec.wav_path, settings.clips_dir, det.id,
                det.start_time, det.end_time, padding=settings.clip_padding_seconds,
                is_bat=rec.is_bat,
            )
            det.clip_path = clip_path
            db.commit()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Clip extraction failed: {e}")

    # nr=true: noise reduction too (the app's single "Enhanced" setting).
    tag = "rumbleremoved_nr" if nr else "rumbleremoved"
    cache_path = os.path.join(settings.enhanced_dir, f"{det.id}_{tag}_{DSP_VERSION}_enhanced.wav")
    if os.path.exists(cache_path):
        return FileResponse(
            cache_path, media_type="audio/wav",
            filename=f"rumble_removed_clip_{det.common_name.replace(' ', '_')}_{det.id[:8]}.wav",
            headers={"Cache-Control": "public, max-age=2592000, immutable"},
        )

    try:
        clip_for_enhance = det.clip_path
        tmp_decoded_wav = None
        if det.clip_path.lower().endswith(".mp3"):
            tmp_decoded_wav = os.path.join(settings.enhanced_dir, f"{det.id}_srcdecode_rumble_tmp.wav")
            decode_result = subprocess.run(
                ["ffmpeg", "-y", "-i", det.clip_path, tmp_decoded_wav],
                capture_output=True, timeout=30,
            )
            if decode_result.returncode != 0 or not os.path.exists(tmp_decoded_wav):
                raise RuntimeError(
                    f"Could not decode clip for rumble removal: "
                    f"{decode_result.stderr.decode(errors='replace')[-300:]}"
                )
            clip_for_enhance = tmp_decoded_wav

        try:
            low_hz = recommended_high_pass_hz([det.common_name])
            generated = processor.enhance_audio(
                clip_for_enhance, settings.enhanced_dir, f"{det.id}_{tag}_{DSP_VERSION}",
                low_hz=low_hz, apply_noise_reduction=nr,
            )
        finally:
            if tmp_decoded_wav and os.path.exists(tmp_decoded_wav):
                os.unlink(tmp_decoded_wav)
        return FileResponse(
            generated, media_type="audio/wav",
            filename=f"rumble_removed_clip_{det.common_name.replace(' ', '_')}_{det.id[:8]}.wav",
            headers={"Cache-Control": "public, max-age=2592000, immutable"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rumble removal failed: {e}")


@router.get("/{recording_id}/clip/{detection_id}/ai-enhanced")
def get_clip_ai_enhanced(recording_id: str, detection_id: str, db: Session = Depends(get_db)):
    """
    AI Enhance (neural-network denoised) version of a single detection's
    clip — the highest-value target for this feature, since "does this
    specific call sound clean" is what a person is actually judging when
    they listen to one clip. See /audio/ai-enhanced above and
    services/ai_enhance.py for the shared implementation and its real
    16kHz-bandwidth caveat. Bird-only, same as the full-recording endpoint.

    Generated from the (already-extracted) raw clip on first request and
    cached on disk.
    """
    app_s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if not app_s or not app_s.ai_enhance_enabled:
        raise HTTPException(status_code=400, detail="AI Enhance is not enabled in Settings")

    det = db.query(Detection).filter(
        Detection.id == detection_id,
        Detection.recording_id == recording_id,
    ).first()
    if not det:
        raise HTTPException(status_code=404, detail="Detection not found")
    if det.common_name == "Bat":
        raise HTTPException(status_code=404, detail="AI Enhance is not available for bat detections")

    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")

    if not det.clip_path or not os.path.exists(det.clip_path):
        try:
            clip_path = processor.extract_clip(
                rec.wav_path, settings.clips_dir, det.id,
                det.start_time, det.end_time, padding=settings.clip_padding_seconds,
                is_bat=rec.is_bat,
            )
            det.clip_path = clip_path
            db.commit()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Clip extraction failed: {e}")

    cache_path = os.path.join(settings.enhanced_dir, f"{det.id}_{ai_enhance.AI_ENHANCE_VERSION}_aienhanced.wav")
    if os.path.exists(cache_path):
        return FileResponse(
            cache_path, media_type="audio/wav",
            filename=f"ai_enhanced_clip_{det.common_name.replace(' ', '_')}_{det.id[:8]}.wav",
            headers={"Cache-Control": "public, max-age=2592000, immutable"},
        )

    if not ai_enhance.is_available():
        raise HTTPException(
            status_code=400,
            detail="AI Enhance is enabled but not usable on this server — "
                   "torch/torchaudio isn't installed or the model failed to "
                   "load, check server logs (see requirements.txt)",
        )

    try:
        # Same MP3-decode-first step as /clip/{detection_id}/enhanced —
        # sf.read() (used inside ai_enhance.enhance_wav) is libsndfile-
        # backed and can't read MP3 directly. FLAC/WAV pass through as-is.
        clip_for_enhance = det.clip_path
        tmp_decoded_wav = None
        if det.clip_path.lower().endswith(".mp3"):
            tmp_decoded_wav = os.path.join(settings.enhanced_dir, f"{det.id}_srcdecode_ai_tmp.wav")
            decode_result = subprocess.run(
                ["ffmpeg", "-y", "-i", det.clip_path, tmp_decoded_wav],
                capture_output=True, timeout=30,
            )
            if decode_result.returncode != 0 or not os.path.exists(tmp_decoded_wav):
                raise RuntimeError(
                    f"Could not decode clip for AI Enhance: "
                    f"{decode_result.stderr.decode(errors='replace')[-300:]}"
                )
            clip_for_enhance = tmp_decoded_wav

        try:
            dry = app_s.ai_enhance_dry if app_s.ai_enhance_dry is not None else 0.1
            low_hz = recommended_high_pass_hz([det.common_name])
            generated = ai_enhance.enhance_wav(
                clip_for_enhance, settings.enhanced_dir, f"{det.id}_{ai_enhance.AI_ENHANCE_VERSION}",
                dry=dry, low_hz=low_hz,
            )
        finally:
            if tmp_decoded_wav and os.path.exists(tmp_decoded_wav):
                os.unlink(tmp_decoded_wav)
        return FileResponse(
            generated, media_type="audio/wav",
            filename=f"ai_enhanced_clip_{det.common_name.replace(' ', '_')}_{det.id[:8]}.wav",
            headers={"Cache-Control": "public, max-age=2592000, immutable"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Enhance failed: {e}")





# ── Recording Comments ────────────────────────────────────────────────────────

def _comment_out(c) -> dict:
    return {
        "id": c.id,
        "author": c.author,
        "body": c.body,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@router.get("/{recording_id}/comments")
def get_recording_comments(recording_id: str, db: Session = Depends(get_db), user=Depends(_current_user)):
    """Get all comments for a recording, newest first."""
    comments = (
        db.query(Comment)
        .filter(Comment.recording_id == recording_id, Comment.deleted_at.is_(None))
        .order_by(Comment.created_at.desc())
        .all()
    )
    hidden = _mod.blocked_authors(db, user)
    from ..services.author_photos import with_author_photos
    return with_author_photos(db, [_comment_out(c) for c in comments if c.author not in hidden])


@router.post("/{recording_id}/comments")
def post_recording_comment(recording_id: str, body: dict, db: Session = Depends(get_db), user=Depends(_current_user)):
    """Post a comment on a recording."""
    text = (body.get("body") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Comment body required")
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    c = Comment(
        recording_id=recording_id,
        author=_mod.author_for(user, body),
        body=text,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    from ..services.author_photos import with_author_photos
    return with_author_photos(db, [_comment_out(c)])[0]


@router.delete("/{recording_id}/comments/{comment_id}")
def delete_recording_comment(recording_id: str, comment_id: str, db: Session = Depends(get_db), user=Depends(_current_user)):
    """Soft-delete a comment."""
    from datetime import datetime as _dt
    c = db.query(Comment).filter(
        Comment.id == comment_id, Comment.recording_id == recording_id
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Comment not found")
    if not _mod.may_change(c, user):
        raise HTTPException(status_code=403, detail="Only the author or an admin can change this note")
    c.deleted_at = _dt.utcnow()
    db.commit()
    return {"ok": True}


@router.put("/{recording_id}/comments/{comment_id}")
def update_recording_comment(recording_id: str, comment_id: str, body: dict, db: Session = Depends(get_db), user=Depends(_current_user)):
    """Edit a comment body."""
    from datetime import datetime as _dt
    c = db.query(Comment).filter(
        Comment.id == comment_id, Comment.recording_id == recording_id,
        Comment.deleted_at.is_(None)
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Comment not found")
    if not _mod.may_change(c, user):
        raise HTTPException(status_code=403, detail="Only the author or an admin can change this note")
    new_body = (body.get("body") or "").strip()
    if not new_body:
        raise HTTPException(status_code=400, detail="Body cannot be empty")
    c.body = new_body
    c.updated_at = _dt.utcnow()
    db.commit()
    from ..services.author_photos import with_author_photos
    return with_author_photos(db, [_comment_out(c)])[0]


# ── Edit Recording ────────────────────────────────────────────────────────────

class RecordingPatch(BaseModel):
    label: Optional[str] = None        # User-supplied label / display name
    notes: Optional[str] = None        # Free-text notes
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # When it was recorded (ISO 8601; without an offset, server timezone).
    recorded_at: Optional[str] = None
    is_saved: Optional[bool] = None    # keep out of automatic cleanup


def _parse_hhmm(v: str) -> int:
    try:
        h, m = (int(x) for x in v.split(":"))
        if 0 <= h <= 24 and 0 <= m < 60 and h * 60 + m <= 1440:
            return h * 60 + m
    except (ValueError, AttributeError):
        pass
    raise HTTPException(status_code=422, detail="Times of day must be HH:MM")


def _filter_time_of_day(q, db: Session, time_from: str, time_to: str):
    """Recordings made between two local times of day (site time zone, DST
    included). trigger_timestamp is naive UTC; the local minute of the day is
    UTC minutes plus the zone's offset, which changes at each DST switch, so
    the offset comes from a CASE over the switch instants in the years the
    recordings span."""
    from datetime import datetime as _dt, timedelta as _td
    from zoneinfo import ZoneInfo
    from sqlalchemy import case, cast, func, Integer
    a, b = _parse_hhmm(time_from), _parse_hhmm(time_to)
    if a == b or (a == 0 and b == 1440):
        return q
    try:
        tz = ZoneInfo(_server_tz(db))
    except Exception:
        tz = ZoneInfo("UTC")
    lo, hi = db.query(func.min(Recording.trigger_timestamp), func.max(Recording.trigger_timestamp)).one()
    lo = (lo or _dt.utcnow()) - _td(days=1)
    hi = (hi or _dt.utcnow()) + _td(days=1)

    def off(t):   # minutes east of UTC at naive-UTC instant t
        return int(t.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz).utcoffset().total_seconds() // 60)

    segments = []           # (start, offset) in time order
    t, cur = lo, off(lo)
    segments.append((lo, cur))
    while t < hi:
        nxt = t + _td(days=1)
        if off(nxt) != cur:
            a_, b_ = t, nxt
            while (b_ - a_) > _td(minutes=1):     # bisect to the switch minute
                mid = a_ + (b_ - a_) / 2
                if off(mid) == cur:
                    a_ = mid
                else:
                    b_ = mid
            cur = off(b_)
            segments.append((b_, cur))
        t = nxt
    ts = Recording.trigger_timestamp
    if len(segments) == 1:
        offset = segments[0][1]
    else:
        offset = case(*[(ts >= s0, o) for s0, o in reversed(segments[1:])], else_=segments[0][1])
    utc_min = cast(func.strftime("%H", ts), Integer) * 60 + cast(func.strftime("%M", ts), Integer)
    local = (utc_min + offset + 1440) % 1440
    if a < b:
        return q.filter(local >= a, local < b)
    return q.filter((local >= a) | (local < b))      # wraps midnight, e.g. 21:00-04:00


def _server_tz(db: Session) -> str:
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    return (getattr(s, "timezone", None) or "America/New_York") if s else "America/New_York"


@router.patch("/{recording_id}", response_model=RecordingOut)
def edit_recording(
    recording_id: str,
    body: RecordingPatch,
    db: Session = Depends(get_db),
):
    """Edit user-supplied metadata on a recording (label, notes, GPS, and
    when it was recorded)."""
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    fields = body.model_dump(exclude_none=True)
    recorded_at = fields.pop("recorded_at", None)
    if "is_saved" in fields:
        logger.info("Recording %s %s", recording_id, "saved" if fields["is_saved"] else "unsaved")
    if recorded_at is not None:
        try:
            ts = parse_recorded_at(recorded_at, _server_tz(db))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if ts is None:
            raise HTTPException(status_code=400, detail="Unreadable date and time")
        logger.info("Recording %s: time changed %s -> %s UTC", recording_id, rec.trigger_timestamp, ts)
        rec.trigger_timestamp = ts
    for field, value in fields.items():
        setattr(rec, field, value)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    if recorded_at is not None:
        from ..cache import invalidate_detection_caches
        invalidate_detection_caches()
    return recording_to_out(rec, db)


@router.delete("/{recording_id}", status_code=204)
def delete_recording(
    recording_id: str,
    delete_files: bool = Query(False, description="Also delete audio/spectrogram files from disk"),
    hard_delete: bool = Query(False, description="Permanently remove DB row (default: soft-delete)"),
    db: Session = Depends(get_db),
):
    """
    Soft-delete a recording (hidden from counts and lists but kept in DB).
    Pass hard_delete=true to permanently remove the DB row.
    Pass delete_files=true to also remove audio/spectrogram/clip files.
    """
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")

    # Files go after the commit, on a thread: scanning the spectrograms
    # folder takes seconds on a large server. Enhanced caches are derived
    # and regenerate on demand, so they go on every delete (soft or hard).
    from ..services.file_cleanup import collect_files, remove_files_in_background
    _job = collect_files([rec])
    if not delete_files:
        _job = {"paths": [], "rec_ids": [], "owner_ids": _job["owner_ids"]}

    if hard_delete:
        db.delete(rec)
    else:
        from datetime import datetime as _dt
        rec.deleted_at = _dt.utcnow()
    db.commit()
    remove_files_in_background(_job, f"recording {recording_id}")



@router.post("/{recording_id}/restore", status_code=200)
def restore_recording(recording_id: str, db: Session = Depends(get_db)):
    """Restore a soft-deleted recording (clears deleted_at)."""
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    rec.deleted_at = None
    db.commit()
    return {"id": recording_id, "status": "restored"}


class BulkActionRequest(BaseModel):
    ids: List[str]


@router.post("/bulk-archive", status_code=200)
def bulk_archive(req: BulkActionRequest, db: Session = Depends(get_db)):
    """Archive audio from multiple recordings in one call.

    Previously issued one SELECT per id (plus a lazy-loaded query per
    recording's .detections access) — for a bulk selection this meant
    2N+ round trips to the database. Now a single bulk query fetches every
    requested recording (with detections eager-loaded via selectinload) up
    front, and the loop below just does an in-memory dict lookup per id.
    Same skip logic, same side effects, same returned counts — only the
    query pattern changed.
    """
    archived = 0
    skipped  = 0
    recs = (
        db.query(Recording)
        .options(selectinload(Recording.detections))
        .filter(Recording.id.in_(req.ids))
        .all()
    )
    by_id = {r.id: r for r in recs}
    for rid in req.ids:
        rec = by_id.get(rid)
        if not rec or rec.archived_at:
            skipped += 1
            continue
        for fpath in [rec.wav_path]:
            if fpath and os.path.exists(fpath):
                try:
                    os.unlink(fpath)
                except OSError as e:
                    logger.warning("Bulk archive: could not delete %s: %s", fpath, e)
        for det in rec.detections:
            if det.clip_path and os.path.exists(det.clip_path):
                try:
                    os.unlink(det.clip_path)
                except OSError:
                    pass
                det.clip_path = None
        _sweep_enhanced(rec)
        rec.wav_path = ""
        rec.archived_at = datetime.utcnow()
        archived += 1
    db.commit()
    return {"archived": archived, "skipped": skipped,
            "message": f"Archived {archived} recording(s), skipped {skipped} already-archived."}


@router.post("/bulk-delete", status_code=200)
def bulk_delete(req: BulkActionRequest, db: Session = Depends(get_db)):
    """Soft-delete multiple recordings in one call.

    Same N+1 fix as bulk_archive above — one bulk SELECT with eager-loaded
    detections instead of one query per id plus a lazy-load per recording.
    """
    deleted = 0
    skipped = 0
    now = datetime.utcnow()
    recs = (
        db.query(Recording)
        .options(selectinload(Recording.detections))
        .filter(Recording.id.in_(req.ids))
        .all()
    )
    from ..services.file_cleanup import collect_files, merge_jobs, remove_files_in_background
    _jobs = []
    by_id = {r.id: r for r in recs}
    for rid in req.ids:
        rec = by_id.get(rid)
        if not rec or rec.deleted_at:
            skipped += 1
            continue
        _jobs.append(collect_files([rec]))
        rec.deleted_at = now
        deleted += 1
    db.commit()
    # Files after the commit, on a thread (see delete_recording).
    remove_files_in_background(merge_jobs(_jobs), f"{deleted} recording(s)")
    return {"deleted": deleted, "skipped": skipped,
            "message": f"Deleted {deleted} recording(s), skipped {skipped}."}


@router.post("/{recording_id}/archive", status_code=200)
def archive_recording(recording_id: str, db: Session = Depends(get_db)):
    """
    Archive a recording: permanently delete its audio file (and any
    per-detection clip files) to free disk space, while keeping
    everything else fully intact — the recording stays in the main list,
    its spectrogram and every Detection row are untouched, and it
    continues to count toward species/detection statistics exactly as
    before. This is deliberately NOT the same as delete_recording's
    soft-delete (deleted_at), which hides a recording from counts
    entirely — see Recording.archived_at's model docstring for the full
    reasoning. Reversible only in the sense that archived_at can be
    cleared again (see unarchive_recording below); the audio file itself
    is gone for good once this runs, same as a real hard delete of audio.

    Once archived, playback, WAV download, and iNaturalist submission are
    all correctly disabled — has_audio becomes False automatically since
    it's computed from wav_path (see recording_to_out), and
    submit_to_inaturalist explicitly checks archived_at directly below.
    """
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    if rec.archived_at:
        return {"id": recording_id, "status": "already_archived"}

    deleted_files = []
    for fpath in [rec.wav_path]:
        if fpath and os.path.exists(fpath):
            try:
                os.unlink(fpath)
                deleted_files.append(fpath)
            except OSError as e:
                logger.warning("Archive: could not delete audio file %s for %s: %s", fpath, recording_id, e)
    for det in rec.detections:
        if det.clip_path and os.path.exists(det.clip_path):
            try:
                os.unlink(det.clip_path)
                deleted_files.append(det.clip_path)
            except OSError as e:
                logger.warning("Archive: could not delete clip %s for detection %s: %s", det.clip_path, det.id, e)

    n_enh = _sweep_enhanced(rec)
    if n_enh:
        deleted_files.extend(["enhanced"] * n_enh)

    # wav_path is non-nullable on the model (see Recording.wav_path) and
    # is what has_audio/recording_to_out actually check — clearing it to
    # an empty string (matching the existing convention for "no audio"
    # rows, e.g. Haikubox-imported recordings) is what correctly turns
    # off playback/download/submission everywhere, not just deleting the
    # file from disk while leaving the DB pointing at a path that no
    # longer exists.
    rec.wav_path = ""
    for det in rec.detections:
        det.clip_path = None
    rec.archived_at = datetime.utcnow()
    db.commit()
    logger.info("Archived recording %s — removed %d file(s)", recording_id, len(deleted_files))
    return {"id": recording_id, "status": "archived", "files_removed": len(deleted_files)}


@router.post("/{recording_id}/unarchive", status_code=200)
def unarchive_recording(recording_id: str, db: Session = Depends(get_db)):
    """
    Clear archived_at. Does NOT restore the audio file — it was
    permanently deleted by archive_recording above and cannot be
    recovered. This exists so an accidentally-archived recording's
    archived status (and any future archive-specific UI treatment) can
    be undone, not so audio comes back.
    """
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    if not rec.archived_at:
        return {"id": recording_id, "status": "not_archived"}
    rec.archived_at = None
    db.commit()
    return {"id": recording_id, "status": "unarchived", "note": "Archive status cleared — the deleted audio file cannot be restored."}


# ── Manual Web Upload Endpoint ────────────────────────────────────────────────

@router.post("/upload-manual", status_code=status.HTTP_201_CREATED)
async def upload_recording_manual(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="WAV or MP3 audio file"),
    label: Optional[str] = Form(None, description="Optional user-supplied label/note"),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    recorded_at: Optional[str] = Form(None, description="When the recording was made (ISO 8601; without an offset it's read in the server's timezone). Default: from the file name if it carries one, else now."),
    is_bat: bool = Form(False, description="True if this is a bat-echolocation recording rather than a bird recording — routes to the bat pipeline (spectrogram + optional species classification) instead of BirdNET"),
    db: Session = Depends(get_db),
):
    """
    Manual upload from the WebGUI — no API key required.
    Accepts WAV or MP3. Bird recordings (is_bat=False, the default) run
    BirdNET server-side to generate detections, then process normally
    (spectrogram, clips, enrichment). Bat recordings (is_bat=True) skip
    BirdNET entirely and instead get the one-Detection "Bat" placeholder +
    bat-specific spectrogram/clip/species-classification pipeline — the
    exact same pipeline device-uploaded bat clips use (see
    api/bat_activity.py and process_recording_bg's `if rec.is_bat` branch),
    reused as-is rather than duplicated here.
    """
    # Validate file type
    fname = file.filename or "upload.wav"
    ext = os.path.splitext(fname)[1].lower()
    if ext not in (".wav", ".mp3", ".flac", ".ogg", ".m4a"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported: WAV, MP3, FLAC, OGG, M4A"
        )

    # Save uploaded file
    rec_dir = Path(settings.recordings_dir)
    rec_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"manual_{uuid.uuid4().hex[:8]}_{Path(fname).name}"
    file_path = rec_dir / safe_name

    try:
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    file_size_mb = file_path.stat().st_size / (1024 * 1024)
    if file_size_mb > settings.max_upload_mb:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail=f"File too large: {file_size_mb:.1f} MB")

    # Convert non-WAV to WAV via ffmpeg if needed.
    # Bat recordings are never resampled here even if this path runs —
    # ffmpeg's -ar 48000 below would destroy the ultrasonic content a bat
    # file needs, same reasoning as why storage_manager.py's Opus
    # compression is skipped for bat clips. In practice this only matters
    # for non-WAV bat uploads (rare — ultrasonic mics normally produce WAV
    # directly), but skip the forced resample for is_bat regardless.
    wav_path = file_path
    if ext != ".wav":
        if is_bat:
            logger.info("Manual bat upload is non-WAV (%s) — skipping the bird-path ffmpeg resample "
                        "to avoid destroying ultrasonic content; using the original file as-is.", ext)
        else:
            wav_converted = rec_dir / (safe_name.rsplit(".", 1)[0] + ".wav")
            try:
                import subprocess
                from starlette.concurrency import run_in_threadpool
                result = await run_in_threadpool(
                    subprocess.run,
                    ["ffmpeg", "-y", "-i", str(file_path), "-ar", "48000",
                     "-ac", "2", "-sample_fmt", "s16", str(wav_converted)],
                    capture_output=True, timeout=120,
                )
                if result.returncode == 0:
                    file_path.unlink(missing_ok=True)
                    wav_path = wav_converted
                    safe_name = wav_converted.name
                else:
                    logger.warning("ffmpeg conversion failed, keeping original: %s",
                                   result.stderr.decode()[:200])
                    wav_path = file_path
            except Exception as e:
                logger.warning("ffmpeg unavailable, keeping original: %s", e)
                wav_path = file_path

    # Get audio duration + real sample rate — read directly from the file
    # rather than asking the user to supply it (they'd have to already
    # know it via some other tool anyway; the file itself is authoritative).
    try:
        import soundfile as sf
        info = sf.info(str(wav_path))
        duration = info.duration
        sample_rate = info.samplerate
        channels = info.channels
    except Exception:
        duration = 0.0
        sample_rate = 48000
        channels = 1

    # Bat calls run ~15-120kHz — capturing them at all requires a genuine
    # ultrasonic mic sampling well above the Nyquist limit for that range.
    # A standard bird-mic recording (44.1/48kHz, sometimes 96kHz) physically
    # cannot contain bat echolocation content — same physical constraint
    # documented in chirp-device/config.yaml for the device-side detector's
    # own min_sample_rate check. Reject clearly rather than silently running
    # species classification on audio that can't possibly contain the thing
    # it's being asked to classify.
    if is_bat and sample_rate < 96000:
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=(
                f"This file is {sample_rate}Hz — bat echolocation calls (~15-120kHz) require a "
                f"genuine ultrasonic microphone recording at well above standard rates. A normal "
                f"bird-mic recording (44.1/48kHz) cannot physically contain bat call content. "
                f"If this is actually a bird recording, re-upload without marking it as a bat recording."
            ),
        )

    # When it was recorded: the form's value, else the file name (HaikuBox,
    # AudioMoth, Song Meter and Chirp names carry local time), else now.
    # Drives the date shown and BirdNET's week-of-year species list.
    _tz = _server_tz(db)
    try:
        trigger_ts = parse_recorded_at(recorded_at, _tz) or time_from_filename(fname, _tz) or datetime.utcnow()
    except ValueError as e:
        file_path.unlink(missing_ok=True)
        if wav_path != file_path:
            Path(wav_path).unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(e))

    # Create Recording row — detections will be filled by background task
    rec_id = str(uuid.uuid4())
    recording = Recording(
        id=rec_id,
        filename=safe_name,
        wav_path=str(wav_path),
        trigger_timestamp=trigger_ts,
        duration_seconds=duration,
        sample_rate=sample_rate,
        channels=channels,
        pre_roll_seconds=0.0,
        device_count=1,
        processing_status="pending",
        latitude=latitude,
        longitude=longitude,
        is_bat=is_bat,
    )
    db.add(recording)

    if is_bat:
        # Same placeholder pattern as api/bat_activity.py's device upload
        # endpoint: one Detection spanning the full recording, no graded
        # confidence (presence/absence, not a species call) since there's
        # no pulse-train stats available here the way the device's
        # real-time BatDetector produces them — bat_metadata stays empty
        # for manually uploaded files rather than fabricating fake values.
        det = Detection(
            id=str(uuid.uuid4()),
            recording_id=rec_id,
            common_name="Bat",
            scientific_name="Chiroptera",
            label="Bat",
            confidence=1.0,
            start_time=0.0,
            end_time=duration,
            source="server",
        )
        db.add(det)

    db.commit()

    from ..cache import invalidate_detection_caches
    invalidate_detection_caches()

    logger.info("Manual upload: %s (%.1fs, %.1f MB, is_bat=%s)", safe_name, duration, file_size_mb, is_bat)

    # Bat recordings reuse process_recording_bg's existing `if rec.is_bat`
    # branch (spectrogram + clip + optional species classification) rather
    # than the bird-specific _process_manual_upload background task.
    if is_bat:
        background_tasks.add_task(process_recording_bg, rec_id)
    else:
        # Run BirdNET + full processing pipeline in background
        background_tasks.add_task(_process_manual_upload, rec_id, label)

    return {
        "id": rec_id,
        "status": "processing",
        "filename": safe_name,
        "duration_seconds": round(duration, 2),
        "is_bat": is_bat,
        "message": ("File received. Bat pipeline running — refresh in a few seconds."
                    if is_bat else
                    "File received. BirdNET analysis running — refresh in a few seconds."),
    }


def _process_manual_upload(rec_id: str, label: Optional[str] = None, use_ai_enhance: bool = False,
                           prior: Optional[list] = None, min_conf_override: Optional[float] = None,
                           run_id: Optional[str] = None):
    """
    Background task for manual uploads:
      1. Run BirdNET on the full file (sliding 3s windows)
      2. Store detections
      3. Generate spectrogram + clips
      4. Enrich bird profiles

    use_ai_enhance: analyze the AI-Enhanced version of the audio instead of
    the original — requested directly, after measuring that AI Enhance's
    neural denoising can genuinely improve in-band SNR on a noisy
    recording (confirmed on a real example: a 3.8dB in-band SNR climbing
    to 13.5dB), and realizing that improvement had never once reached
    BirdNET itself. Both Rumble Removed and AI Enhance have only ever
    been playback-only — every "Enhanced" toggle a person ever clicks
    changes what they hear, never what gets analyzed or what confidence
    score gets stored, since BirdNET always ran on rec.wav_path regardless.
    This is the one re-analysis path that actually closes that gap: a
    recording that came back empty or low-confidence because it's
    genuinely noisy gets a real second chance with denoised input, not
    just a different confidence threshold on the same noisy original.
    """
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        rec = db.query(Recording).filter(Recording.id == rec_id).first()
        if not rec:
            return

        rec.processing_status = "processing"
        db.commit()
        # For the re-analysis change log: what this recording showed before.
        _before = [(d["common_name"], "server", d["confidence"], d["start_time"]) for d in (prior or [])]
        _before += [(d.common_name, d.source, float(d.confidence or 0), float(d.start_time or 0))
                    for d in rec.detections if d.source == "device"]
        _diag: dict = {}

        # Same SNR quality signal as process_recording_bg's own copy of
        # this — manual uploads need it computed here too, not just
        # device uploads, since this is meant to cover every recording
        # regardless of source.
        try:
            rec.snr_db = compute_snr_db(rec.wav_path)
            db.commit()
        except Exception as e:
            logger.warning("compute_snr_db failed for %s: %s", rec_id, e)

        # ── Step 0: AI-Enhance the audio first, if requested ─────────────────
        # Deliberately BEFORE normalization, not instead of it — even though
        # enhance_wav's own output is already resampled back to the file's
        # original sample rate and written as 16-bit PCM (so it usually
        # already satisfies birdnetlib's exact format requirement), the
        # normalization step below is still the one safety net that holds
        # regardless of what the ORIGINAL recording's own sample rate was —
        # running it unconditionally here, same as on the plain original,
        # costs nothing on the already-compliant case and protects the
        # non-48kHz one. A failure in this AI Enhance step falls back to the
        # original file with a clear log line rather than silently losing
        # the recording's whole re-analysis attempt — AI Enhance is
        # inherently best-effort (a 429/network hiccup on first model
        # download, a corrupt cached weights file, an OOM on a particularly
        # long recording) and none of those should turn into a recording
        # stuck in "processing" forever.
        analysis_source = rec.wav_path
        if use_ai_enhance:
            try:
                from ..services.ai_enhance import enhance_wav
                # Species aren't known yet, so use the low-caller cutoff: the
                # 500 Hz default would strip owl hoots before BirdNET hears them.
                from ..services.audio_processor import LOW_FREQUENCY_HIGH_PASS_HZ
                enhanced_path = enhance_wav(rec.wav_path, settings.enhanced_dir,
                                            f"{rec_id}_reanalyze_{ai_enhance.AI_ENHANCE_VERSION}",
                                            low_hz=LOW_FREQUENCY_HIGH_PASS_HZ)
                analysis_source = enhanced_path
                logger.info("Re-analyzing %s using AI-Enhanced audio: %s", rec_id, enhanced_path)
            except Exception as e:
                logger.warning(
                    "AI Enhance failed during reanalysis of %s, falling back to original audio: %s",
                    rec_id, e,
                )

        # ── Step 1: Normalize audio to birdnetlib's required format ─────────
        # birdnetlib expects: 48 kHz, mono, 16-bit signed PCM WAV.
        # Any other encoding (24-bit, 32-bit float, stereo, wrong sample rate,
        # RF64, A-law, u-law) causes librosa's "Generic audio read error".
        # We always transcode through ffmpeg first so BirdNET gets clean input.
        analysis_wav = analysis_source   # will be overwritten with normalized path
        normalized_path = None
        try:
            import subprocess, os as _os
            # Use a temp file with a fixed .wav extension regardless of input format.
            # rec.wav_path may be .opus/.flac after compression — the old
            # .replace(".wav", "_birdnet_norm.wav") silently produced wrong paths.
            _stem = _os.path.splitext(analysis_source)[0]
            normalized_path = _stem + "_birdnet_norm.wav"
            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", analysis_source,
                    "-ar", "48000",       # birdnetlib requires 48 kHz
                    "-ac", "1",           # mono
                    "-sample_fmt", "s16", # 16-bit signed PCM
                    "-f", "wav",
                    normalized_path,
                ],
                capture_output=True,
                timeout=120,
            )
            if result.returncode == 0:
                analysis_wav = normalized_path
                logger.info("Audio normalized for BirdNET: %s", normalized_path)
            else:
                logger.warning(
                    "ffmpeg normalization failed (will try original): %s",
                    result.stderr.decode()[-300:],
                )
        except Exception as e:
            logger.warning("ffmpeg normalization error (will try original): %s", e)

        # ── Step 2: Run BirdNET on the normalized file ────────────────────────
        detections_raw = []
        analysis_error = None
        used_bn3 = False
        try:
            from datetime import date as dt_date

            # Get optional location from recording or app settings
            # Single AppSettings fetch for all BirdNET params + location fallback
            from ..models import AppSettings
            app_s_bn = db.query(AppSettings).filter(AppSettings.id == 1).first()

            rec_lat = rec.latitude or (app_s_bn.latitude  if app_s_bn else None)
            rec_lon = rec.longitude or (app_s_bn.longitude if app_s_bn else None)

            birdnet_min_conf   = float(app_s_bn.birdnet_min_confidence or 0.05)  if app_s_bn else 0.05
            if min_conf_override is not None:
                birdnet_min_conf = float(min_conf_override)
            birdnet_overlap    = float(app_s_bn.birdnet_overlap    or 2.5)        if app_s_bn else 2.5
            birdnet_sensitivity= float(app_s_bn.birdnet_sensitivity or 1.5)       if app_s_bn else 1.5

            logger.info("BirdNET analysis: min_conf=%.2f overlap=%.1f sensitivity=%.1f for %s",
                        birdnet_min_conf, birdnet_overlap, birdnet_sensitivity, rec_id)

            rec_when = rec.trigger_timestamp.date() if rec.trigger_timestamp else dt_date.today()
            raw = None
            if _bn3_main(app_s_bn):
                # BirdNET v3, the default model (Settings → Detection), as in
                # _run_server_birdnet. With AI Enhance, the original is scored
                # too and each species/window keeps its higher score.
                try:
                    from ..services import birdnet3
                    bn3_conf = float(min_conf_override) if min_conf_override is not None \
                        else float(getattr(app_s_bn, "exp_birdnet3_min_conf", None) or birdnet3.DEFAULT_MIN_CONF)
                    best = {}
                    for src in dict.fromkeys([analysis_source, rec.wav_path]):
                        for d in birdnet3.analyze(src, lat=rec_lat, lon=rec_lon, when=rec_when, min_conf=bn3_conf,
                                                  start_utc=rec.trigger_timestamp):
                            k = (d["label"], round(float(d["start_time"]), 1))
                            if k not in best or d["confidence"] > best[k]["confidence"]:
                                best[k] = d
                    raw = sorted(best.values(), key=lambda d: (d["start_time"], -d["confidence"]))
                    birdnet_min_conf = bn3_conf
                    used_bn3 = True
                    logger.info("BirdNET v3 (main) returned %d detections for %s", len(raw), rec_id)
                except Exception as e:
                    logger.warning("BirdNET v3 unavailable for %s (%s) — using BirdNET 2.4", rec_id, e)
                    raw = None
            if raw is None:
                raw = _run_birdnet_pass(
                    analysis_wav, lat=rec_lat, lon=rec_lon, when=rec_when,
                    min_conf=birdnet_min_conf, sensitivity=birdnet_sensitivity, overlap=birdnet_overlap,
                    # Earlier server results came from the original WAV; keep the
                    # ones compression or AI Enhance nudged just under threshold.
                    prior=prior if (use_ai_enhance or rec.wav_path.lower().endswith(_LOSSY_EXTS)) else None,
                    diag=_diag, **_bn_rules(app_s_bn))
                if analysis_source != rec.wav_path:
                    # AI Enhance can erase calls (a Tufted Titmouse went from 0.36
                    # to 0.07), so the enhanced pass only adds: the original audio
                    # is scored too and each species/window keeps its higher score.
                    raw = _merge_with_original_pass(
                        raw, rec.wav_path, _diag, lat=rec_lat, lon=rec_lon, when=rec_when,
                        min_conf=birdnet_min_conf, sensitivity=birdnet_sensitivity,
                        overlap=birdnet_overlap, rec_id=rec_id, rules=_bn_rules(app_s_bn))
                logger.info("BirdNET returned %d detections for %s", len(raw), rec_id)
                _store_near_misses(db, rec_id, _diag, raw)
                if _bn3_shadow(app_s_bn) and not rec.is_live_detect_clip:
                    _store_shadow(db, rec_id, rec.wav_path, rec_lat, rec_lon, rec_when, app_s_bn, rec.trigger_timestamp)
            _drop_superseded_device_detections(db, rec_id, raw, v3=used_bn3)

            for det in raw:
                common   = det.get("common_name", "Unknown")
                sci      = det.get("scientific_name", "")
                # birdnetlib label is already "Scientific name_Common name"
                # but build a stable label ourselves to match BirdProfile keys
                lbl = det.get("label") or f"{common}_{sci}"
                detections_raw.append({
                    "common_name": common,
                    "scientific_name": sci,
                    "label": lbl,
                    "confidence": float(det.get("confidence", 0)),
                    "start_time": float(det.get("start_time", 0)),
                    "end_time": float(det.get("end_time", 3)),
                })

            logger.info("BirdNET found %d detections (stored) for manual upload %s",
                        len(detections_raw), rec_id)

        except Exception as e:
            analysis_error = str(e)
            logger.error("BirdNET analysis failed for manual upload %s: %s", rec_id, e, exc_info=True)
        finally:
            # Remove temporary normalized file
            if normalized_path and normalized_path != rec.wav_path:
                try:
                    import os as _os
                    _os.unlink(normalized_path)
                except OSError:
                    pass

        # ── Step 3: Store detections ─────────────────────────────────────────
        for det_data in detections_raw:
            det = Detection(
                id=str(uuid.uuid4()),
                recording_id=rec_id,
                common_name=det_data["common_name"],
                scientific_name=det_data.get("scientific_name"),
                label=det_data["label"],
                confidence=det_data["confidence"],
                start_time=det_data["start_time"],
                end_time=det_data["end_time"],
                source="server",
            )
            db.add(det)
        db.commit()
        db.refresh(rec)

        from ..cache import invalidate_detection_caches
        invalidate_detection_caches()
        _changes = []
        if _before and not analysis_error:
            _changes = _log_reanalysis_changes(
                rec_id, _before,
                [{"common_name": d.common_name, "confidence": float(d.confidence or 0)} for d in rec.detections],
                _diag, birdnet_min_conf,
                float(getattr(app_s_bn, "min_confidence_display", 0.0) or 0.0) if app_s_bn else 0.0,
                _species_thresholds(app_s_bn), night_rules(app_s_bn))
        if run_id:
            from ..models import ReanalysisRun
            _run = db.query(ReanalysisRun).filter(ReanalysisRun.id == run_id).first()
            if _run:
                _run.changes = _changes
                _run.status = "error" if analysis_error else "done"
                _run.finished_at = datetime.utcnow()
                n = {k: sum(1 for c in _changes if c["change"] == k) for k in ("added", "removed", "hidden")}
                _run.summary = (f"BirdNET error: {analysis_error}"[:250] if analysis_error else
                                f"{n['added']} added, {n['removed']} removed, {n['hidden']} now hidden"
                                + (" (AI-Enhanced + original)" if use_ai_enhance else "")
                                + (" (BirdNET v3)" if used_bn3 else ""))
                db.commit()

        # ── Step 4: Spectrogram + clips ──────────────────────────────────────
        try:
            dets_as_dicts = [
                {"common_name": d.common_name, "confidence": d.confidence,
                 "start_time": d.start_time, "end_time": d.end_time}
                for d in rec.detections
            ]
            spec_path = processor.generate_spectrogram(
                rec.wav_path, settings.spectrograms_dir, rec_id,
                detections=dets_as_dicts or None,
                color_palette=getattr(app_s_bn, "detection_color_palette", None) or "vivid",
            )
            rec.spectrogram_path = spec_path
        except Exception as e:
            logger.warning("Spectrogram failed for manual upload %s: %s", rec_id, e)

        for det in rec.detections:
            try:
                clip_path = processor.extract_clip(
                    rec.wav_path, settings.clips_dir, det.id,
                    det.start_time, det.end_time,
                    padding=settings.clip_padding_seconds,
                )
                det.clip_path = clip_path
                db.add(det)
            except Exception as e:
                logger.debug("Clip extraction failed for %s: %s", det.id, e)

        if not detections_raw and analysis_error:
            rec.processing_error = f"BirdNET analysis error: {analysis_error}"
        elif not detections_raw:
            rec.processing_error = (
                "BirdNET found no bird calls in this recording. "
                "Check that the audio contains bird vocalizations, "
                "that the recording is not excessively noisy, "
                "and that sample rate is at least 22050 Hz."
            )
        rec.processing_status = "done"
        db.commit()

        # ── Auto-purge (Bird Buddy imports only) ─────────────────────────────
        # auto_purge_empty_recordings already applied to device uploads via
        # process_recording_bg's own copy of this logic, but Bird Buddy
        # imports go through this function instead (see bird_buddy_sync.py's
        # _import_media), which needs its own copy. Scoped to
        # rec.bird_buddy_media_id specifically — not a genuine manual
        # upload via the Upload button, which also runs through this same
        # function and shouldn't be silently deleted the way a passive,
        # high-volume import should. No device-confidence gating here
        # either, since Bird Buddy media has no such signal to begin with —
        # "server found zero" is the whole condition.
        try:
            if rec.bird_buddy_media_id and not rec.detections:
                from ..models import AppSettings as _APurge2
                _ps2 = db.query(_APurge2).filter(_APurge2.id == 1).first()
                if _ps2 and getattr(_ps2, "auto_purge_empty_recordings", False):
                    logger.info("Auto-purge: deleting Bird Buddy recording %s — 0 server detections", rec_id)
                    from ..services.file_cleanup import collect_files, remove_files
                    _job = collect_files([rec])
                    if normalized_path:
                        _job["paths"].append(normalized_path)
                    db.delete(rec)
                    db.commit()
                    remove_files(_job)   # after the commit: no lock held
                    return
        except Exception as _pe2:
            logger.warning("Bird Buddy auto-purge step failed for %s: %s", rec_id, _pe2)

        # ── Step 5: Enrich bird profiles ─────────────────────────────────────
        if settings.enrich_on_upload:
            labels = list({d.label for d in rec.detections})
            for lbl in labels:
                try:
                    from ..services.bird_enricher import BirdEnricher
                    enricher = BirdEnricher(db)
                    enricher.ensure_profile(lbl)
                except Exception as e:
                    logger.debug("Enrichment failed for %s: %s", lbl, e)

        # Broadcast
        try:
            import asyncio
            from ..main import manager
            top = rec.top_species or "Unknown"
            asyncio.run(manager.broadcast({
                "type": "new_recording",
                "data": {"id": rec_id, "species": top,
                         "confidence": rec.max_confidence, "source": "manual"}
            }))
        except Exception:
            pass

    except Exception as e:
        logger.error("Manual upload processing error %s: %s", rec_id, e)
        try:
            rec = db.query(Recording).filter(Recording.id == rec_id).first()
            if rec:
                rec.processing_status = "error"
                rec.processing_error = str(e)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()




@router.post("/storage/cleanup", status_code=200)
async def trigger_storage_cleanup(request: Request, db: Session = Depends(get_db)):
    """
    Manually trigger a storage cleanup pass (size + age enforcement + compression).
    Returns a summary of what was pruned. Safe to call at any time.
    """
    try:
        mgr = request.app.state.storage_manager
        summary = mgr.run_cleanup_now()
        return {"status": "ok", **summary}
    except AttributeError:
        return {"status": "storage_manager_not_initialized"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.post("/activity-log/purge", status_code=200)
async def trigger_activity_log_purge(request: Request):
    """
    Manually trigger an activity log purge pass (enforces activity_log_retention_days
    immediately rather than waiting for the next scheduled pass). Real fix for
    run_purge_now() on ActivityLogManager — already correctly implemented and
    explicitly documented as "safe to call from an API endpoint," but never
    actually wired to one. The scheduled background loop (see main.py) already
    runs this automatically on its own interval regardless, so this endpoint
    is a manual "run it now" convenience rather than a fix to any actual
    purging gap — the retention policy itself was always being enforced.
    """
    try:
        mgr = request.app.state.activity_log_manager
        summary = mgr.run_purge_now()
        return {"status": "ok", **summary}
    except AttributeError:
        return {"status": "activity_log_manager_not_initialized"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.get("/storage/status", status_code=200)
def storage_status(db: Session = Depends(get_db)):
    """
    Comprehensive storage usage report — every directory chirp-server writes
    to (recordings, spectrograms, clips, enhanced, bat_clips, media), not
    just recordings_dir, matching the same breakdown the diagnostics report
    shows. Also answers "why does file count not match recording count?"
    directly: soft-deleted recordings keep their files on disk until
    something actually unlinks them (auto-purge, if configured, or an
    explicit delete/cleanup action) — the accounting below shows exactly
    how many soft-deleted rows still have a file present, and how much
    space reclaiming them would free, without guessing.

    Top-level used_gb/limit_gb/limit_pct/compress_* fields are kept exactly
    as before for backward compatibility with the existing usage bar in
    Settings — they still describe recordings_dir specifically, which is
    what storage_max_dir_gb enforcement is measured against. Everything
    else is new, additive data under "directories"/"recordings_accounting"/
    "orphans".
    """
    from ..services.storage_manager import get_directory_size_gb, dir_stats, find_orphaned_files, fmt_bytes
    from ..models import AppSettings as _AS, Recording, Detection
    s = db.query(_AS).filter(_AS.id == 1).first()
    dir_gb = get_directory_size_gb(settings.recordings_dir)
    limit_gb = getattr(s, 'storage_max_dir_gb', 0.0) or 0.0
    compress_enabled = getattr(s, 'storage_compress_on_upload', True)
    compress_quality = getattr(s, 'storage_compress_quality', 'lossless')

    # ── Full multi-directory breakdown, matching the diagnostics report ──────
    dir_paths = {
        "recordings":   settings.recordings_dir,
        "spectrograms": settings.spectrograms_dir,
        "clips":        settings.clips_dir,
        "enhanced":     getattr(settings, "enhanced_dir", ""),
        "bat_clips":    getattr(settings, "bat_clips_dir", ""),
        "media":        getattr(settings, "media_dir", ""),
    }
    directories = {k: dir_stats(v) for k, v in dir_paths.items() if v}
    total_all_bytes = sum(d.get("size_bytes", 0) for d in directories.values())

    # ── Recordings DB accounting — the direct, real answer to "why does the
    #    file count not match my recording count?" ──────────────────────────
    all_recs = db.query(Recording.id, Recording.wav_path, Recording.deleted_at).all()
    db_rows_total = len(all_recs)
    db_rows_active = sum(1 for r in all_recs if r.deleted_at is None)
    db_rows_soft_deleted = db_rows_total - db_rows_active

    soft_deleted_with_file = 0
    soft_deleted_reclaimable_bytes = 0
    for r in all_recs:
        if r.deleted_at is not None and r.wav_path and os.path.exists(r.wav_path):
            soft_deleted_with_file += 1
            try:
                soft_deleted_reclaimable_bytes += os.path.getsize(r.wav_path)
            except OSError:
                pass

    # ── True orphans — files with NO matching DB row at all (any recording,
    #    active or soft-deleted). Covers leftovers from failed cleanups,
    #    interrupted compressions, or pre-migration artifacts. Read-only
    #    detection here; see /storage/purge-orphans to actually remove them. ──
    referenced_rec_paths = {os.path.abspath(r.wav_path) for r in all_recs if r.wav_path}
    rec_orphans = find_orphaned_files(settings.recordings_dir, referenced_rec_paths)

    all_dets = db.query(Detection.clip_path).filter(Detection.clip_path.isnot(None)).all()
    referenced_clip_paths = {os.path.abspath(d.clip_path) for d in all_dets if d.clip_path}
    clip_orphans = find_orphaned_files(settings.clips_dir, referenced_clip_paths)
    enhanced_orphans = _scan_enhanced(db, delete=False)
    spectrogram_orphans = _scan_spectrograms(db, delete=False)

    return {
        "recordings_dir": settings.recordings_dir,
        "used_gb": round(dir_gb, 3),
        "limit_gb": limit_gb,
        "limit_pct": round(dir_gb / limit_gb * 100, 1) if limit_gb > 0 else None,
        "compress_enabled": compress_enabled,
        "compress_quality": compress_quality,

        "directories": directories,
        "total_all_gb": round(total_all_bytes / (1024**3), 3),

        "recordings_accounting": {
            "db_rows_total": db_rows_total,
            "db_rows_active": db_rows_active,
            "db_rows_soft_deleted": db_rows_soft_deleted,
            "soft_deleted_with_file_on_disk": soft_deleted_with_file,
            "soft_deleted_reclaimable_bytes": soft_deleted_reclaimable_bytes,
            "soft_deleted_reclaimable_human": fmt_bytes(soft_deleted_reclaimable_bytes),
        },

        "orphans": {
            "recordings": rec_orphans,
            "clips": clip_orphans,
            "enhanced": enhanced_orphans,
            "spectrograms": spectrogram_orphans,
        },
    }


def _scan_enhanced(db: Session, delete: bool) -> dict:
    """enhanced_dir files whose owner is gone (deleted/archived recording or
    its detections) or whose DSP / AI Enhance version is out of date."""
    from ..services.storage_manager import scan_enhanced_cache
    live_ids = {r.id for r in db.query(Recording.id).filter(
        Recording.deleted_at.is_(None), Recording.archived_at.is_(None)).all()}
    live_ids |= {d.id for d in db.query(Detection.id).join(
        Recording, Detection.recording_id == Recording.id).filter(
        Recording.deleted_at.is_(None), Recording.archived_at.is_(None)).all()}
    return scan_enhanced_cache(getattr(settings, "enhanced_dir", ""), live_ids,
                               DSP_VERSION, ai_enhance.AI_ENHANCE_VERSION, delete=delete)


def _scan_spectrograms(db: Session, delete: bool) -> dict:
    """Spectrogram images whose recording is gone, or (for recordings with
    audio) cached for an old display threshold, palette or thumbnail size."""
    from ..services.file_cleanup import scan_spectrogram_cache
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    key = str(int(round(float(getattr(s, "min_confidence_display", 0.0) or 0.0) * 100)))
    palette = getattr(s, "detection_color_palette", None) or "vivid"
    recs = {r.id: bool(r.wav_path) and r.archived_at is None
            for r in db.query(Recording.id, Recording.wav_path, Recording.archived_at).all()}
    return scan_spectrogram_cache(recs, key, palette, delete=delete)


@router.post("/storage/purge-orphans", status_code=200)
def purge_orphans(
    target: str = Query(..., description="'recordings', 'clips', 'enhanced' or 'spectrograms'"),
    confirm: bool = Query(False, description="Must be true to actually delete — otherwise this is a dry-run preview identical to /storage/status's orphans section"),
    db: Session = Depends(get_db),
):
    """
    Delete files in recordings_dir or clips_dir that have NO matching DB row
    at all (see /storage/status's "orphans" section for a preview first).
    Deliberately requires confirm=true — without it, returns the same
    dry-run counts as the status endpoint so this is always safe to call
    speculatively from the UI without risking an accidental delete.

    Never touches soft-deleted recordings' files (those ARE referenced by a
    real DB row, just a hidden one) — use the existing "Clean up deleted"
    settings action for those instead. This endpoint only removes files
    with literally no corresponding row of any kind.
    """
    from ..services.storage_manager import find_orphaned_files, delete_orphaned_files
    from ..models import Recording, Detection

    if target == "recordings":
        dir_path = settings.recordings_dir
        all_recs = db.query(Recording.wav_path).all()
        referenced = {os.path.abspath(r.wav_path) for r in all_recs if r.wav_path}
    elif target == "enhanced":
        result = _scan_enhanced(db, delete=confirm)
        if confirm:
            logger.info("Purged enhanced cache: %d deleted (%s), %d error(s)",
                        result.get("deleted_count", 0), result.get("deleted_human", "0 B"), result.get("errors", 0))
        return {"dry_run": not confirm, **result}
    elif target == "spectrograms":
        result = _scan_spectrograms(db, delete=confirm)
        if confirm:
            logger.info("Purged spectrogram cache: %d deleted (%s), %d error(s)",
                        result.get("deleted_count", 0), result.get("deleted_human", "0 B"), result.get("errors", 0))
        return {"dry_run": not confirm, **result}
    elif target == "clips":
        dir_path = settings.clips_dir
        all_dets = db.query(Detection.clip_path).filter(Detection.clip_path.isnot(None)).all()
        referenced = {os.path.abspath(d.clip_path) for d in all_dets if d.clip_path}
    else:
        raise HTTPException(status_code=400, detail="target must be 'recordings', 'clips', 'enhanced' or 'spectrograms'")

    if not confirm:
        preview = find_orphaned_files(dir_path, referenced)
        return {"dry_run": True, **preview}

    result = delete_orphaned_files(dir_path, referenced)
    logger.info(
        "Purged orphaned %s files: %d deleted (%s), %d error(s)",
        target, result.get("deleted_count", 0), result.get("deleted_human", "0 B"), result.get("errors", 0),
    )
    return {"dry_run": False, **result}

def _reanalyze_one(rec: Recording, db: Session, background_tasks: BackgroundTasks, min_conf: Optional[float] = None, use_ai_enhance: bool = False) -> dict:
    """
    Shared reanalyze logic for a single already-fetched, already-validated
    Recording — extracted so both the single-recording endpoint and the
    bulk-reanalyze endpoint call the exact same code rather than
    maintaining two copies that could quietly drift apart from each other.
    Caller is responsible for existence/archived/audio-exists validation
    (different callers want different error-handling behavior for those —
    a single 404 vs. a per-item skip count in a bulk response).
    """
    if rec.is_bat:
        old_dets = db.query(Detection).filter(Detection.recording_id == rec.id).all()
        # Clean up the old detection(s)' clip + enhanced-cache files BEFORE
        # deleting the rows — both are keyed by detection id, and the
        # replacement detection created below gets a fresh id, so without
        # this cleanup these files would be orphaned on disk forever with
        # every reanalyze attempt on the same recording.
        for old_det in old_dets:
            if old_det.clip_path and os.path.exists(old_det.clip_path):
                try:
                    os.remove(old_det.clip_path)
                except OSError:
                    pass
            for enhanced_clip_path in (
                os.path.join(settings.enhanced_dir, f"{old_det.id}_{DSP_VERSION}_enhanced.wav"),
                os.path.join(settings.enhanced_dir, f"{old_det.id}_enhanced.wav"),
            ):
                if os.path.exists(enhanced_clip_path):
                    try:
                        os.remove(enhanced_clip_path)
                    except OSError:
                        pass
        db.query(Detection).filter(Detection.recording_id == rec.id).delete()
        rec.processing_status = "pending"
        rec.processing_error = None
        if rec.spectrogram_path and os.path.exists(rec.spectrogram_path):
            try:
                os.remove(rec.spectrogram_path)
            except OSError:
                pass
        rec.spectrogram_path = None
        rec.bat_metadata = None  # clear any previous species_guess too — this is a fresh attempt
        db.commit()
        # Bat recordings have exactly one Detection (common_name="Bat",
        # spanning the full recording) — recreate it so
        # process_recording_bg's pipeline (which iterates rec.detections)
        # has something to work with, matching what upload originally created.
        new_det = Detection(
            recording_id=rec.id, common_name="Bat", scientific_name="Chiroptera", label="Bat",
            confidence=1.0, start_time=0.0, end_time=rec.duration_seconds or 0.0,
            source="device",
        )
        db.add(new_det)
        db.commit()

        from ..cache import invalidate_detection_caches
        invalidate_detection_caches()

        background_tasks.add_task(process_recording_bg, rec.id)
        return {"status": "reanalysis_queued", "id": rec.id, "type": "bat"}

    # Clear existing server-generated detections before re-analysis, keeping
    # a copy for the new pass (see _process_manual_upload's prior) and every
    # row for Undo (the pass may also drop device detections).
    prior = _prior_server_detections(db, rec.id)
    from ..models import ReanalysisRun
    run = ReanalysisRun(recording_id=rec.id, use_ai_enhance=bool(use_ai_enhance),
                        min_conf=min_conf, before=_detection_snapshot(db, rec.id))
    db.add(run)
    # Keep the 10 newest runs per recording (each holds a detection snapshot).
    for old_run in (db.query(ReanalysisRun).filter(ReanalysisRun.recording_id == rec.id)
                    .order_by(ReanalysisRun.created_at.desc()).offset(9).all()):
        db.delete(old_run)
    db.query(Detection).filter(
        Detection.recording_id == rec.id,
        Detection.source == "server",
    ).delete()
    # Device detections stay here; _process_manual_upload removes them only
    # with server_reanalyze_delete_device on and a new pass that found something.
    rec.processing_status = "pending"
    rec.processing_error = None

    # Delete cached spectrogram so it gets regenerated with new detections
    if rec.spectrogram_path and os.path.exists(rec.spectrogram_path):
        try:
            os.remove(rec.spectrogram_path)
        except OSError:
            pass
    rec.spectrogram_path = None
    # Reported directly: the spectrogram didn't update after a reanalyze
    # that changed the detections — this only ever cleared the regular
    # spectrogram cache. The Enhanced spectrogram is a separate cached
    # file (see get_spectrogram_enhanced()'s own dumb os.path.exists()
    # check, no regard for whether the recording's analysis changed
    # underneath it) with detection overlays baked in just like the
    # regular one — never cleared here, so anyone who'd ever toggled
    # Enhanced mode for this recording would keep seeing stale overlays
    # forever, through any number of future reanalyses. The enhanced
    # *audio* cache is untouched on purpose — reanalysis re-classifies
    # the same existing audio, it doesn't change it, so there's nothing
    # wrong with that cache to invalidate.
    enhanced_spec_path = _enhanced_spec_path(rec.id)
    if os.path.exists(enhanced_spec_path):
        try:
            os.remove(enhanced_spec_path)
        except OSError:
            pass
    db.commit()

    background_tasks.add_task(_process_manual_upload, rec.id, None, use_ai_enhance,
                              prior, min_conf, run.id)
    return {"status": "reanalysis_queued", "id": rec.id, "min_conf": min_conf,
            "use_ai_enhance": use_ai_enhance, "run_id": run.id}


@router.post("/{recording_id}/reanalyze", status_code=202)
def reanalyze_recording(
    recording_id: str,
    background_tasks: BackgroundTasks,
    min_conf: Optional[float] = Query(None, ge=0.01, le=0.99, description="Minimum BirdNET confidence threshold (defaults to saved setting)"),
    use_ai_enhance: bool = Query(False, description="Run BirdNET on the AI-Enhanced audio instead of the original — see _reanalyze_one's own docstring for why this can rescue detections a noisy original missed or scored low"),
    db: Session = Depends(get_db),
):
    """
    Re-run BirdNET (or the bat pipeline, for bat recordings) on an existing
    recording. Clears existing server-generated detections and
    re-analyzes. Useful when a recording came back empty, you want to try
    a different confidence threshold, or (for bats) species ID was enabled
    or its threshold changed since this recording was first uploaded.
    """
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    # Admin can turn this off in Settings to stop people re-triggering
    # analysis at will — checked server-side, not just hidden in the UI,
    # since hiding a button alone never stops a direct request.
    app_s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if app_s and app_s.allow_manual_reanalyze is False:
        raise HTTPException(status_code=403, detail="Manual re-analysis is disabled in Settings.")
    if rec.archived_at:
        raise HTTPException(status_code=400, detail="This recording has been archived and its audio file deleted — re-analysis requires audio.")
    if not os.path.exists(rec.wav_path):
        raise HTTPException(status_code=404, detail="Audio file not found on disk")
    # Same gate as every other AI Enhance endpoint — a disabled/unavailable
    # feature returns 400 with a clear message here too, not a confusing
    # silent fallback to the original audio mid-background-task.
    if use_ai_enhance:
        if rec.is_bat:
            raise HTTPException(status_code=400, detail="AI Enhance is not available for bat recordings")
        if not app_s or not app_s.ai_enhance_enabled:
            raise HTTPException(status_code=400, detail="AI Enhance is not enabled in Settings")

    return _reanalyze_one(rec, db, background_tasks, min_conf, use_ai_enhance)


def _regenerate_visuals_bg(rec_id: str):
    """Background: redraw a recording's spectrogram and cut any missing
    detection clips (after Undo re-analysis restores older detections)."""
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        rec = db.query(Recording).filter(Recording.id == rec_id).first()
        if not rec or not rec.wav_path or not os.path.exists(rec.wav_path):
            return
        app_s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        try:
            rec.spectrogram_path = processor.generate_spectrogram(
                rec.wav_path, settings.spectrograms_dir, rec_id,
                detections=[{"common_name": d.common_name, "confidence": d.confidence,
                             "start_time": d.start_time, "end_time": d.end_time}
                            for d in rec.detections] or None,
                color_palette=getattr(app_s, "detection_color_palette", None) or "vivid",
            )
        except Exception as e:
            logger.warning("Spectrogram failed after undo for %s: %s", rec_id, e)
        for d in rec.detections:
            if d.clip_path and os.path.exists(d.clip_path):
                continue
            try:
                d.clip_path = processor.extract_clip(rec.wav_path, settings.clips_dir, d.id,
                                                     d.start_time, d.end_time,
                                                     padding=settings.clip_padding_seconds)
            except Exception as e:
                logger.debug("Clip extraction failed for %s: %s", d.id, e)
        rec.processing_status = "done"
        db.commit()
    finally:
        db.close()


def _run_out(run, latest_id: Optional[str]) -> dict:
    return {
        "id": run.id,
        "created_at": run.created_at.isoformat() + "Z" if run.created_at else None,
        "finished_at": run.finished_at.isoformat() + "Z" if run.finished_at else None,
        "status": run.status,
        "use_ai_enhance": bool(run.use_ai_enhance),
        "min_conf": run.min_conf,
        "summary": run.summary,
        "changes": run.changes or [],
        "before_count": len(run.before or []),
        "undone_at": run.undone_at.isoformat() + "Z" if run.undone_at else None,
        "can_undo": run.id == latest_id and run.status in ("done", "error"),
    }


@router.get("/{recording_id}/shadow")
def shadow_results(recording_id: str, db: Session = Depends(get_db)):
    """BirdNET v3 shadow results for one recording next to the main
    detections (Settings → Detection, with BirdNET 2.4). `ran` is false until the shadow
    pass has scored this recording."""
    from ..models import ShadowDetection
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    rows = db.query(ShadowDetection).filter(ShadowDetection.recording_id == recording_id).all()
    main = {}
    for d in rec.detections:
        main[d.common_name] = max(main.get(d.common_name, 0.0), float(d.confidence or 0))
    best = {}
    for r in rows:
        b = best.setdefault(r.common_name, {"common_name": r.common_name, "scientific_name": r.scientific_name,
                                            "confidence": 0.0, "windows": 0, "first": r.start_time})
        b["confidence"] = max(b["confidence"], r.confidence); b["windows"] += 1
        b["first"] = min(b["first"], r.start_time)
    species = sorted(best.values(), key=lambda b: -b["confidence"])
    for b in species:
        b["in_main"] = b["common_name"] in main
    return {
        "model": "BirdNET v3 (preview)",
        "ran": bool(rows) or rec.shadow_checked_at is not None,
        "species": species,
        "main_only": sorted(n for n in main if n not in best),
    }


@router.get("/{recording_id}/reanalysis-history")
def reanalysis_history(recording_id: str, limit: int = Query(10, ge=1, le=50),
                       db: Session = Depends(get_db)):
    """This recording's re-analyses, newest first, with what each changed.
    Only the newest one can be undone (older ones are superseded by it)."""
    from ..models import ReanalysisRun
    runs = (db.query(ReanalysisRun).filter(ReanalysisRun.recording_id == recording_id)
            .order_by(ReanalysisRun.created_at.desc()).limit(limit).all())
    latest = next((r.id for r in runs if r.status != "undone"), None)
    return {"runs": [_run_out(r, latest) for r in runs]}


@router.post("/{recording_id}/reanalysis/{run_id}/undo")
def undo_reanalysis(recording_id: str, run_id: str, background_tasks: BackgroundTasks,
                    db: Session = Depends(get_db)):
    """Put back the detections a re-analysis replaced (same ids, scores and
    sources) and redraw the spectrogram. Only the newest re-analysis."""
    from ..models import ReanalysisRun
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    app_s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if app_s and app_s.allow_manual_reanalyze is False:
        raise HTTPException(status_code=403, detail="Manual re-analysis is disabled in Settings.")
    run = db.query(ReanalysisRun).filter(ReanalysisRun.id == run_id,
                                         ReanalysisRun.recording_id == recording_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Re-analysis not found")
    latest = (db.query(ReanalysisRun).filter(ReanalysisRun.recording_id == recording_id,
                                             ReanalysisRun.status != "undone")
              .order_by(ReanalysisRun.created_at.desc()).first())
    if not latest or latest.id != run.id:
        raise HTTPException(status_code=409, detail="Only the most recent re-analysis can be undone.")
    if run.status == "running" or rec.processing_status in ("pending", "processing"):
        raise HTTPException(status_code=409, detail="This re-analysis is still running.")

    # Before any write: the folder scan takes seconds on a large server.
    from ..services.file_cleanup import spectrogram_files
    _old_specs = spectrogram_files([rec.id])
    keep_clips = {d.get("clip_path") for d in (run.before or []) if d.get("clip_path")}
    for d in db.query(Detection).filter(Detection.recording_id == recording_id).all():
        if d.clip_path and d.clip_path not in keep_clips and os.path.exists(d.clip_path):
            try:
                os.remove(d.clip_path)
            except OSError:
                pass
        db.delete(d)
    db.flush()
    for b in run.before or []:
        db.add(Detection(
            id=b.get("id") or str(uuid.uuid4()), recording_id=recording_id,
            common_name=b.get("common_name"), scientific_name=b.get("scientific_name"),
            label=b.get("label") or b.get("common_name"), confidence=float(b.get("confidence") or 0),
            start_time=float(b.get("start_time") or 0), end_time=float(b.get("end_time") or 3),
            clip_path=b.get("clip_path") if b.get("clip_path") and os.path.exists(b.get("clip_path")) else None,
            source=b.get("source") or "device"))
    for path in {rec.spectrogram_path, _enhanced_spec_path(rec.id), *_old_specs}:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
    rec.spectrogram_path = None
    rec.processing_status = "processing"
    rec.processing_error = None
    run.status = "undone"
    run.undone_at = datetime.utcnow()
    db.commit()
    from ..cache import invalidate_detection_caches
    invalidate_detection_caches()
    logger.info("Undid re-analysis %s of %s: restored %d detection(s)",
                run.id, recording_id, len(run.before or []))
    background_tasks.add_task(_regenerate_visuals_bg, recording_id)
    return {"status": "undone", "restored": len(run.before or []), "id": recording_id}


@router.post("/bulk-reanalyze", status_code=200)
def bulk_reanalyze(req: BulkActionRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Reanalyze multiple recordings in one call — reuses _reanalyze_one for
    each, the exact same logic the single-recording endpoint uses (bird
    recordings re-run BirdNET, bat recordings re-run the full bat pipeline
    including species classification), so bulk and single reanalysis can
    never behave differently from each other.

    Gated by the same allow_manual_reanalyze setting as the single-
    recording endpoint — otherwise bulk-reanalyzing one recording would
    be a loophole around an admin turning the button off.

    Same efficient batch-fetch pattern as bulk_archive/bulk_delete: one
    query for every requested recording rather than one per id.
    """
    app_s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if app_s and app_s.allow_manual_reanalyze is False:
        raise HTTPException(status_code=403, detail="Manual re-analysis is disabled in Settings.")
    queued = 0
    skipped = 0
    skipped_reasons = []
    recs = (
        db.query(Recording)
        .options(selectinload(Recording.detections))
        .filter(Recording.id.in_(req.ids))
        .all()
    )
    by_id = {r.id: r for r in recs}
    for rid in req.ids:
        rec = by_id.get(rid)
        if not rec:
            skipped += 1
            skipped_reasons.append(f"{rid}: not found")
            continue
        if rec.archived_at:
            skipped += 1
            skipped_reasons.append(f"{rid}: archived (no audio)")
            continue
        if not rec.wav_path or not os.path.exists(rec.wav_path):
            skipped += 1
            skipped_reasons.append(f"{rid}: audio file missing")
            continue
        _reanalyze_one(rec, db, background_tasks)
        queued += 1
    return {
        "queued": queued, "skipped": skipped,
        "message": f"Queued {queued} recording(s) for reanalysis, skipped {skipped}.",
        "skipped_reasons": skipped_reasons[:20],  # cap — a bulk selection could be large
    }


@router.post("/repair-durations", status_code=200)
def repair_durations(
    recording_id: Optional[str] = Query(None, description="Repair only this one recording; omit to scan all"),
    dry_run: bool = Query(False, description="Report what would change without writing anything"),
    db: Session = Depends(get_db),
):
    """
    Retroactively correct duration_seconds for already-uploaded recordings
    by re-reading the real WAV file, the same cross-check now applied at
    upload time going forward. Needed because that upload-time fix only
    protects recordings uploaded AFTER it shipped — anything uploaded
    before could still carry a wrong duration_seconds inherited from the
    device's wall-clock estimate (see the device-side fix in
    chirp-device/chirp/recorder.py for the full root cause).

    Skips archived recordings (audio deleted, nothing to re-read) and any
    recording whose wav_path is missing on disk. Returns a summary rather
    than per-recording detail to keep the response small when scanning
    everything.
    """
    q = db.query(Recording).filter(Recording.archived_at.is_(None))
    if recording_id:
        q = q.filter(Recording.id == recording_id)
        target = q.first()
        if not target:
            raise HTTPException(status_code=404, detail="Recording not found, or it's archived (audio deleted)")
        recordings = [target]
    else:
        recordings = q.all()

    import soundfile as _sf
    checked = 0
    corrected = 0
    missing_files = 0
    unreadable = 0
    examples = []  # first few corrections, for visibility in the response

    for rec in recordings:
        if not rec.wav_path or not os.path.exists(rec.wav_path):
            missing_files += 1
            continue
        checked += 1
        try:
            real_duration = float(_sf.info(rec.wav_path).duration)
        except Exception as e:
            unreadable += 1
            logger.warning("repair-durations: could not read %s: %s", rec.wav_path, e)
            continue

        old = rec.duration_seconds or 0.0
        if abs(real_duration - old) > 0.05:
            corrected += 1
            if len(examples) < 20:
                examples.append({
                    "id": rec.id, "filename": rec.filename,
                    "old_duration_seconds": round(old, 2),
                    "real_duration_seconds": round(real_duration, 2),
                })
            if not dry_run:
                rec.duration_seconds = real_duration

    if not dry_run and corrected:
        db.commit()

    return {
        "dry_run": dry_run,
        "scanned": len(recordings),
        "checked_against_real_file": checked,
        "corrected": corrected,
        "missing_files": missing_files,
        "unreadable_files": unreadable,
        "examples": examples,
    }


# ── Waveform Data ─────────────────────────────────────────────────────────────

@router.get("/{recording_id}/spectrogram-bounds")
async def get_spectrogram_bounds(recording_id: str, db: Session = Depends(get_db)):
    """Return the axes bounds (left/right fractions) for aligning the waveform player."""
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    import json as _json, os as _os
    if rec.spectrogram_path:
        bounds_path = rec.spectrogram_path.replace("_spectrogram.png", "_spectrogram_bounds.json")
        if _os.path.exists(bounds_path):
            return _json.load(open(bounds_path))
    # Fallback: return the known fixed values matching subplots_adjust
    return {"left_frac": 0.045, "right_frac": 0.998, "bottom_frac": 0.12, "top_frac": 0.99}

@router.get("/{recording_id}/waveform")
def get_waveform(
    recording_id: str,
    response: Response,
    # ge=10 (was 100): RecordingDetail.jsx's per-species mini-waveform
    # requests only MINI_BARS=28 points for its compact display — a real,
    # intentional value, not a bug in the caller. The old ge=100 floor
    # was rejecting every one of those requests with a 500 (surfaced as
    # a real report: repeated "Input should be >= 100" validation
    # warnings in the server log for a genuine, legitimate 28-point
    # request).
    points: int = Query(2000, ge=10, le=8000),
    db: Session = Depends(get_db),
):
    """
    Return downsampled waveform as [[min, max], ...] for rendering an
    accurate amplitude waveform in the frontend audio player.

    Investigated directly as part of a Dashboard/Recordings performance
    pass: this recomputed the waveform from scratch on every single
    request, with no caching at any layer — not even an HTTP cache
    header, unlike get_spectrogram()'s two-layer approach just above.
    Benchmarked at 12-58ms depending on recording length; modest per
    call, but paid again on every page view/refresh of the same
    recording for data that never changes once the recording exists.
    Immutable HTTP caching, same rationale and duration as the
    spectrogram cache: a recording's audio content doesn't change after
    the fact (compress_on_upload can change the file format later, but
    not the underlying waveform shape), so there's nothing to
    invalidate.
    """
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec or not os.path.exists(rec.wav_path):
        raise HTTPException(status_code=404, detail="Audio not found")
    try:
        import soundfile as sf
        info = sf.info(rec.wav_path)
        result = processor.get_waveform_data(rec.wav_path, num_points=points)
        response.headers["Cache-Control"] = "public, max-age=2592000, immutable"
        return {"waveform": result, "sample_rate": info.samplerate, "duration": info.duration}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Waveform error: {e}")


# ── Share Tokens ──────────────────────────────────────────────────────────────

@router.post("/{recording_id}/share")
def create_share_link(recording_id: str, db: Session = Depends(get_db)):
    """Generate a public shareable link for a recording (no auth required to view)."""
    from ..models import ShareToken
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    existing = db.query(ShareToken).filter(ShareToken.recording_id == recording_id).first()
    if existing:
        return {"token": existing.token, "url": f"/share/{existing.token}"}
    import secrets
    token = secrets.token_urlsafe(16)
    db.add(ShareToken(token=token, recording_id=recording_id))
    db.commit()
    return {"token": token, "url": f"/share/{token}"}


@router.get("/shared/{token}")
def get_shared_recording(token: str, db: Session = Depends(get_db)):
    """Load a shared recording by its share token."""
    from ..models import ShareToken
    st = db.query(ShareToken).filter(ShareToken.token == token).first()
    if not st:
        raise HTTPException(status_code=404, detail="Share link not found or expired")
    st.view_count = (st.view_count or 0) + 1
    db.commit()
    rec = db.query(Recording).filter(Recording.id == st.recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording no longer exists")
    return recording_to_out(rec, db)


# ── iNaturalist submission ─────────────────────────────────────────────────────

def _format_second_opinion_comment(ai_reanalysis_note: str) -> str:
    """
    Shared formatting for the AI second opinion as an iNaturalist
    comment — used by both the initial submission flow (when the
    "Include AI second opinion" option is checked) and the dedicated
    post_inaturalist_comment endpoint for an already-submitted
    recording, so the two paths can't drift into two different-looking
    comments for what's conceptually the same action.
    """
    return (
        "\U0001f916 AI second opinion (via Chirp, not an official iNaturalist identification):\n\n"
        f"{tidy_stored_note(ai_reanalysis_note)}"
    )


def _build_inat_description(rec, det, detections, include_details, db):
    """
    Build the iNaturalist observation DESCRIPTION — always the real,
    auto-generated detection summary, never replaced by the user's own
    notes. A real, confirmed bug this fixes: the previous version used
    `user_notes or "Automated detection..."`, so providing ANY note at
    all silently dropped the auto-generated summary line from the
    description. User notes are now posted as their own SEPARATE
    iNaturalist comment instead (see submit_to_inaturalist below) — a
    structurally cleaner fix than trying to merge the two into one
    field, since it means neither can ever overwrite the other no
    matter what either one contains.

    When include_details is true, appends real recording metadata and a
    per-detection timestamp breakdown below the summary — using only
    fields that actually exist on Recording/Detection, not invented data.
    """
    base = f"Automated detection by Chirp bird monitoring system. Species: {det.common_name}."
    if not include_details:
        return base

    lines = [base, ""]

    # Recording metadata
    lines.append(f"Recorded: {rec.trigger_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    if rec.duration_seconds:
        lines.append(f"Duration: {rec.duration_seconds:.1f}s")
    device_name = None
    if rec.device_id:
        try:
            from ..models import Device as _Device
            dev = db.query(_Device).filter(_Device.id == rec.device_id).first()
            device_name = dev.name if dev else None
        except Exception:
            device_name = None
    if device_name:
        lines.append(f"Device: {device_name}")

    # Per-detection breakdown — every detection in this recording, not just
    # the one being submitted, so the observation's description documents
    # everything Chirp heard in the clip even though only one species can
    # be the observation's primary identification.
    if detections:
        lines.append("")
        lines.append("Detections in this recording:")
        for d in sorted(detections, key=lambda x: x.start_time or 0):
            start = d.start_time or 0
            end = d.end_time or 0
            conf_pct = round((d.confidence or 0) * 100)
            marker = "→ " if d.id == det.id else "  "
            lines.append(f"{marker}{d.common_name}: {start:.1f}s–{end:.1f}s ({conf_pct}% confidence)")

    return "\n".join(lines)


class InatSubmitRequest(BaseModel):
    detection_id: Optional[str] = None   # specific detection to use; if None uses top species
    notes: Optional[str] = ""
    use_enhanced_audio: bool = False     # submit the noise-reduced version instead of the original WAV
    include_spectrogram: bool = True     # attach the spectrogram (with detection-box overlays) as a second photo
    include_details: bool = True         # append per-detection timestamps + recording metadata to the description
    include_second_opinion: bool = False # post the AI second opinion (ai_reanalysis_note) as a separate comment — defaults False deliberately, unlike the options above: posting AI-generated content to a public platform is a different kind of decision than including objective recording metadata, worth requiring explicit opt-in for

@router.post("/{recording_id}/submit-inaturalist")
def submit_to_inaturalist(
    recording_id: str,
    body: InatSubmitRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Submit a recording as an iNaturalist sound observation.
    Requires admin or submitter role, and an iNat API token in Settings.
    """
    from ..models import AppSettings, BirdProfile, Detection as _Det, User as _User
    from ..api.auth import verify_token

    # Role check — admin or submitter only.
    #
    # Bug (found live): this used to trust a "role" claim baked into the
    # JWT at login time. In chirp-server-instances that claim is never
    # set at all (login() only returns role in the response body, not
    # in the signed token itself) — so payload.get("role", "viewer")
    # silently fell back to "viewer" for every user, every time,
    # regardless of actual role, including real admins. Fixed by doing
    # a live lookup against this instance's own User table (same
    # username-from-token pattern get_current_user already uses
    # elsewhere), which also means a role promotion takes effect
    # immediately instead of requiring the user to log out and back in.
    token_str = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token_str = auth_header[7:]
    role = "viewer"
    if token_str:
        payload = verify_token(token_str)
        if payload:
            user_row = db.query(_User).filter(_User.username == payload.get("sub")).first()
            if user_row and user_row.active:
                role = user_row.role
    # When auth is disabled, treat as admin
    s_auth = db.query(AppSettings).first()
    auth_on = bool(s_auth.auth_enabled) if s_auth and s_auth.auth_enabled is not None else False
    if not auth_on:
        role = "admin"
    if role not in ("admin", "submitter"):
        raise HTTPException(status_code=403, detail="Submitting to iNaturalist requires admin or submitter role.")

    # Load recording
    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    if rec.archived_at:
        raise HTTPException(
            status_code=400,
            detail="This recording has been archived and its audio file deleted — iNaturalist sound observations require audio to submit.",
        )

    # Get iNat token: prefer the user's own token, fall back to global settings
    user_obj = None
    if token_str:
        payload_user = verify_token(token_str)
        if payload_user and payload_user.get("sub"):
            from ..models import User as _User
            user_obj = db.query(_User).filter(_User.username == payload_user["sub"]).first()

    inat_token = (
        getattr(user_obj, "inat_api_token", None)
        or getattr(s_auth, "inat_api_token", None)
        if s_auth else None
    )
    if not inat_token:
        raise HTTPException(
            status_code=400,
            detail="No iNaturalist API token configured. Add your personal token in My Profile, or ask an admin to set a global token in Settings → API Keys."
        )

    # Resolve detection to use
    det = None
    if body.detection_id:
        det = db.query(_Det).filter(_Det.id == body.detection_id, _Det.recording_id == recording_id).first()
    if not det and rec.detections:
        det = max(rec.detections, key=lambda d: d.confidence)
    if not det:
        raise HTTPException(status_code=400, detail="No detections found for this recording.")

    # Look up BirdProfile for taxon_id — NOT used for bat detections (see
    # below): "Bat" isn't a real taxonomic rank, so its BirdProfile resolves
    # to the ORDER-level Chiroptera as the closest real match, which then
    # shows on iNaturalist as the observation's primary identification
    # ("Chiroptera"), not "Bat" — a real reported point of confusion, and
    # arguably a genuine overclaim: bat detection here identifies "activity
    # consistent with echolocation," explicitly not species (see
    # bat_detector.py's own docstring), so asserting even an order-level ID
    # states more taxonomic confidence than the system actually has.
    bp = db.query(BirdProfile).filter(BirdProfile.common_name == det.common_name).first()
    is_bat_detection = det.common_name == "Bat"
    taxon_id = None if is_bat_detection else (bp.inaturalist_id if bp else None)
    submit_scientific_name = None if is_bat_detection else (det.scientific_name or (bp.scientific_name if bp else None))

    # Determine location
    lat = rec.latitude or (s_auth.latitude if s_auth else None)
    lon = rec.longitude or (s_auth.longitude if s_auth else None)

    # Resolve which WAV to actually submit. Enhanced audio is generated
    # on-demand and cached the same way the existing enhanced-playback
    # endpoints already do (settings.enhanced_dir/{id}_enhanced.wav) — if
    # generation fails for any reason, fall back to the original rather
    # than blocking the whole submission over an optional toggle.
    submit_wav_path = rec.wav_path
    if body.use_enhanced_audio:
        enhanced_path = os.path.join(settings.enhanced_dir, f"{_nr_cache_id(recording_id, rec.is_bat)}_enhanced.wav")
        if not os.path.exists(enhanced_path):
            try:
                if rec.is_bat:
                    enhanced_path = processor.downshift_bat_clip(rec.wav_path, settings.enhanced_dir, recording_id)
                else:
                    # apply_bandpass=False, matching /audio/enhanced's own
                    # updated scope (pure noise reduction now) — this can
                    # also be the first to generate the shared cache.
                    enhanced_path = processor.enhance_audio(rec.wav_path, settings.enhanced_dir, _nr_cache_id(recording_id), apply_bandpass=False)
            except Exception as e:
                logger.warning("submit_to_inaturalist: enhanced audio generation failed, using original: %s", e)
                enhanced_path = None
        if enhanced_path and os.path.exists(enhanced_path):
            submit_wav_path = enhanced_path

    description = _build_inat_description(
        rec, det, rec.detections, body.include_details, db
    )

    # Phase 1 — fast (<10 s): create observation, return immediately
    from ..services.inat_service import submit_observation, attach_sound_background, attach_photo_background
    from ..database import SessionLocal as _SL
    try:
        result = submit_observation(
            token=inat_token,
            common_name=det.common_name,
            scientific_name=submit_scientific_name,
            taxon_id=taxon_id,
            wav_path=submit_wav_path,
            observed_at=rec.trigger_timestamp,
            latitude=lat,
            longitude=lon,
            notes=description,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Persist observation link immediately
    inat_note = "\U0001f4ce iNaturalist: [{inat_id}]({inat_url})".format(
        inat_id=result.get('inat_id'), inat_url=result.get('inat_url', '')
    )
    if "inaturalist.org" not in (rec.notes or ""):
        rec.notes = ((rec.notes or "") + "\n" + inat_note).strip()
    if hasattr(rec, 'inat_observation_id'):
        rec.inat_observation_id  = str(result.get('inat_id', ''))
        rec.inat_observation_url = result.get('inat_url', '')
    db.commit()

    # User's own additional notes, if given, are posted as a genuinely
    # SEPARATE comment — not blended into the description at all, and
    # therefore structurally unable to ever overwrite the real detection
    # details there (see _build_inat_description's own docstring for the
    # real bug this replaces). Background task, same reasoning as the
    # sound/photo attachments below: never let a slower iNat API call
    # hold up the HTTP response, and a failure here shouldn't fail the
    # whole submission — the observation itself was already created
    # successfully by this point.
    if body.notes and body.notes.strip():
        from ..services.inat_service import post_comment_background
        background_tasks.add_task(
            post_comment_background,
            token=inat_token,
            obs_id=result.get("inat_id"),
            body=body.notes.strip(),
        )

    # AI second opinion, if the "Include AI second opinion" option was
    # checked in the submission modal — same real gap a direct report
    # flagged: this was previously only reachable as a separate,
    # easy-to-miss follow-up action AFTER submission (the dedicated
    # post_inaturalist_comment endpoint above), with no way to include
    # it as part of the actual submission itself. Posted as its own
    # comment (via the same shared _format_second_opinion_comment used
    # by that dedicated endpoint), not blended into the description —
    # same reasoning as the user notes above.
    if body.include_second_opinion and rec.ai_reanalysis_note:
        from ..services.inat_service import post_comment_background
        background_tasks.add_task(
            post_comment_background,
            token=inat_token,
            obs_id=result.get("inat_id"),
            body=_format_second_opinion_comment(rec.ai_reanalysis_note),
        )

    # Phase 2 — background: transcode + attach sound (no proxy timeout)
    background_tasks.add_task(
        attach_sound_background,
        token=inat_token,
        obs_id=result.get("inat_id"),
        wav_path=submit_wav_path,
        recording_id=rec.id,
        db_factory=_SL,
    )

    # Optionally attach the spectrogram (with detection-box overlays
    # already baked in, confirmed from get_spectrogram's own docstring —
    # the only thing NOT included is the frontend's separate legend UI,
    # which is redundant here anyway since each box is already
    # self-labeled with its species name and confidence) as a second
    # observation photo, same background-task pattern as the sound
    # attachment so it can't block or delay the HTTP response.
    if body.include_spectrogram:
        spec_path = rec.spectrogram_path
        if spec_path and os.path.exists(spec_path):
            background_tasks.add_task(
                attach_photo_background,
                token=inat_token,
                obs_id=result.get("inat_id"),
                image_path=spec_path,
            )
        else:
            logger.info("submit_to_inaturalist: spectrogram not yet generated for %s, skipping photo attachment", recording_id)

    return result


class InatCommentRequest(BaseModel):
    comment_type: str = "second_opinion"  # "second_opinion" | "custom"
    body: Optional[str] = None            # required when comment_type == "custom"

@router.post("/{recording_id}/inaturalist-comment")
def post_inaturalist_comment(
    recording_id: str,
    body: InatCommentRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Posts a real comment on this recording's already-submitted
    iNaturalist observation — the new capability this project didn't
    have before: only the observation's own description could carry any
    text, with no way to add anything after the fact. Two real uses:
    comment_type="second_opinion" posts the AI's own re-analysis note
    (Recording.ai_reanalysis_note — see call_reanalysis.py) clearly
    attributed as AI-generated, not blended into anything else;
    comment_type="custom" posts arbitrary text the caller provides.
    Requires the recording to have already been submitted to
    iNaturalist (a real inat_observation_id on file) — there's nothing
    to comment ON otherwise.
    """
    from ..models import AppSettings, User as _User
    from ..api.auth import verify_token

    # Same live-lookup fix as submit_to_inaturalist above — see that
    # function's comment for why the JWT "role" claim can't be trusted.
    token_str = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token_str = auth_header[7:]
    role = "viewer"
    if token_str:
        payload = verify_token(token_str)
        if payload:
            user_row = db.query(_User).filter(_User.username == payload.get("sub")).first()
            if user_row and user_row.active:
                role = user_row.role
    s_auth = db.query(AppSettings).first()
    auth_on = bool(s_auth.auth_enabled) if s_auth and s_auth.auth_enabled is not None else False
    if not auth_on:
        role = "admin"
    if role not in ("admin", "submitter"):
        raise HTTPException(status_code=403, detail="Posting iNaturalist comments requires admin or submitter role.")

    rec = db.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    if not rec.inat_observation_id:
        raise HTTPException(
            status_code=400,
            detail="This recording hasn't been submitted to iNaturalist yet — submit it first, then you can add a comment.",
        )

    if body.comment_type == "second_opinion":
        if not rec.ai_reanalysis_note:
            raise HTTPException(
                status_code=400,
                detail="No AI second opinion has been generated for this recording yet — use \"Re-check this call\" first.",
            )
        comment_body = _format_second_opinion_comment(rec.ai_reanalysis_note)
    elif body.comment_type == "custom":
        if not body.body or not body.body.strip():
            raise HTTPException(status_code=400, detail="body is required when comment_type is \"custom\".")
        comment_body = body.body.strip()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown comment_type: {body.comment_type!r}")

    user_obj = None
    if token_str:
        payload_user = verify_token(token_str)
        if payload_user and payload_user.get("sub"):
            from ..models import User as _User
            user_obj = db.query(_User).filter(_User.username == payload_user["sub"]).first()
    inat_token = (
        getattr(user_obj, "inat_api_token", None)
        or getattr(s_auth, "inat_api_token", None)
        if s_auth else None
    )
    if not inat_token:
        raise HTTPException(
            status_code=400,
            detail="No iNaturalist API token configured. Add your personal token in My Profile, or ask an admin to set a global token in Settings → API Keys.",
        )

    from ..services.inat_service import post_comment
    try:
        result = post_comment(token=inat_token, obs_id=rec.inat_observation_id, body=comment_body)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {"posted": True, "comment_id": result.get("comment_id"), "inat_url": rec.inat_observation_url}


@router.get("/settings/inat-verify")
def verify_inat_token(db: Session = Depends(get_db)):
    """Verify the stored iNaturalist token is valid."""
    s = db.query(AppSettings).first()
    token = getattr(s, "inat_api_token", None) if s else None
    if not token:
        return {"valid": False, "error": "No token configured"}
    from ..services.inat_service import check_token
    return check_token(token)


# ── Statistics Page Endpoint ───────────────────────────────────────────────────


@router.get("/statistics/full")
def full_statistics(
    heatmap_limit: int = Query(10, ge=1, le=500),
    metric: str = Query("detections", description="'detections' or 'recordings'"),
    exclude_bats: bool = Query(True, description="Exclude bat-echolocation recordings from every chart on this page — they get a generic common_name of \"Bat\" (see upload-manual/is_bat), which otherwise pollutes bird-focused species charts (top species, monthly/hourly distribution, heatmap) as if it were a real species. Bats already have their own dedicated Bat Activity section further down this page."),
    db: Session = Depends(get_db),
):
    """
    Rich statistics for the Statistics page — all queries use the same
    filters (deleted_at, min_confidence_display) so every chart is consistent.
    metric='detections' (default): counts Detection rows (one per species per recording).
    metric='recordings': counts distinct Recording rows (one per triggered event).
    """
    from ..cache import slow_stats_cache as statistics_cache
    _metric = metric if metric in ("detections", "recordings") else "detections"
    _by_rec = _metric == "recordings"
    cache_key = f"stats_{heatmap_limit}_{_metric}_{exclude_bats}"
    cached = statistics_cache.get(cache_key)
    if cached is not None:
        return cached

    from sqlalchemy import func, or_, and_
    from ..models import AppSettings as _AS

    _s = db.query(_AS).filter(_AS.id == 1).first()
    _show_del = bool(getattr(_s, "show_deleted_detections", False)) if _s else False
    _min_conf = float(getattr(_s, "min_confidence_display", 0.0) or 0.0) if _s else 0.0

    # ── Shared base query — apply all filters once ────────────────────────────
    # Excludes species detected ONLY via Haikubox, for the same reason
    # get_life_list() and the Dashboard's recording_stats() both already
    # exclude them: a species with zero real Pi/device detections was never
    # actually heard by this Chirp install, and disabling the Haikubox
    # toggle doesn't delete these rows, so without this exclusion every
    # chart on the Statistics page (Life List Growth, day-of-week activity,
    # confidence-by-species, top species) would keep counting Haikubox-only
    # species even with the feature turned off — exactly what caused the
    # Life List Growth chart to still show 88 species (matching the
    # Dashboard's pre-fix count) instead of 80 after Haikubox was disabled.
    # This is the SAME class of bug fixed for recording_stats() previously,
    # but full_statistics() is a separate query path that fix never touched.

    from ..services.species_filters import exclude_haikubox_only

    def _base():
        q = exclude_haikubox_only(
            db.query(Detection).join(Recording, Detection.recording_id == Recording.id), db)
        if not _show_del:
            q = q.filter(Recording.deleted_at.is_(None))
        if _min_conf > 0:
            q = q.filter(Detection.confidence >= _min_conf)
        if exclude_bats:
            q = q.filter(Recording.is_bat == False)
        return q

    # Total species count — NOT the same as len(top_species), which is
    # deliberately capped to max(20, heatmap_limit) for the bar chart/
    # heatmap. The frontend previously had no total_species field to read
    # from this endpoint, and silently fell back to top_species.length
    # instead — reporting the query's LIMIT (20 by default) as if it were
    # the actual species count (20 shown instead of the real 80).
    total_species = _base().with_entities(func.count(Detection.common_name.distinct())).scalar()

    # Top species — count by detections or distinct recordings depending on metric
    _count_expr = func.count(Recording.id.distinct()) if _by_rec else func.count(Detection.id)
    top_species = (
        _base()
        .with_entities(Detection.common_name, _count_expr.label("n"))
        .group_by(Detection.common_name)
        .order_by(_count_expr.desc())
        .limit(max(20, heatmap_limit))  # always fetch enough for both top-20 bar and heatmap
        .all()
    )
    top10 = [s for s, _ in top_species[:heatmap_limit]]

    # Monthly distribution
    # Counting detections, month / hour / weekday / month-by-species all come
    # from one grouped scan instead of four (each full scan of the
    # detections join took about half a second on a year-old site).
    # Counting recordings needs DISTINCT per group, so it keeps its queries.
    _cube = None
    if not _by_rec:
        _cube = (
            _base()
            .with_entities(
                func.strftime("%m", Recording.trigger_timestamp).label("month"),
                func.strftime("%H", Recording.trigger_timestamp).label("hour"),
                func.strftime("%w", Recording.trigger_timestamp).label("dow"),
                Detection.common_name,
                func.count(Detection.id).label("n"),
            )
            .filter(Recording.trigger_timestamp.isnot(None))
            .group_by("month", "hour", "dow", Detection.common_name).all()
        )

    def _cube_sum(*keys):
        out: dict = {}
        for r in _cube:
            k = tuple(getattr(r, x) for x in keys)
            out[k] = out.get(k, 0) + r.n
        return out

    if _cube is not None:
        monthly_dict = {int(k[0]): n for k, n in _cube_sum("month").items()}
    else:
        monthly_rows = (
            _base()
            .with_entities(
                func.strftime("%m", Recording.trigger_timestamp).label("month"),
                _count_expr.label("n"),
            )
            .filter(Recording.trigger_timestamp.isnot(None))
            .group_by("month").order_by("month").all()
        )
        monthly_dict = {int(r.month): r.n for r in monthly_rows}
    monthly_data = [{"month": m, "count": monthly_dict.get(m, 0)} for m in range(1, 13)]

    # Hour-of-day distribution — convert UTC → configured timezone before grouping
    from zoneinfo import ZoneInfo
    from datetime import datetime as _dt
    _tz_name = (db.query(AppSettings).first() or AppSettings()).timezone or "UTC"
    try:
        _tz = ZoneInfo(_tz_name)
    except Exception:
        _tz = ZoneInfo("UTC")
    # Compute current UTC offset (hours, accounting for DST)
    _now = _dt.now(ZoneInfo("UTC")).astimezone(_tz)
    _offset_h = int(_now.utcoffset().total_seconds() // 3600)

    if _cube is not None:
        hourly_dict_utc = {int(k[0]): n for k, n in _cube_sum("hour").items()}
    else:
        hourly_rows = (
            _base()
            .with_entities(
                func.strftime("%H", Recording.trigger_timestamp).label("hour"),
                _count_expr.label("n"),
            )
            .filter(Recording.trigger_timestamp.isnot(None))
            .group_by("hour").order_by("hour").all()
        )
        hourly_dict_utc = {int(r.hour): r.n for r in hourly_rows}
    # Shift each UTC bucket to local time
    hourly_dict: dict[int, int] = {}
    for h_utc, n in hourly_dict_utc.items():
        h_local = (h_utc + _offset_h) % 24
        hourly_dict[h_local] = hourly_dict.get(h_local, 0) + n
    hourly_data = [{"hour": h, "count": hourly_dict.get(h, 0)} for h in range(24)]

    # Recording-time-normalized version, same reasoning as
    # day_of_week_normalized above: an hour-of-day bucket with more total
    # recording time behind it will show more raw detections even at an
    # identical activity rate. Dividing by actual recorded seconds in
    # that hour bucket gives "detections per hour actually recorded".
    # Same Haikubox-duration exclusion as the day-of-week version, same
    # reason (synthetic 3s placeholder duration would distort real
    # listening-time sums).
    hour_duration_rows = (
        db.query(
            func.strftime("%H", Recording.trigger_timestamp).label("hour"),
            func.sum(Recording.duration_seconds).label("total_seconds"),
        )
        .filter(Recording.trigger_timestamp.isnot(None))
        .filter(Recording.haikubox_detection_id.is_(None))
    )
    if not _show_del:
        hour_duration_rows = hour_duration_rows.filter(Recording.deleted_at.is_(None))
    hour_duration_rows = hour_duration_rows.group_by("hour").all()
    hour_seconds_utc: dict[int, float] = {}
    for r in hour_duration_rows:
        hour_seconds_utc[int(r.hour)] = (r.total_seconds or 0)
    hour_seconds_local: dict[int, float] = {}
    for h_utc, secs in hour_seconds_utc.items():
        h_local = (h_utc + _offset_h) % 24
        hour_seconds_local[h_local] = hour_seconds_local.get(h_local, 0) + secs
    hourly_data_normalized = [
        {
            "hour": h,
            "count": hourly_dict.get(h, 0),
            "hours_recorded": round(hour_seconds_local.get(h, 0) / 3600.0, 2),
            "per_hour": round(hourly_dict.get(h, 0) / (hour_seconds_local[h] / 3600.0), 2)
                        if hour_seconds_local.get(h, 0) > 0 else 0,
        }
        for h in range(24)
    ]

    # Confidence distribution buckets
    # Bucketed in SQL rather than pulling every confidence value into Python.
    from sqlalchemy import Integer, cast
    _bucket = cast(Detection.confidence * 10, Integer)
    conf_hist = [0] * 10
    for b, n in _base().with_entities(_bucket.label("b"), func.count(Detection.id)).group_by("b").all():
        if b is not None:
            conf_hist[min(max(int(b), 0), 9)] += n
    conf_data = [{"bucket": f"{i*10}-{(i+1)*10}%", "low": i * 10, "count": conf_hist[i]}
                 for i in range(10)]

    # Species × Month heatmap (top 10 species)
    heatmap: dict = {s: [0] * 12 for s in top10}
    if _cube is not None:
        for (month, name), n in _cube_sum("month", "common_name").items():
            if name in heatmap:
                heatmap[name][int(month) - 1] = n
    else:
        sbm_rows = (
            _base()
            .with_entities(
                func.strftime("%m", Recording.trigger_timestamp).label("month"),
                Detection.common_name,
                _count_expr.label("n"),
            )
            .filter(Recording.trigger_timestamp.isnot(None))
            .group_by("month", Detection.common_name).all()
        )
        for row in sbm_rows:
            if row.common_name in heatmap:
                heatmap[row.common_name][int(row.month) - 1] = row.n

    # Day-of-week (SQLite %w: 0=Sun)
    if _cube is not None:
        dow_dict = {int(k[0]): n for k, n in _cube_sum("dow").items()}
    else:
        dow_rows = (
            _base()
            .with_entities(
                func.strftime("%w", Recording.trigger_timestamp).label("dow"),
                _count_expr.label("n"),
            )
            .filter(Recording.trigger_timestamp.isnot(None))
            .group_by("dow").order_by("dow").all()
        )
        dow_dict = {int(r.dow): r.n for r in dow_rows}
    dow_labels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    dow_data = [{"day": dow_labels[d], "count": dow_dict.get(d, 0)} for d in range(7)]

    # Recording-time-normalized version of the same chart: raw detection
    # counts by day of week are biased by how MUCH was actually recorded
    # that day — a day with 10 hours of recording will show more
    # detections than a day with 1 hour even if the bird activity rate was
    # identical. Dividing by total recording hours for that day of week
    # gives "detections per hour actually recorded", a fairer comparison.
    #
    # Sums DISTINCT recordings' duration_seconds per day-of-week (not
    # per-detection, which would multiply-count the same recording's
    # duration once for every species detected within it) and explicitly
    # excludes Haikubox-sourced recordings from the duration sum — those
    # carry a synthetic 3-second placeholder duration (Haikubox is a cloud
    # detection feed with no real audio file), and summing that as if it
    # were real listening time would badly distort the normalization.
    # Detections FROM Haikubox recordings are already excluded from
    # dow_rows above for Haikubox-only species via _base(); a species
    # detected by both Pi and Haikubox still has its Haikubox detections
    # counted in the numerator here, same as everywhere else in this file,
    # but its synthetic duration is kept out of the denominator regardless.
    duration_rows = (
        db.query(
            func.strftime("%w", Recording.trigger_timestamp).label("dow"),
            func.sum(Recording.duration_seconds).label("total_seconds"),
        )
        .filter(Recording.trigger_timestamp.isnot(None))
        .filter(Recording.haikubox_detection_id.is_(None))
    )
    if not _show_del:
        duration_rows = duration_rows.filter(Recording.deleted_at.is_(None))
    duration_rows = duration_rows.group_by("dow").order_by("dow").all()
    dow_hours = {int(r.dow): (r.total_seconds or 0) / 3600.0 for r in duration_rows}
    dow_data_normalized = [
        {
            "day": dow_labels[d],
            "count": dow_dict.get(d, 0),
            "hours_recorded": round(dow_hours.get(d, 0), 2),
            "per_hour": round(dow_dict.get(d, 0) / dow_hours[d], 2) if dow_hours.get(d, 0) > 0 else 0,
        }
        for d in range(7)
    ]

    # Cumulative life-list growth — bucketed by REAL calendar day, with the
    # cumulative total carried forward on days with no new species.
    # (Previously this was one point per species on a categorical x-axis,
    # which spaces points evenly regardless of actual elapsed time between
    # discoveries — making the chart look like a straight diagonal line.
    # Real growth is bursty: many species in the first week, then long flat
    # stretches. A daily-resolution series with carry-forward shows that.)
    first_seen = (
        _base()
        .with_entities(
            Detection.common_name,
            func.min(Recording.trigger_timestamp).label("first"),
        )
        .group_by(Detection.common_name)
        .order_by(func.min(Recording.trigger_timestamp)).all()
    )
    new_species_by_date: dict = {}
    for row in first_seen:
        if not row.first:
            continue
        d = row.first.date()
        new_species_by_date.setdefault(d, []).append(row.common_name)

    cumulative = []
    if new_species_by_date:
        from datetime import timedelta as _td
        all_dates = sorted(new_species_by_date.keys())
        start_d, end_d = all_dates[0], all_dates[-1]
        total_days = (end_d - start_d).days + 1
        # Downsample to weekly buckets if the range is long, to keep payload
        # small and the chart readable — still carries the real cumulative
        # value forward, just sampled at a coarser interval.
        step_days = 1 if total_days <= 200 else max(1, total_days // 200)

        running_total = 0
        last_new_species = []
        d = start_d
        while d <= end_d:
            todays_new = new_species_by_date.get(d, [])
            running_total += len(todays_new)
            if todays_new:
                last_new_species = todays_new
            cumulative.append({
                "date": d.strftime("%Y-%m-%d"),
                "total": running_total,
                "species": ", ".join(todays_new) if todays_new else (
                    f"+0 (last: {', '.join(last_new_species[:2])})" if last_new_species else ""
                ),
            })
            d += _td(days=step_days)
        # Always include the final day exactly (loop above may overshoot/undershoot end_d)
        if cumulative and cumulative[-1]["date"] != end_d.strftime("%Y-%m-%d"):
            cumulative.append({
                "date": end_d.strftime("%Y-%m-%d"),
                "total": running_total,
                "species": "",
            })

    # Seasonal totals
    season_map = {1:"Winter",2:"Winter",3:"Spring",4:"Spring",5:"Spring",
                  6:"Summer",7:"Summer",8:"Summer",9:"Autumn",10:"Autumn",
                  11:"Autumn",12:"Winter"}
    season_counts: dict = {"Spring":0,"Summer":0,"Autumn":0,"Winter":0}
    for m, cnt in monthly_dict.items():
        season_counts[season_map[m]] += cnt
    seasonal_data = [{"season": s, "count": season_counts[s]}
                     for s in ["Spring","Summer","Autumn","Winter"]]

    # Per-species confidence stats — ALL species, not just a top-N slice.
    # Frontend sizes the chart height dynamically and makes it scrollable.
    species_conf = (
        _base()
        .with_entities(
            Detection.common_name,
            func.avg(Detection.confidence).label("avg"),
            func.max(Detection.confidence).label("max"),
            _count_expr.label("n"),
        )
        .group_by(Detection.common_name)
        .order_by(func.avg(Detection.confidence).desc())
        .all()
    )
    species_conf_data = [
        {"name": r.common_name,
         "avg": round(float(r.avg or 0) * 100, 1),
         "max": round(float(r.max or 0) * 100, 1),
         "count": r.n}
        for r in species_conf
    ]

    # ── Fun & engagement stats ──────────────────────────────────────────────
    inat_submitted_count = (
        db.query(Recording)
        .filter(Recording.inat_observation_id.isnot(None))
        .count()
    )
    # Comments on a soft-deleted OR hard-deleted recording aren't
    # cascade-deleted (the Comment row survives either way), unlike every
    # other stat on this page which respects deleted_at — exclude those
    # for consistency. Requires `Recording.id.isnot(None)` (real proof a
    # matching row was found), not just `Recording.deleted_at.is_(None)` —
    # the outer join makes every Recording column NULL when there's no
    # matching row at all (hard delete), and `NULL IS NULL` is true, so a
    # check that only looked at deleted_at would silently miss the
    # hard-delete case (same bug, same fix, as get_recent_comments in
    # birds.py). Comments attached to a bird_profile_id (not a
    # recording_id) are unaffected, since profiles don't have the same
    # soft-delete concept.
    comment_count = (
        db.query(Comment)
        .outerjoin(Recording, Comment.recording_id == Recording.id)
        .filter(Comment.deleted_at.is_(None))
        .filter(or_(
            Comment.recording_id.is_(None),
            and_(Recording.id.isnot(None), Recording.deleted_at.is_(None)),
        ))
        .count()
    )
    commented_birds_count = (
        db.query(Comment.bird_profile_id)
        .filter(Comment.deleted_at.is_(None), Comment.bird_profile_id.isnot(None))
        .distinct().count()
    )
    photo_count = (
        db.query(BirdProfile)
        .filter(BirdProfile.photo_path.isnot(None))
        .count()
    )
    call_media_total = sum(
        len(p.call_media or []) for p in db.query(BirdProfile).filter(BirdProfile.call_media.isnot(None)).all()
    )

    # Rarest species detected (fewest total, excluding noise)
    rarest = (
        _base()
        .with_entities(Detection.common_name, _count_expr.label("n"))
        .group_by(Detection.common_name)
        .order_by(_count_expr.asc())
        .limit(5).all()
    )
    rarest_data = [{"name": r.common_name, "count": r.n} for r in rarest]

    # Busiest single day
    busiest_day_row = (
        _base()
        .with_entities(
            func.date(Recording.trigger_timestamp).label("d"),
            _count_expr.label("n"),
        )
        .filter(Recording.trigger_timestamp.isnot(None))
        .group_by("d").order_by(_count_expr.desc())
        .first()
    )
    busiest_day = (
        {"date": busiest_day_row.d, "count": busiest_day_row.n}
        if busiest_day_row else None
    )

    # Longest "new species" streak — most consecutive days with at least one new species
    streak_dates = sorted(new_species_by_date.keys()) if new_species_by_date else []
    longest_streak = 0
    if streak_dates:
        cur_streak = 1
        longest_streak = 1
        for i in range(1, len(streak_dates)):
            if (streak_dates[i] - streak_dates[i-1]).days == 1:
                cur_streak += 1
                longest_streak = max(longest_streak, cur_streak)
            else:
                cur_streak = 1

    fun_stats = {
        "inat_submitted_count":   inat_submitted_count,
        "comment_count":          comment_count,
        "commented_birds_count":  commented_birds_count,
        "photo_count":            photo_count,
        "call_media_total":       call_media_total,
        "rarest_species":         rarest_data,
        "busiest_day":            busiest_day,
        "longest_new_species_streak_days": longest_streak,
    }

    result = {
        "metric":             _metric,
        "total_species":      total_species,
        "top_species":        [{"name": s, "count": c} for s, c in top_species],
        "monthly":            monthly_data,
        "hourly":             hourly_data,
        "hourly_normalized":  hourly_data_normalized,
        "confidence":         conf_data,
        "species_by_month":   heatmap,
        "cumulative_species": cumulative,
        "seasonal":           seasonal_data,
        "day_of_week":        dow_data,
        "day_of_week_normalized": dow_data_normalized,
        "species_confidence": species_conf_data,
        "top10_names":        top10,
        "fun_stats":          fun_stats,
    }
    statistics_cache.set(cache_key, result)
    return result


_NOT_PROVIDED = object()  # sentinel — see _period_summary's app_settings param


def _period_summary(db: Session, since: datetime, bucket_fmt: str, bucket_count: int,
                     bucket_unit_delta: timedelta, app_settings=_NOT_PROVIDED) -> dict:
    """
    Shared computation for one period (today or this week) of the dashboard
    summary: most common bird (with profile details), total detections/
    recordings, a per-bucket breakdown (hourly for "today", daily for "this
    week"), and the rarest species detected within the period. Used twice
    by dashboard_summary() below — once for daily, once for weekly — with
    different `since`/bucket parameters.

    app_settings: pass the already-fetched AppSettings row to avoid querying
    the single-row settings table twice on every dashboard load (once per
    call from dashboard_summary, for identical id=1 data both times).
    Defaults to a sentinel rather than None — a database with genuinely no
    AppSettings row at all is a real, legal state (confirmed by testing it
    directly) and would mean the caller correctly passes app_settings=None;
    using plain None as the default made that case indistinguishable from
    "caller didn't pass anything," which silently defeated the whole
    optimization by re-querying anyway whenever the settings row didn't
    exist — caught by testing that exact edge case rather than assuming
    the fix worked.
    """
    from sqlalchemy import func, or_
    from datetime import datetime
    from ..models import AppSettings as _AS, BirdProfile as _BP

    _s = app_settings if app_settings is not _NOT_PROVIDED else db.query(_AS).filter(_AS.id == 1).first()
    _show_deleted = bool(getattr(_s, "show_deleted_detections", False)) if _s else False
    _min_conf = float(getattr(_s, "min_confidence_display", 0.0) or 0.0) if _s else 0.0

    rec_q = db.query(Recording).filter(Recording.trigger_timestamp >= since)
    if not _show_deleted:
        rec_q = rec_q.filter(Recording.deleted_at.is_(None))
    total_recordings = rec_q.count()

    det_q = (
        db.query(Detection)
        .join(Recording, Detection.recording_id == Recording.id)
        .filter(Recording.trigger_timestamp >= since)
    )
    if not _show_deleted:
        det_q = det_q.filter(Recording.deleted_at.is_(None))
    if _min_conf > 0:
        det_q = det_q.filter(Detection.confidence >= _min_conf)
    total_detections = det_q.count()

    # Species counts within the period, most → least common
    #
    # Groups by common_name ALONE, not also scientific_name — grouping by
    # both would break for any species whose detections have inconsistent
    # scientific_name values (happens for "Bat" — some detections have it
    # set, e.g. from a confident species-ID pass or older data, others
    # don't), producing multiple separate groups for what's actually one
    # species and showing up as duplicate tiles on the Dashboard's "Seen
    # Today" grid. scientific_name is still selected via func.max() (an
    # aggregate, so it's valid alongside a GROUP BY that doesn't include
    # it) to get a single representative value for display, rather than
    # as a bare non-aggregated column — same pattern get_life_list() uses.
    species_counts = (
        det_q.with_entities(
            Detection.common_name, func.max(Detection.scientific_name).label("scientific_name"),
            func.count(Detection.id).label("n"),
            func.avg(Detection.confidence).label("avg_conf"),
            func.max(Recording.is_bat).label("is_bat"),
        )
        .group_by(Detection.common_name)
        .order_by(func.count(Detection.id).desc())
        .all()
    )

    # Batch-fetch matching bird profiles for photo/id lookups (one query,
    # not one per species — same pattern used by recording_to_out()).
    #
    # Matches on BOTH common_name and label, not common_name alone — a
    # profile's common_name (the user-facing display name) can diverge
    # from its label (the stable, never-user-edited internal identifier).
    # This happened to the "Bat" profile: its common_name was changed
    # away from "Bat" while every actual bat Detection's common_name
    # stayed "Bat". Matching common_name alone silently misses the
    # profile entirely in that case, meaning no photo or profile link
    # ever shows
    # for that species again. profile_map is keyed by both fields so a
    # lookup by either succeeds.
    names_needed = {row.common_name for row in species_counts}
    profile_map = {}
    if names_needed:
        for p in db.query(_BP).filter(
            or_(_BP.common_name.in_(names_needed), _BP.label.in_(names_needed))
        ).all():
            profile_map[p.common_name] = p
            profile_map[p.label] = p

    # Per-species first-ever-detection timestamp (across ALL of that
    # species' detections, not just within this period) — needed to
    # honestly compute is_new below: a species only counts as new if its
    # first-ever detection at this location falls within this period's
    # window. Computed directly from the same Detection/Recording join
    # already in scope, batched in one query rather than once per species.
    # Deliberately does not call the separately-cached /life-list endpoint,
    # which exists for a different purpose with its own cache timing.
    first_detected_map = {}
    if names_needed:
        _first_q = (
            db.query(Detection.common_name, func.min(Recording.trigger_timestamp).label("first_dt"))
            .join(Recording, Detection.recording_id == Recording.id)
            .filter(Detection.common_name.in_(names_needed))
        )
        if not _show_deleted:
            _first_q = _first_q.filter(Recording.deleted_at.is_(None))
        for row in _first_q.group_by(Detection.common_name).all():
            first_detected_map[row.common_name] = row.first_dt

    def _bird_card(row):
        prof = profile_map.get(row.common_name)
        photo_url = None
        if prof:
            if prof.photo_path and os.path.exists(prof.photo_path):
                photo_url = f"/api/v1/birds/{prof.id}/photo"
            elif prof.photo_url:
                photo_url = prof.photo_url
        first_dt = first_detected_map.get(row.common_name)
        return {
            "common_name": row.common_name,
            "scientific_name": row.scientific_name,
            "count": row.n,
            "avg_confidence": round(float(row.avg_conf or 0), 3),
            "photo_url": photo_url,
            "bird_profile_id": prof.id if prof else None,
            "is_new": bool(first_dt and first_dt >= since),
            "is_bat": bool(row.is_bat),
        }

    # Full species list for the period (not just most-common + rarest-5),
    # needed for the Dashboard's species photo grid — sorted most-to-least
    # detections, same order as species_counts.
    species_today = [_bird_card(row) for row in species_counts]

    most_common_bird = _bird_card(species_counts[0]) if species_counts else None
    # Rarest = lowest detection counts within the period, excluding whichever
    # species is the most-common one. Exclude by slicing off index 0 first
    # (not just by name) — otherwise, when only a handful of species were
    # detected in the period, the bottom-5 slice can wrap around and include
    # the same species that's already shown as "most common" above.
    rarest_candidates = species_counts[1:]
    rarest_species = [_bird_card(row) for row in rarest_candidates[-5:][::-1]]

    # Per-bucket breakdown (hourly for daily, daily for weekly)
    bucket_rows = (
        rec_q.with_entities(
            func.strftime(bucket_fmt, Recording.trigger_timestamp).label("bucket"),
            func.count(Recording.id).label("n"),
        ).group_by("bucket").all()
    )
    recordings_by_bucket = {r.bucket: r.n for r in bucket_rows}

    det_bucket_rows = (
        det_q.with_entities(
            func.strftime(bucket_fmt, Recording.trigger_timestamp).label("bucket"),
            func.count(Detection.id).label("n"),
        ).group_by("bucket").all()
    )
    detections_by_bucket = {r.bucket: r.n for r in det_bucket_rows}

    # Build a complete, gap-filled bucket series from `since` to now, so the
    # chart always has the expected number of points (e.g. 24 hours) even
    # when some buckets had zero activity.
    buckets = []
    cursor = since
    now = datetime.utcnow()
    while cursor <= now and len(buckets) < bucket_count:
        key = cursor.strftime(bucket_fmt)
        buckets.append({
            "label": key,
            "detections": detections_by_bucket.get(key, 0),
            "recordings": recordings_by_bucket.get(key, 0),
        })
        cursor += bucket_unit_delta

    return {
        "total_detections": total_detections,
        "total_recordings": total_recordings,
        "most_common_bird": most_common_bird,
        "rarest_species": rarest_species,
        "species_today": species_today,
        "buckets": buckets,
    }


@router.get("/statistics/dashboard-summary")
def dashboard_summary(db: Session = Depends(get_db)):
    """
    Daily + weekly summary for the Dashboard: most common bird (with photo/
    confidence details), total detections and recordings, an activity
    breakdown (hourly for today, daily for this week), and the rarest
    species detected in each window. Both periods computed in one request
    so the Dashboard only needs a single fetch.
    """
    # Loads on every Dashboard visit and runs _period_summary() twice
    # (once for today, once for this week) — each of those already does
    # several aggregate queries of its own on top of that, and this
    # endpoint had no caching at all, the same gap yard_pulse() and
    # recording_stats() above were already fixed for. No parameters here
    # (unlike recording_stats' period), so a single canonical key covers
    # every request, same as yard_pulse's own "yard_pulse" key.
    from ..cache import statistics_cache
    _dash_cache_key = "dashboard_summary"
    _dash_cached = statistics_cache.get(_dash_cache_key)
    if _dash_cached is not None:
        return _dash_cached

    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    # "Today" must mean the calendar day in the server's configured local
    # timezone, not midnight UTC. Recording.trigger_timestamp is stored as
    # naive UTC (see upload_recording()'s timestamp normalization), so the
    # fix is: get local midnight in the configured tz, then convert that
    # boundary back to naive UTC for the query — not the other way around.
    # Same zoneinfo pattern already used a few hundred lines up in this
    # file for hour-of-day bucketing; previously this endpoint used
    # datetime.utcnow().replace(hour=0,...) directly, which is midnight UTC
    # and for any timezone west of UTC (e.g. America/New_York) silently
    # shifted "today" to start several hours into the previous evening.
    # Single fetch reused for the timezone lookup below AND passed into
    # both _period_summary calls — this endpoint was previously querying
    # the same single-row id=1 settings record three separate times on
    # every dashboard load (once here, once inside each of the two
    # _period_summary calls) for the exact same data.
    _app_settings = db.query(AppSettings).filter(AppSettings.id == 1).first()
    _tz_name = (_app_settings.timezone if _app_settings else None) or "UTC"
    try:
        _tz = ZoneInfo(_tz_name)
    except Exception:
        _tz = ZoneInfo("UTC")

    now_local = datetime.now(ZoneInfo("UTC")).astimezone(_tz)
    today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start = today_start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    week_start = today_start - timedelta(days=6)   # last 7 days inclusive of today

    daily = _period_summary(db, today_start, "%Y-%m-%dT%H:00", 24, timedelta(hours=1), app_settings=_app_settings)
    weekly = _period_summary(db, week_start, "%Y-%m-%d", 7, timedelta(days=1), app_settings=_app_settings)

    result = {"daily": daily, "weekly": weekly}
    statistics_cache.set(_dash_cache_key, result)
    return result


@router.get("/statistics/digest")
def get_day_digest(date: Optional[str] = None, db: Session = Depends(get_db)):
    """One day's digest for the app's digest page (default yesterday, in
    the site's time zone; today shows the day so far): the
    same numbers as the email and push digest (compute_day_stats), plus
    activity by hour and each species' photo, first time heard and best
    recording."""
    from datetime import date as _date, timezone as _tz
    from ..models import BirdProfile
    from ..services.email_service import compute_day_stats, _hour_label, site_today
    try:
        day = _date.fromisoformat(date) if date else site_today(db) - timedelta(days=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    base = {"date": day.isoformat(), "day": day.strftime("%A, %B %-d, %Y"),
            "partial": day >= site_today(db)}
    st = compute_day_stats(db, day)
    if st is None:
        return {**base, "quiet": True}
    names = list(st["species_counts"])
    profiles = {p.common_name: p for p in db.query(BirdProfile).filter(BirdProfile.common_name.in_(names)).all()}
    tz = st["tz"]

    def local(t):
        if t is None:
            return None
        if tz is not None:
            t = t.replace(tzinfo=_tz.utc).astimezone(tz)
        return t.strftime("%-I:%M %p")

    new = set(st["new_species"])
    species = []
    for name, count in st["species_counts"].most_common():
        p = profiles.get(name)
        photo = None
        if p is not None:
            if p.photo_path and os.path.exists(p.photo_path):
                photo = f"/api/v1/birds/{p.id}/photo"
            elif p.photo_url:
                photo = p.photo_url
        species.append({
            "name": name, "count": count, "new": name in new,
            "scientific": st["scientific"].get(name),
            "best": round(st["best_conf"].get(name, 0), 2),
            "first_heard": local(st["first_heard"].get(name)),
            "profile_id": p.id if p else None, "photo_url": photo,
            "best_recording_id": st["best_rec"].get(name),
        })
    return {
        **base, "quiet": False,
        "recordings": st["total_recs"], "detections": st["total_dets"],
        "species_count": st["unique_species"], "new_species": st["new_species"],
        "busiest_hour": _hour_label(st["busiest_hour"]) if st["busiest_hour"] is not None else None,
        "hours": [st["hours"].get(h, 0) for h in range(24)],
        "species": species,
    }


@router.get("/statistics/daily-journal")
def get_daily_journal(db: Session = Depends(get_db)):
    """
    Cached AI-written daily summary — see services/daily_summary.py for
    the full generation logic. Returns whatever's currently cached
    (generated on schedule, or via the manual regenerate endpoint below);
    this endpoint itself never triggers generation, it's a pure read.
    `enabled` reflects whether the feature has a provider assigned at all
    — the frontend uses this to decide whether to render the card,
    independent of whether a summary happens to exist yet.
    """
    from ..models import AppSettings
    from ..services.ai_providers import get_feature_config
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    enabled = get_feature_config("daily_summary", db) is not None
    return {
        "enabled": enabled,
        "text": s.daily_summary_text if s else None,
        "generated_at": s.daily_summary_generated_at.isoformat() if s and s.daily_summary_generated_at else None,
        "error": s.daily_summary_error if s else None,
    }


@router.post("/statistics/daily-journal/regenerate")
def regenerate_daily_journal(db: Session = Depends(get_db)):
    """Manual regenerate — the escape hatch alongside the scheduled run."""
    from ..services.daily_summary import generate_daily_summary
    generate_daily_summary(db)
    return get_daily_journal(db)


@router.get("/statistics/weekly-journal")
def get_weekly_journal(db: Session = Depends(get_db)):
    """
    Cached AI-written weekly summary — see services/weekly_summary.py.
    Same read-only/scheduled-or-manual-generation contract as
    get_daily_journal above, plus the actual date range this entry
    covers (period_start/period_end), since "Weekly Journal" needs a
    real range shown, not an assumed one.
    """
    from ..models import AppSettings
    from ..services.ai_providers import get_feature_config
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    enabled = get_feature_config("weekly_summary", db) is not None
    return {
        "enabled": enabled,
        "text": s.weekly_summary_text if s else None,
        "generated_at": s.weekly_summary_generated_at.isoformat() if s and s.weekly_summary_generated_at else None,
        "period_start": s.weekly_summary_period_start.isoformat() if s and s.weekly_summary_period_start else None,
        "period_end": s.weekly_summary_period_end.isoformat() if s and s.weekly_summary_period_end else None,
        "error": s.weekly_summary_error if s else None,
    }


@router.post("/statistics/weekly-journal/regenerate")
def regenerate_weekly_journal(db: Session = Depends(get_db)):
    """Manual regenerate — the escape hatch alongside the scheduled run."""
    from ..services.weekly_summary import generate_weekly_summary
    generate_weekly_summary(db)
    return get_weekly_journal(db)


def _species_local_dates(db, base_filters, min_conf, tz, since=None) -> dict:
    """{species: set of local calendar dates it was detected on}, for the
    streak endpoints. On SQLite the database groups detections by
    (species, UTC hour) first, which turns hundreds of thousands of rows
    into a few thousand; each hour maps to exactly one local date as long
    as the site's UTC offset is whole hours (true almost everywhere).
    Otherwise it reads every row, as before."""
    from datetime import timedelta as _td
    from zoneinfo import ZoneInfo
    from sqlalchemy import func
    utc = ZoneInfo("UTC")
    now = datetime.utcnow().replace(tzinfo=utc)
    whole_hours = all((tz.utcoffset(now + _td(days=d)) or _td(0)).total_seconds() % 3600 == 0
                      for d in (0, 91, 182, 273))
    try:
        sqlite = db.get_bind().dialect.name == "sqlite"
    except Exception:
        sqlite = False
    out: dict = {}
    if sqlite and whole_hours:
        bucket = func.strftime("%Y-%m-%d %H", Recording.trigger_timestamp)
        q = (db.query(Detection.common_name, bucket)
             .join(Recording, Detection.recording_id == Recording.id)
             .filter(*base_filters))
        if since is not None:
            q = q.filter(Recording.trigger_timestamp >= since)
        if min_conf > 0:
            q = q.filter(Detection.confidence >= min_conf)
        for name, b in q.group_by(Detection.common_name, bucket).all():
            if not b:
                continue
            local = datetime.strptime(b, "%Y-%m-%d %H").replace(tzinfo=utc).astimezone(tz).date()
            out.setdefault(name, set()).add(local)
        return out
    q = (db.query(Detection.common_name, Recording.trigger_timestamp)
         .join(Recording, Detection.recording_id == Recording.id)
         .filter(*base_filters))
    if since is not None:
        q = q.filter(Recording.trigger_timestamp >= since)
    if min_conf > 0:
        q = q.filter(Detection.confidence >= min_conf)
    for name, ts in q.all():
        if ts is None:
            continue
        out.setdefault(name, set()).add(ts.replace(tzinfo=utc).astimezone(tz).date())
    return out


@router.get("/statistics/yard-pulse")
def yard_pulse(db: Session = Depends(get_db)):
    """
    Two Dashboard highlights distinct from the day/week summary above:

    1. Species streaks — for each species, the current run of consecutive
       calendar days (ending today or yesterday — a streak isn't "broken"
       until a full day passes with zero detections) with at least one
       detection. Top 5 by streak length. Genuinely different from a
       generic "days you opened the app" streak — this is about which
       birds have been reliably present, which is actually interesting
       content for a birder rather than an app-engagement gimmick.

    2. 30-day diversity — distinct species in the last 30 days vs. the
       previous 30 days (a rolling window, not calendar-month — see the
       comment further down for why), plus a Shannon evenness score
       (H / ln(S), a standard ecological evenness measure — how evenly
       detections are spread across species rather than dominated by one
       or two) shown as a 0-100 gauge. Deliberately called "diversity",
       not "yard health" — this measures the evenness of what got
       detected and recorded, which is a real, defensible number; it is
       not a claim about actual ecosystem health, which acoustic
       detection data alone can't support.
    """
    from datetime import datetime, timedelta as _td
    from zoneinfo import ZoneInfo
    from sqlalchemy import func
    from ..models import AppSettings as _AS, BirdProfile as _BP
    import math

    from ..cache import slow_stats_cache as statistics_cache
    _yp_cache_key = "yard_pulse"
    _yp_cached = statistics_cache.get(_yp_cache_key)
    if _yp_cached is not None:
        return _yp_cached

    _s = db.query(_AS).filter(_AS.id == 1).first()
    _show_deleted = bool(getattr(_s, "show_deleted_detections", False)) if _s else False
    _min_conf = float(getattr(_s, "min_confidence_display", 0.0) or 0.0) if _s else 0.0
    _tz_name = (_s.timezone if _s else None) or "UTC"
    try:
        _tz = ZoneInfo(_tz_name)
    except Exception:
        _tz = ZoneInfo("UTC")

    now_local = datetime.now(ZoneInfo("UTC")).astimezone(_tz)
    today_local = now_local.date()

    base_filters = [Recording.is_bat.is_(False)]
    if not _show_deleted:
        base_filters.append(Recording.deleted_at.is_(None))
    base_filters.append(Recording.haikubox_detection_id.is_(None))

    # ── 1. Species streaks ──────────────────────────────────────────────
    # Bounded to the last 120 days (a generous cap — nothing realistic
    # streaks past that, and it keeps this query cheap regardless of how
    # much history the DB holds) — pulled as (species, local calendar
    # date) pairs, then streak-walked in Python. Computing "current streak
    # per species" set-wise in pure SQL across arbitrary date gaps is
    # awkward across SQLite/Postgres alike; this is a few hundred rows at
    # most, trivial to walk in-process.
    window_start = datetime.combine(today_local - _td(days=120), datetime.min.time())
    # Local dates (not UTC), matching how "today" is defined everywhere else
    # on this dashboard, so a detection at 11pm local isn't counted as tomorrow.
    species_dates = _species_local_dates(db, base_filters, _min_conf, _tz, since=window_start)

    streaks = []
    for common_name, dates in species_dates.items():
        # Streak must include today or yesterday to still be "current" —
        # a species not heard in 3 days doesn't have an active streak,
        # even if it had a long one recently.
        if today_local not in dates and (today_local - _td(days=1)) not in dates:
            continue
        cursor = today_local if today_local in dates else today_local - _td(days=1)
        count = 0
        while cursor in dates:
            count += 1
            cursor -= _td(days=1)
        streaks.append({"common_name": common_name, "streak_days": count})

    streaks.sort(key=lambda x: x["streak_days"], reverse=True)
    top_streaks = streaks[:5]

    # Attach profile photo/scientific name — batched, not per-row
    streak_names = [s["common_name"] for s in top_streaks]
    profile_map = {
        p.common_name: p
        for p in db.query(_BP).filter(_BP.common_name.in_(streak_names)).all()
    } if streak_names else {}
    for s in top_streaks:
        p = profile_map.get(s["common_name"])
        s["scientific_name"] = p.scientific_name if p else None
        s["photo_url"] = p.photo_url if p else None
        s["profile_id"] = p.id if p else None

    # ── 2. Monthly diversity ─────────────────────────────────────────────
    # ── 2. 30-day rolling diversity ──────────────────────────────────────
    # Deliberately a ROLLING 30-day window (today back 29 days, vs. the
    # 30 days before that), not calendar-month — a Dashboard "how's my
    # yard doing lately" figure should update smoothly every day rather
    # than jumping/resetting on the 1st and reading as a near-empty
    # "1 day into this month" figure for the first few days of every
    # month. The Statistics page's separate Diversity Trend chart still
    # reports genuine calendar months, for a different purpose — a
    # month-by-month history to look back over, where calendar
    # boundaries are the right unit.
    window_end_excl = today_local + _td(days=1)
    window_start = today_local - _td(days=29)      # 30 days total, inclusive of today
    prev_window_end_excl = window_start
    prev_window_start = window_start - _td(days=30)

    def _window_bounds_utc(start_date, end_date_exclusive):
        return (
            datetime.combine(start_date, datetime.min.time()),
            datetime.combine(end_date_exclusive, datetime.min.time()),
        )

    this_start, this_end = _window_bounds_utc(window_start, window_end_excl)
    last_start, last_end = _window_bounds_utc(prev_window_start, prev_window_end_excl)

    def _species_counts(start, end):
        qq = (
            db.query(Detection.common_name, func.count(Detection.id))
            .join(Recording, Detection.recording_id == Recording.id)
            .filter(*base_filters)
            .filter(Recording.trigger_timestamp >= start, Recording.trigger_timestamp < end)
        )
        if _min_conf > 0:
            qq = qq.filter(Detection.confidence >= _min_conf)
        qq = qq.group_by(Detection.common_name)
        return {name: cnt for name, cnt in qq.all()}

    last_30d_counts = _species_counts(this_start, this_end)
    prev_30d_counts = _species_counts(last_start, last_end)

    species_last_30d = len(last_30d_counts)
    species_prev_30d = len(prev_30d_counts)

    total = sum(last_30d_counts.values())
    shannon = 0.0
    if total > 0 and species_last_30d > 0:
        for cnt in last_30d_counts.values():
            p = cnt / total
            if p > 0:
                shannon -= p * math.log(p)
    shannon = round(shannon, 2)

    # Shannon diversity index (H) — a standard ecological measure of how
    # many species were detected AND how evenly detections are spread
    # across them (a month with 20 species but one bird dominating 90% of
    # detections scores much lower than 20 species detected roughly
    # equally often). Real bird-community H values for actual sites
    # typically land in the 1-4 range; going higher requires both a large
    # species count AND very even representation among all of them, which
    # is genuinely rare — these bands match how the metric is actually
    # used in ecological literature, not an arbitrary scale invented for
    # this feature.
    if species_last_30d == 0:
        diversity_label = "No data yet"
        diversity_description = "Detect a few different species in the last 30 days to see a diversity score."
    elif shannon < 1.0:
        diversity_label = "Low diversity"
        diversity_description = "A small number of species, or one or two dominating most detections."
    elif shannon < 2.0:
        diversity_label = "Moderate diversity"
        diversity_description = "A reasonable species mix, though a few species are detected far more than others."
    elif shannon < 3.0:
        diversity_label = "High diversity"
        diversity_description = "A healthy variety of species, detected fairly evenly — typical of an active, diverse yard."
    elif shannon < 4.0:
        diversity_label = "Very high diversity"
        diversity_description = "A large number of species detected with unusually even representation — an excellent stretch."
    else:
        diversity_label = "Exceptional diversity"
        diversity_description = "Rare — this needs both a large species count and very even detection frequency across all of them. Top tier for a single location."

    # ── Simpson's diversity index (1-D, "Gini-Simpson") ──────────────────
    # A second, differently-behaved diversity measure alongside Shannon's
    # H: the probability that two randomly chosen detections in the last
    # 30 days are different species. Bounded 0-1 by construction (no
    # precision mismatch possible across different roundings, unlike a
    # cross-window percentile comparison would risk). Simpson's weights
    # the most common species more heavily than Shannon's does, and is
    # less sensitive to rare/one-off species — the two together give a
    # fuller picture than either alone.
    simpson = None
    simpson_label = None
    simpson_description = None
    if total > 0 and species_last_30d > 0:
        simpson_sum = sum((cnt / total) ** 2 for cnt in last_30d_counts.values())
        simpson = round(1 - simpson_sum, 3)
        # Bounded 0-1 by construction — bands are simpler than Shannon's
        # since there's no open-ended top end to describe. Labels are
        # phrased around "evenness/dominance" rather than reusing
        # Shannon's "diversity" wording — both are real, distinct ways
        # Simpson's is actually described in the literature, and it
        # avoids the two gauges saying the literal same words for
        # different numbers, which read as redundant/confusing side by
        # side on the same card.
        if simpson < 0.5:
            simpson_label = "Mostly one species"
            simpson_description = "One or two species make up most of what you hear."
        elif simpson < 0.7:
            simpson_label = "A few stand out"
            simpson_description = "Some species are heard a lot more than others."
        elif simpson < 0.85:
            simpson_label = "Nicely balanced"
            simpson_description = "Most species are heard about equally often."
        else:
            simpson_label = "Very balanced"
            simpson_description = "Practically every species is heard equally often."

    _yp_result = {
        "streaks": top_streaks,
        "diversity": {
            "species_last_30d": species_last_30d,
            "species_prev_30d": species_prev_30d,
            "shannon_index": shannon,
            "simpson_index": simpson,
            "simpson_label": simpson_label,
            "simpson_description": simpson_description,
            "label": diversity_label,
            "description": diversity_description,
        },
    }
    statistics_cache.set(_yp_cache_key, _yp_result)
    return _yp_result


@router.get("/statistics/diversity-trend")
def diversity_trend(
    window: str = Query("12", description="'12', '24', '36', or 'all' — how many trailing calendar months to return"),
    db: Session = Depends(get_db),
):
    """
    Calendar-month species richness plus three standard diversity
    indices, each on its own natural scale rather than forced onto a
    shared axis (they measure different things and have genuinely
    different ranges):

    - Species richness (S): raw count, no theoretical ceiling.
    - Shannon index (H'): richness weighted by evenness. Real bird-
      community values typically run 1.5-3.5, rarely above 4 (matches
      the same bands used on the Dashboard's own 30-day Yard Diversity
      card — that card and this chart intentionally use DIFFERENT
      windows: a rolling 30 days there, real calendar months here. The
      Dashboard wants a smoothly-updating "how's it going lately"
      figure that doesn't jump on the 1st of the month; this chart
      wants a real month-by-month history to browse back through, where
      calendar boundaries are the meaningful unit).
    - Simpson's index (as 1-D, "Gini-Simpson"): probability two randomly
      chosen detections are different species. Bounded 0-1 by
      construction; puts more weight on the most common species than
      Shannon does, less sensitive to rare ones.
    - Pielou's evenness (J' = H'/ln(S)): the evenness component of
      Shannon on its own, independent of richness. Bounded 0-1; a low
      value with high richness means many species but one or two
      dominating detections.

    `window` controls how far back: '12'/'24'/'36' trailing months, or
    'all' for every month since the first recording. Every month except
    the current (still-accumulating) one is cached in
    MonthlyDiversityStats — see that model's own docstring for why —
    so 'all' costs a real Detection-table scan only for months that
    have never been requested by anyone before; every month after that,
    on any request, is a cheap primary-key read.
    """
    from datetime import datetime, timedelta as _td
    from zoneinfo import ZoneInfo
    from sqlalchemy import func
    from ..models import AppSettings as _AS, MonthlyDiversityStats as _MDS
    import math

    _s = db.query(_AS).filter(_AS.id == 1).first()
    _show_deleted = bool(getattr(_s, "show_deleted_detections", False)) if _s else False
    _min_conf = float(getattr(_s, "min_confidence_display", 0.0) or 0.0) if _s else 0.0
    _tz_name = (_s.timezone if _s else None) or "UTC"
    try:
        _tz = ZoneInfo(_tz_name)
    except Exception:
        _tz = ZoneInfo("UTC")

    now_local = datetime.now(ZoneInfo("UTC")).astimezone(_tz)
    today_local = now_local.date()

    base_filters = [Recording.is_bat.is_(False)]
    if not _show_deleted:
        base_filters.append(Recording.deleted_at.is_(None))
    base_filters.append(Recording.haikubox_detection_id.is_(None))

    def _species_counts(start, end):
        qq = (
            db.query(Detection.common_name, func.count(Detection.id))
            .join(Recording, Detection.recording_id == Recording.id)
            .filter(*base_filters)
            .filter(Recording.trigger_timestamp >= start, Recording.trigger_timestamp < end)
        )
        if _min_conf > 0:
            qq = qq.filter(Detection.confidence >= _min_conf)
        qq = qq.group_by(Detection.common_name)
        return {name: cnt for name, cnt in qq.all()}

    this_month_start = today_local.replace(day=1)

    if window == "all":
        # Earliest month with any qualifying recording — a plain MIN()
        # is cheap (single indexed scan), unlike computing every
        # candidate month just to find out which ones are empty.
        earliest = (
            db.query(func.min(Recording.trigger_timestamp))
            .filter(*base_filters)
            .scalar()
        )
        if earliest is None:
            months = [this_month_start]
        else:
            earliest_local = earliest.astimezone(_tz) if earliest.tzinfo else earliest.replace(tzinfo=ZoneInfo("UTC")).astimezone(_tz)
            cursor = this_month_start
            months = []
            floor_month = earliest_local.date().replace(day=1)
            while cursor >= floor_month:
                months.append(cursor)
                cursor = (cursor - _td(days=1)).replace(day=1)
            months.reverse()
    else:
        try:
            n_months = max(1, min(int(window), 600))  # hard ceiling — sane guard against a malformed/huge param, not a real expected case
        except ValueError:
            n_months = 12
        cursor = this_month_start
        months = []
        for _ in range(n_months):
            months.append(cursor)
            cursor = (cursor - _td(days=1)).replace(day=1)
        months.reverse()

    # Pull every already-cached month in this range in ONE query, rather
    # than one SELECT per month — the whole point of caching is to avoid
    # per-month DB round-trips piling back up.
    month_keys = [m.strftime("%Y-%m") for m in months]
    cached_rows = {
        row.month: row
        for row in db.query(_MDS).filter(_MDS.month.in_(month_keys)).all()
    }

    results = []
    newly_computed = []  # rows to persist, batched into one commit at the end
    for i, m_start in enumerate(months):
        m_key = m_start.strftime("%Y-%m")
        is_current_month = (i == len(months) - 1) and (m_start == this_month_start)

        if not is_current_month and m_key in cached_rows:
            row = cached_rows[m_key]
            results.append({
                "month": m_key,
                "species_richness": row.species_richness,
                "shannon_index": row.shannon_index,
                "simpson_index": row.simpson_index,
                "evenness": row.evenness,
            })
            continue

        if i + 1 < len(months):
            m_end = months[i + 1]
        elif is_current_month:
            m_end = today_local + _td(days=1)  # current month runs through "now", not to month-end
        else:
            m_end = (m_start.replace(day=28) + _td(days=4)).replace(day=1)

        start_dt = datetime.combine(m_start, datetime.min.time())
        end_dt = datetime.combine(m_end, datetime.min.time())
        counts = _species_counts(start_dt, end_dt)

        s = len(counts)
        total = sum(counts.values())
        shannon = 0.0
        simpson_sum = 0.0
        if total > 0 and s > 0:
            for cnt in counts.values():
                p = cnt / total
                if p > 0:
                    shannon -= p * math.log(p)
                simpson_sum += p * p
        simpson = round(1 - simpson_sum, 3) if total > 0 else None
        shannon = round(shannon, 2) if total > 0 else None
        evenness = round(shannon / math.log(s), 3) if (shannon is not None and s > 1) else (1.0 if s == 1 else None)

        results.append({
            "month": m_key,
            "species_richness": s,
            "shannon_index": shannon,
            "simpson_index": simpson,
            "evenness": evenness,
        })

        # Never persist the current month — it's still accumulating
        # detections and today's own numbers would go stale the moment
        # tomorrow's first detection arrives.
        if not is_current_month:
            newly_computed.append(_MDS(
                month=m_key, species_richness=s, total_detections=total,
                shannon_index=shannon, simpson_index=simpson, evenness=evenness,
            ))

    if newly_computed:
        for row in newly_computed:
            db.merge(row)  # merge, not add — guards against a rare concurrent-request race double-inserting the same month
        db.commit()

    return {"months": results, "window": window}


@router.get("/statistics/species-streaks")
def species_streaks(db: Session = Depends(get_db)):
    """
    Per-species streaks for the Statistics page — two different things,
    not to be confused:

    - Active: same "current, unbroken run ending today/yesterday" logic
      as the Dashboard's Yard Pulse, capped to the last 120 days (a
      streak realistically never runs longer than that, and it keeps the
      query cheap — same reasoning as yard_pulse).
    - Lifetime longest: the longest run any species has EVER had, scanned
      across full history (no 120-day cap — a genuine lifetime record
      could be older than that window, and this endpoint is a one-time
      page load rather than something polled frequently like yard_pulse).
      Independent of whether that streak is still active today.
    """
    from datetime import datetime, timedelta as _td
    from zoneinfo import ZoneInfo
    from ..models import AppSettings as _AS, BirdProfile as _BP

    _s = db.query(_AS).filter(_AS.id == 1).first()
    _show_deleted = bool(getattr(_s, "show_deleted_detections", False)) if _s else False
    _min_conf = float(getattr(_s, "min_confidence_display", 0.0) or 0.0) if _s else 0.0
    _tz_name = (_s.timezone if _s else None) or "UTC"
    try:
        _tz = ZoneInfo(_tz_name)
    except Exception:
        _tz = ZoneInfo("UTC")

    today_local = datetime.now(ZoneInfo("UTC")).astimezone(_tz).date()

    base_filters = [Recording.is_bat.is_(False)]
    if not _show_deleted:
        base_filters.append(Recording.deleted_at.is_(None))
    base_filters.append(Recording.haikubox_detection_id.is_(None))

    def _longest_run(dates: set) -> int:
        best = cur = 0
        prev = None
        for d in sorted(dates):
            if prev is not None and (d - prev).days == 1:
                cur += 1
            else:
                cur = 1
            best = max(best, cur)
            prev = d
        return best

    from ..cache import slow_stats_cache as statistics_cache
    _cached = statistics_cache.get("species_streaks")
    if _cached is not None:
        return _cached

    # One pass over full history; active streaks only look back from today.
    all_dates = _species_local_dates(db, base_filters, _min_conf, _tz)
    active = []
    for common_name, dates in all_dates.items():
        if today_local not in dates and (today_local - _td(days=1)) not in dates:
            continue
        cursor = today_local if today_local in dates else today_local - _td(days=1)
        count = 0
        while cursor in dates:
            count += 1
            cursor -= _td(days=1)
        active.append({"common_name": common_name, "streak_days": count})
    active.sort(key=lambda x: x["streak_days"], reverse=True)
    active = active[:10]

    # Lifetime longest — full history, no window cap
    lifetime = [
        {"common_name": name, "streak_days": _longest_run(dates)}
        for name, dates in all_dates.items()
    ]
    lifetime.sort(key=lambda x: x["streak_days"], reverse=True)
    lifetime = [x for x in lifetime if x["streak_days"] > 0][:10]

    # Attach profile photo/scientific name — batched
    all_names = list({x["common_name"] for x in active + lifetime})
    profile_map = {
        p.common_name: p
        for p in db.query(_BP).filter(_BP.common_name.in_(all_names)).all()
    } if all_names else {}
    for x in active + lifetime:
        p = profile_map.get(x["common_name"])
        x["scientific_name"] = p.scientific_name if p else None
        x["photo_url"] = p.photo_url if p else None
        x["profile_id"] = p.id if p else None

    result = {"active": active, "lifetime": lifetime}
    statistics_cache.set("species_streaks", result)
    return result


@router.get("/statistics/bat-activity")
def bat_activity_statistics(nights: int = Query(30, ge=1, le=180), db: Session = Depends(get_db)):
    """
    Bat-specific statistics for the Statistics page — nightly activity,
    hour-of-night distribution, peak-frequency spread, and species
    breakdown where classification has actually asserted one. Everything
    here is scoped to Recording.is_bat rows only, separate from the
    bird-detection queries the rest of this file's stats endpoints use.
    """
    from datetime import timedelta as _td
    from zoneinfo import ZoneInfo

    since = datetime.utcnow() - _td(days=nights)
    base_q = db.query(Recording).filter(
        Recording.is_bat.is_(True),
        Recording.deleted_at.is_(None),
        Recording.trigger_timestamp >= since,
    )
    recordings = base_q.all()

    total = len(recordings)
    interference_flagged = sum(1 for r in recordings if (r.bat_metadata or {}).get("likely_interference"))
    confirmed = total - interference_flagged

    # Recording.trigger_timestamp is stored as naive UTC throughout this
    # codebase (see upload_recording()'s timestamp normalization). Both
    # groupings below need the configured LOCAL timezone, not raw UTC —
    # this endpoint previously used the UTC timestamp directly for both,
    # which is exactly why "by hour of night" showed a hard peak at
    # 0:00-2:00 with total silence from 9am-9pm: real dusk-emergence
    # activity around 8-10pm EDT was being labeled with its UTC hour
    # (00:00-02:00) instead of its local one. Same zoneinfo/offset
    # pattern already used a few hundred lines up in this file for the
    # bird-detection hour-of-day chart — this bat endpoint was simply
    # never updated to match when that fix was made there.
    _tz_name = (db.query(AppSettings).filter(AppSettings.id == 1).first() or AppSettings()).timezone or "UTC"
    try:
        _tz = ZoneInfo(_tz_name)
    except Exception:
        _tz = ZoneInfo("UTC")
    _offset_h = int(datetime.now(ZoneInfo("UTC")).astimezone(_tz).utcoffset().total_seconds() // 3600)

    # By night — local calendar date, not the UTC one. A bat recorded at
    # 2am UTC is 10pm the PREVIOUS evening in America/New_York — bucketing
    # by the raw UTC date would silently shift it into the wrong night.
    by_night: dict = {}
    for r in recordings:
        local_ts = r.trigger_timestamp.replace(tzinfo=ZoneInfo("UTC")).astimezone(_tz)
        day_key = local_ts.strftime("%Y-%m-%d")
        by_night[day_key] = by_night.get(day_key, 0) + 1
    by_night_list = [{"date": k, "count": v} for k, v in sorted(by_night.items())]

    # By hour of night — shift each UTC hour to local, same wraparound
    # approach as the bird-detection hourly chart (an hour-only shift is
    # sufficient here, unlike by_night above, since a 24-bucket
    # wraparound is exactly what "hour of day" already means regardless
    # of which calendar date it falls on).
    by_hour = [0] * 24
    for r in recordings:
        h_local = (r.trigger_timestamp.hour + _offset_h) % 24
        by_hour[h_local] += 1

    # Peak frequency spread — gives a sense of species mix even with
    # classification off, since different bat families cluster in
    # characteristic frequency bands
    freqs = [(r.bat_metadata or {}).get("peak_freq_hz") for r in recordings]
    freqs = [f for f in freqs if f]
    freq_buckets = {"15-25kHz": 0, "25-40kHz": 0, "40-60kHz": 0, "60-90kHz": 0, "90kHz+": 0}
    for f in freqs:
        if f < 25000:
            freq_buckets["15-25kHz"] += 1
        elif f < 40000:
            freq_buckets["25-40kHz"] += 1
        elif f < 60000:
            freq_buckets["40-60kHz"] += 1
        elif f < 90000:
            freq_buckets["60-90kHz"] += 1
        else:
            freq_buckets["90kHz+"] += 1

    # Species breakdown — only counts recordings where classification
    # actually asserted a species. There's no distinct source marker for
    # this: _process_bat_recording_bg updates the SAME Detection row's
    # common_name in place once confident, from the generic "Bat" default
    # every bat recording starts with — so "still Bat" means unclassified
    # or not confident enough, not "no bat here."
    species_counts: dict = {}
    for r in recordings:
        for d in r.detections:
            if d.common_name and d.common_name != "Bat":
                species_counts[d.common_name] = species_counts.get(d.common_name, 0) + 1
    species_breakdown = sorted(
        [{"common_name": k, "count": v} for k, v in species_counts.items()],
        key=lambda x: -x["count"],
    )[:10]

    return {
        "total": total,
        "confirmed": confirmed,
        "interference_flagged": interference_flagged,
        "by_night": by_night_list,
        "by_hour": by_hour,
        "peak_freq_buckets": freq_buckets,
        "species_breakdown": species_breakdown,
        "nights_window": nights,
    }
