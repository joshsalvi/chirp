"""
Night-caller near misses: owls and other night species BirdNET scored but
didn't report (under the threshold, or an owl score without a matching
hoot). One row per species per analysis, written by the server BirdNET
pass (see services/birdnet_pass._near_misses). Listening to the top ones
is how to pick a per-species threshold (Settings -> Detection).
"""
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AppSettings, Detection, NearMiss, Recording
from ..services.birdnet_pass import (NIGHT_CALLER_RE, NIGHT_SPECIES_MIN_CONF, OWL_MIN_CONF, is_low_owl,
                                     night_rules, night_species_for, species_required, uses_night_floor)

router = APIRouter()

# Thresholds the summary counts near misses at: "lowering this species to
# t would have reported N more recordings".
STEPS = (0.05, 0.075, 0.10, 0.125, 0.15, 0.20, 0.25, 0.30)


def _default_threshold(app_s, name: str) -> float:
    """Same rule as birdnet_pass.run_birdnet's required(), before any
    per-species score."""
    mc = float(getattr(app_s, "birdnet_min_confidence", 0.05) or 0.05) if app_s else 0.05
    r = night_rules(app_s)
    return species_required(name, mc, None, r["mode"], r["per_species"])


@router.get("/summary")
def near_miss_summary(days: int = Query(90, ge=1, le=3650), db: Session = Depends(get_db)):
    """Per species: how often and how high it nearly made it, why it didn't,
    its current threshold, and what lower thresholds would have added."""
    since = datetime.utcnow() - timedelta(days=days)
    app_s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    overrides = dict(getattr(app_s, "birdnet_species_thresholds", None) or {}) if app_s else {}
    rows = (db.query(NearMiss.common_name, NearMiss.confidence, NearMiss.reason, NearMiss.recording_id)
            .join(Recording, Recording.id == NearMiss.recording_id)
            .filter(Recording.deleted_at.is_(None), Recording.trigger_timestamp >= since)
            .all())
    by: dict = {}
    for name, conf, reason, rid in rows:
        e = by.setdefault(name, {"scores": [], "reasons": {}, "recordings": set(), "below": []})
        e["scores"].append(float(conf))
        e["reasons"][reason or "unknown"] = e["reasons"].get(reason or "unknown", 0) + 1
        e["recordings"].add(rid)
        if reason == "below threshold":
            e["below"].append(float(conf))
    kept = dict(
        (n, (c, lo)) for n, c, lo in
        db.query(Detection.common_name,
                 func.count(Detection.id),
                 func.min(Detection.confidence))
        .join(Recording, Recording.id == Detection.recording_id)
        .filter(Recording.deleted_at.is_(None), Recording.trigger_timestamp >= since,
                Detection.common_name.in_(list(by) or [""]))
        .group_by(Detection.common_name).all())
    out = []
    for name, e in by.items():
        sc = np.array(e["scores"])
        below = np.array(e["below"]) if e["below"] else np.zeros(0)
        out.append({
            "species": name,
            "near_misses": len(sc),
            "recordings": len(e["recordings"]),
            "max": round(float(sc.max()), 3),
            "p50": round(float(np.percentile(sc, 50)), 3),
            "p90": round(float(np.percentile(sc, 90)), 3),
            "reasons": e["reasons"],
            "threshold": float(overrides.get(name, _default_threshold(app_s, name))),
            "custom_threshold": name in overrides,
            "detections": int(kept.get(name, (0, None))[0]),
            "lowest_detection": (round(float(kept[name][1]), 3) if name in kept and kept[name][1] is not None else None),
            "would_add": {f"{t:.3f}": int((below >= t).sum()) for t in STEPS},
        })
    out.sort(key=lambda r: (-r["recordings"], -r["max"]))
    return {"days": days, "steps": list(STEPS), "species": out}


@router.get("")
def list_near_misses(species: Optional[str] = None, days: int = Query(90, ge=1, le=3650),
                     limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    """Highest near misses first, with the recording to listen to."""
    since = datetime.utcnow() - timedelta(days=days)
    q = (db.query(NearMiss, Recording.trigger_timestamp, Recording.filename)
         .join(Recording, Recording.id == NearMiss.recording_id)
         .filter(Recording.deleted_at.is_(None), Recording.trigger_timestamp >= since))
    if species:
        q = q.filter(NearMiss.common_name == species)
    items = []
    for nm, ts, fn in q.order_by(NearMiss.confidence.desc()).limit(limit).all():
        items.append({
            "id": nm.id, "recording_id": nm.recording_id, "species": nm.common_name,
            "confidence": round(float(nm.confidence), 3), "start_time": nm.start_time,
            "end_time": nm.end_time, "threshold": nm.threshold, "reason": nm.reason,
            "band": nm.band, "recorded_at": ts.isoformat() if ts else None, "filename": fn,
        })
    return {"items": items}


@router.get("/night-species")
def night_species(db: Session = Depends(get_db)):
    """Night callers for Settings → Detection's night-threshold toggles:
    those BirdNET can report at the server's location in any week, plus any
    already detected or set. Each with whether it currently uses the night
    floor and the score it needs."""
    from sqlalchemy import func
    app_s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    rules = night_rules(app_s)
    mc = float(getattr(app_s, "birdnet_min_confidence", 0.05) or 0.05) if app_s else 0.05
    overrides = dict(getattr(app_s, "birdnet_species_thresholds", None) or {}) if app_s else {}
    names = set(night_species_for(getattr(app_s, "latitude", None), getattr(app_s, "longitude", None)))
    detected = {}
    for name, n in (db.query(Detection.common_name, func.count(Detection.id))
                    .group_by(Detection.common_name).all()):
        if NIGHT_CALLER_RE.search(name or ""):
            detected[name] = int(n)
            names.add(name)
    names |= {k for k in rules["per_species"] if NIGHT_CALLER_RE.search(k)}
    items = []
    for name in sorted(names, key=lambda n: (-detected.get(n, 0), n)):
        items.append({
            "species": name,
            "owl": is_low_owl(name),
            "detections": detected.get(name, 0),
            "night_floor": uses_night_floor(name, rules["mode"], rules["per_species"]),
            "per_species_setting": rules["per_species"].get(name, True),
            "night_threshold": OWL_MIN_CONF if is_low_owl(name) else min(mc, NIGHT_SPECIES_MIN_CONF),
            "global_threshold": mc,
            "required": species_required(name, mc, overrides, rules["mode"], rules["per_species"]),
            "custom": overrides.get(name),
        })
    return {"mode": rules["mode"], "global_threshold": mc, "items": items}
