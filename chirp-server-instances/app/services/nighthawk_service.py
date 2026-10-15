"""
Nighthawk night flight calls (Settings → Experimental).

Stations upload night audio between exp_nighthawk_start and _end (device
1.4.0+, chirp/night_audio.py): 10-minute 22.05 kHz FLAC chunks. Each chunk
becomes a NightChunk; Nighthawk (Van Doren et al. 2023, CC BY-NC 4.0)
scores it and every call it finds becomes a FlightCall with a 3-second clip.
The chunk's audio is deleted afterwards.

Nighthawk names a species only when confident; otherwise it gives a sound
group (calls that sound alike, e.g. ZEEP), a family or an order. FlightCall
keeps the most specific one (`level`, `category`).

Nighthawk's own package pins Python 3.10 and TensorFlow 2.12; it is
installed with --no-deps and runs unchanged on the server's 3.11/2.21
(checked detection for detection against the official build).

Chunks are processed one at a time per server process (TensorFlow uses all
cores for each). On 2 CPU cores a 10-minute chunk takes about 3 minutes.
"""
import csv
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("chirp.nighthawk")

_lock = threading.Lock()          # one chunk at a time
_model = None
_tax = None
CLIP_PAD = 1.0                    # seconds kept either side of a call
KEEP_FAILED_HOURS = 48            # failed chunks are retried, then removed


def audio_dir() -> Path:
    from ..config import settings
    d = Path(settings.data_dir) / "night_audio"
    d.mkdir(parents=True, exist_ok=True)
    return d


def clips_dir() -> Path:
    from ..config import settings
    d = Path(settings.data_dir) / "night_calls"
    d.mkdir(parents=True, exist_ok=True)
    return d


def available() -> Optional[str]:
    """None when Nighthawk can run here, otherwise why not."""
    try:
        import nighthawk.detector  # noqa: F401
        import pandas  # noqa: F401
        return None
    except Exception as e:
        return f"Nighthawk isn't installed on this server ({e.__class__.__name__})"


def taxonomy() -> dict:
    """eBird code → (common name, scientific name, family), plus group
    members, from Nighthawk's bundled taxonomy."""
    global _tax
    if _tax is None:
        import nighthawk.detector as nd
        base = Path(nd.__file__).parent / "taxonomy"
        species, families = {}, {}
        with open(base / "ebird_taxonomy.csv", newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                species[r["code"]] = (r["name"], r["sci_name"], r["family"])
                fam, _, common = r["family"].partition(" (")   # "Parulidae (New World Warblers)"
                if common:
                    families.setdefault(fam, common.rstrip(")"))
        groups = {}
        with open(base / "groups_ebird_codes.csv", newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                groups.setdefault(r["group"], []).append(species.get(r["ebird_code"], (r["ebird_code"],))[0])
        _tax = {"species": species, "groups": groups, "families": families}
    return _tax


def display_name(level: str, category: str, common: Optional[str] = None,
                 family: Optional[str] = None, order: Optional[str] = None) -> str:
    """Species: common name; group: "ZEEP group"; family: its English name
    ("New World Warblers"); order: the order."""
    if common:
        return common
    if level == "group":
        return f"{category} group"
    if level == "family":
        fam = family or category
        try:
            return taxonomy()["families"].get(fam, fam)
        except Exception:
            return fam
    if level == "order":
        return order or category
    return category


def _get_model():
    global _model
    if _model is None:
        import nighthawk.detector as nd
        _model = nd._load_model()
        logger.info("Nighthawk model loaded")
    return _model


def detect(path: str, threshold: int = 80) -> list:
    """Nighthawk's detections for one audio file, as dicts (the CSV columns
    of the nighthawk command: start_sec, end_sec, order, prob_order, family,
    prob_family, group, prob_group, species, prob_species,
    predicted_category, prob)."""
    import nighthawk.detector as nd
    model = _get_model()
    dets, _ = nd._run_detector_on_file(
        Path(path), model, nd._get_configuration_file_paths(),
        nd.DEFAULT_HOP_SIZE, float(threshold), nd.DEFAULT_MERGE_OVERLAPS,
        nd.DEFAULT_DROP_UNCERTAIN, nd.DEFAULT_AP_MASK_THRESHOLD, False,
        nd.DEFAULT_DO_CALIBRATION, True)
    if dets is None or len(dets) == 0:
        return []
    return dets.to_dict("records")


def _num(v) -> Optional[float]:
    """float, or None for missing/NaN (pandas fills empty cells with NaN)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _str(v) -> Optional[str]:
    return v if isinstance(v, str) and v else None


def _level(d: dict) -> str:
    cat = d.get("predicted_category")
    for lvl in ("species", "group", "family", "order"):
        v = d.get(lvl)
        if isinstance(v, str) and v and v == cat:
            return lvl
    return "order"


def night_of(when_utc: datetime, tz) -> str:
    """Local date the night began: a call at 2 am belongs to the evening before."""
    local = when_utc.replace(tzinfo=timezone.utc).astimezone(tz)
    return (local - timedelta(hours=12)).date().isoformat()


def _cut_clip(y, sr, start, end, dest):
    import soundfile as sf
    a = max(0, int((start - CLIP_PAD) * sr)); b = min(len(y), int((end + CLIP_PAD) * sr))
    sf.write(dest, y[a:b], sr, format="FLAC")


def process_chunk(chunk_id: str) -> int:
    """Run Nighthawk on one uploaded chunk. Returns the number of calls.
    Called from a background task, so database.SessionLocal is already
    this site's database (instance-aware in chirp-server-instances)."""
    from .. import database
    from ..models import AppSettings, FlightCall, NightChunk
    from .scheduled_push import site_tz
    import soundfile as sf

    with _lock:
        db = database.SessionLocal()
        try:
            ch = db.query(NightChunk).filter(NightChunk.id == chunk_id).first()
            if not ch or ch.status == "done" or not ch.path or not os.path.exists(ch.path):
                return 0
            s = db.query(AppSettings).filter(AppSettings.id == 1).first()
            ch.status = "processing"; db.commit()
            t0 = time.time()
            try:
                dets = detect(ch.path, int(getattr(s, "exp_nighthawk_threshold", None) or 80))
                y, sr = sf.read(ch.path, dtype="float32", always_2d=False)
                if getattr(y, "ndim", 1) > 1:
                    y = y.mean(axis=1)
                tz = site_tz(s)
                tax = taxonomy()["species"]
                n = 0
                for d in dets:
                    lvl = _level(d)
                    start, end = float(d["start_sec"]), float(d["end_sec"])
                    when = ch.started_at + timedelta(seconds=start)
                    code = _str(d.get("species"))
                    com, sci = (tax.get(code, (None, None, None))[:2]) if (lvl == "species" and code) else (None, None)
                    fid = str(uuid.uuid4())
                    clip = str(clips_dir() / f"{fid}.flac")
                    try:
                        _cut_clip(y, sr, start, end, clip)
                    except Exception as e:
                        logger.warning("Night call clip failed: %s", e); clip = None
                    db.add(FlightCall(
                        id=fid, chunk_id=ch.id, device_id=ch.device_id, detected_at=when,
                        night=night_of(when, tz), level=lvl, category=str(d.get("predicted_category")),
                        common_name=com, scientific_name=sci,
                        family=_str(d.get("family")), order=_str(d.get("order")), group=_str(d.get("group")),
                        prob=_num(d.get("prob")) or 0.0, prob_species=_num(d.get("prob_species")),
                        duration=end - start, clip_path=clip))
                    n += 1
                ch.calls = n; ch.status = "done"; ch.error = None
                ch.processed_at = datetime.utcnow()
                try:
                    os.remove(ch.path)
                except OSError:
                    pass
                ch.path = None
                db.commit()
                logger.info("Nighthawk: %d call(s) in %.0f s of night audio (%.0f s)",
                            n, ch.duration_seconds or 0, time.time() - t0)
                return n
            except Exception as e:
                db.rollback()
                ch = db.query(NightChunk).filter(NightChunk.id == chunk_id).first()
                if ch:
                    ch.status = "error"; ch.error = str(e)[:500]; db.commit()
                logger.error("Nighthawk failed on chunk %s: %s", chunk_id, e)
                return 0
        finally:
            db.close()


def cleanup(db) -> int:
    """Retry chunks left pending by a restart; drop failed audio after
    KEEP_FAILED_HOURS. Returns chunks removed."""
    from ..models import NightChunk
    removed = 0
    cutoff = datetime.utcnow() - timedelta(hours=KEEP_FAILED_HOURS)
    for ch in db.query(NightChunk).filter(NightChunk.status.in_(("error", "pending", "processing")),
                                          NightChunk.path.isnot(None)).all():
        if ch.created_at and ch.created_at < cutoff:
            try:
                os.remove(ch.path)
            except OSError:
                pass
            ch.path = None; ch.status = "error"; ch.error = (ch.error or "") + " (audio removed)"
            removed += 1
    db.commit()
    return removed


def pending_ids(db) -> list:
    """Chunks still waiting (e.g. after a restart), oldest first."""
    from ..models import NightChunk
    rows = (db.query(NightChunk.id).filter(NightChunk.status.in_(("pending", "processing")),
                                          NightChunk.path.isnot(None))
            .order_by(NightChunk.started_at).all())
    return [r[0] for r in rows]
