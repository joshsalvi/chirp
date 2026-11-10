"""
Usage per location, for Global Admin → Instances: activity (recordings and
detections over today / 7 / 30 days, species, last recording), people
(members and when each last signed in), stations (last seen) and storage.

Counts are quick SQL on each location's database, done on request.
Storage means adding up every recording's files, so it's measured in the
background at most once an hour and shown with when it was measured.
"""
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger("chirp.usage")

STORAGE_MAX_AGE = 3600
_storage: dict = {}            # instance id → {"bytes", "files", "at"}
_measuring = threading.Lock()


def _site_midnight_utc(settings) -> datetime:
    try:
        tz = ZoneInfo((settings.timezone if settings else None) or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    now = datetime.now(tz)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def _iso(dt):
    return dt.isoformat() + "Z" if dt else None


def activity(db) -> dict:
    """Recordings, detections, species and stations for one location's database."""
    from ..models import AppSettings, Detection, Device, Recording
    s = db.query(AppSettings).first()
    now = datetime.utcnow()
    since = {"today": _site_midnight_utc(s), "d7": now - timedelta(days=7), "d30": now - timedelta(days=30)}
    rec = {k: db.query(func.count(Recording.id)).filter(Recording.trigger_timestamp >= t).scalar() or 0 for k, t in since.items()}
    rec["total"] = db.query(func.count(Recording.id)).scalar() or 0
    last = db.query(func.max(Recording.trigger_timestamp)).scalar()
    min_conf = float(getattr(s, "min_confidence_display", 0.0) or 0.0) if s else 0.0

    def shown(q, t):
        return (q.join(Recording, Detection.recording_id == Recording.id)
                .filter(Recording.trigger_timestamp >= t, Detection.confidence >= min_conf))
    det7 = shown(db.query(func.count(Detection.id)), since["d7"]).scalar() or 0
    species30 = shown(db.query(func.count(func.distinct(Detection.common_name))), since["d30"]).scalar() or 0
    stations = [{"name": d.name, "last_seen": _iso(d.last_seen)}
                for d in db.query(Device).order_by(Device.last_seen.desc().nullslast()).all()]
    return {"recordings": rec, "detections_7d": det7, "species_30d": species30,
            "last_recording": _iso(last), "stations": stations}


def _measure(instances):
    """Adds up each location's recording files (WAV, spectrogram, JSON) and its database."""
    from ..instance_registry import _instance_db_path, get_engine_for_instance
    from ..models import Recording
    if not _measuring.acquire(blocking=False):
        return
    try:
        for inst_id, db_filename in instances:
            total, files = 0, 0
            try:
                total += os.path.getsize(_instance_db_path(db_filename))
            except OSError:
                pass
            db = sessionmaker(bind=get_engine_for_instance(db_filename))()
            try:
                for wav, spec, js in db.query(Recording.wav_path, Recording.spectrogram_path, Recording.json_path).yield_per(2000):
                    for p in (wav, spec, js):
                        if p:
                            try:
                                total += os.path.getsize(p); files += 1
                            except OSError:
                                pass
            except Exception as e:
                logger.warning("Usage: storage for %s not measured: %s", inst_id, e)
            finally:
                db.close()
            _storage[inst_id] = {"bytes": total, "files": files, "at": time.time()}
    finally:
        _measuring.release()


def storage(inst_id: str, instances) -> dict:
    """Last measurement for this location; starts a new one in the background when stale."""
    got = _storage.get(inst_id)
    if not got or time.time() - got["at"] > STORAGE_MAX_AGE:
        threading.Thread(target=_measure, args=(list(instances),), daemon=True, name="usage-storage").start()
    if not got:
        return {"bytes": None, "files": None, "measured_at": None}
    return {"bytes": got["bytes"], "files": got["files"],
            "measured_at": datetime.utcfromtimestamp(got["at"]).isoformat() + "Z"}


def all_usage() -> list:
    """Usage for every location on this server."""
    from ..instance_registry import get_engine_for_instance
    from ..registry_db import RegistrySessionLocal
    from ..registry_models import GlobalUser, Instance, Membership
    reg = RegistrySessionLocal()
    try:
        insts = reg.query(Instance).order_by(Instance.created_at.desc()).all()
        pairs = [(i.id, i.db_filename) for i in insts]
        out = []
        for inst in insts:
            members = []
            for m, u in (reg.query(Membership, GlobalUser).join(GlobalUser, GlobalUser.id == Membership.user_id)
                         .filter(Membership.instance_id == inst.id).all()):
                members.append({"username": u.username, "role": m.role, "last_login": _iso(u.last_login)})
            members.sort(key=lambda m: m["last_login"] or "", reverse=True)
            row = {"id": inst.id, "name": inst.name, "members": members,
                   "last_sign_in": members[0]["last_login"] if members else None,
                   "storage": storage(inst.id, pairs)}
            db = sessionmaker(bind=get_engine_for_instance(inst.db_filename))()
            try:
                row.update(activity(db))
            except Exception as e:
                logger.warning("Usage: %s not read: %s", inst.id, e)
                row["error"] = "This location's database couldn't be read."
            finally:
                db.close()
            out.append(row)
        return out
    finally:
        reg.close()
