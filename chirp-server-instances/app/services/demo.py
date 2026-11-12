"""
The public demo location: a read-only copy of a real yard that anyone can
open from "Try the demo" (POST /api/v1/auth/demo) without an account.

build()  copies a curated snapshot of a source location into a new location
         flagged Instance.is_demo:
           - recent days: up to PER_DAY recordings a day from the last
             WINDOW_DAYS, chosen for strong, varied birds;
           - history: each species' first recording, so not every bird
             looks new;
           - bird profiles, regional field-guide data, the latest journals,
             and the stations as placeholders (name, mics, version only).
         Files go to <data_dir>/demo/<instance id>/, outside the recordings
         folder, so no cleanup or retention rule can touch them. Every
         password, key and token is blanked; notes and uploaded photos are
         left out; the place becomes DEMO_PLACE in settings and in text.

roll()   runs hourly (main.py). Recent recordings slide by whole days so they
         always fill the last WINDOW_DAYS up to now, keeping their time of
         day: anything in the future moves back WINDOW_DAYS, anything older
         than the window moves forward. History stays where it is. Journals
         and station "last seen" times follow.

The demo sign-in is read-only (main.py demo_may_use) and background jobs skip
the demo (instance_registry.iter_instance_sessions), so it never makes AI
calls, sends mail or pushes, or syncs. Run from the container:
    python -m app.services.demo build "Natick Birds"
    python -m app.services.demo roll
"""
import json
import logging
import os
import re
import secrets
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select, update
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger("chirp.demo")

WINDOW_DAYS = 14
PER_DAY = 20
DEMO_NAME = "Chirp Demo"
DEMO_USER = "chirp-demo"
DEMO_PLACE = "Concord, Massachusetts"
DEMO_LAT, DEMO_LON = 42.4604, -71.3489
# Marks the demo's stations as Chirp stations (lite.has_station); matches no key.
DEMO_KEY_ID = "demo-station"
NOT_BIRDS = re.compile(r"human|dog|engine|siren|gun|firework|power tool|noise|environmental", re.I)

# Settings that never leave the source: anything that signs in somewhere,
# sends something, or points at the source's own machines.
_SECRET = re.compile(r"(key|token|password|secret|smtp|webhook|vapid|apns|relay|server_url|haikubox|bird_buddy|"
                     r"birdweather|inat_|ollama|admin_email|device_api_keys)", re.I)
_KEEP = {"ebird_api_key"}          # read server-side for the field guide; never sent to viewers


def _demo_dir(instance_id: str) -> str:
    from ..config import settings
    return os.path.join(settings.data_dir, "demo", instance_id)


def _state_path(instance_id: str) -> str:
    return os.path.join(_demo_dir(instance_id), "state.json")


def _scrub_text(s):
    if not isinstance(s, str):
        return s
    return re.sub(r"\bNatick\b", "Concord", s)


_demo_files: dict = {"at": 0.0, "file": None, "id": None}


def is_demo_db() -> bool:
    """True while handling a request for the demo location."""
    import time
    from ..instance_registry import _current_instance_db_filename
    cur = _current_instance_db_filename.get(None)
    if not cur:
        return False
    if time.time() - _demo_files["at"] > 300:
        from ..registry_db import RegistrySessionLocal
        reg = RegistrySessionLocal()
        try:
            inst = demo_instance(reg)
            _demo_files.update(at=time.time(), file=inst.db_filename if inst else None, id=inst.id if inst else None)
        except Exception:
            return False
        finally:
            reg.close()
    return cur == _demo_files["file"]


def demo_instance(reg):
    from ..registry_models import Instance
    return reg.query(Instance).filter(Instance.is_demo == True).first()  # noqa: E712


# ── build ────────────────────────────────────────────────────────────────────

def _pick(src, min_conf: float):
    """Recent recordings (by local day) and one first-ever recording per species."""
    from ..models import AppSettings, Detection, Recording
    tz = ZoneInfo((src.query(AppSettings).first().timezone or "UTC"))
    since = datetime.utcnow() - timedelta(days=WINDOW_DAYS)
    usable = (Recording.deleted_at.is_(None), Recording.archived_at.is_(None), Recording.is_bat.isnot(True),
              Recording.is_live_detect_clip.isnot(True), Recording.is_live_session.isnot(True),
              Recording.haikubox_detection_id.is_(None), Recording.bird_buddy_media_id.is_(None),
              Recording.birdweather_soundscape_id.is_(None), Recording.device_id.isnot(None))

    def ok(r):
        dets = [d for d in r.detections if (d.confidence or 0) >= min_conf and d.common_name]
        if not dets or any(NOT_BIRDS.search(d.common_name or "") or NOT_BIRDS.search(d.label or "") for d in r.detections):
            return None
        if not r.wav_path or not os.path.exists(r.wav_path):
            return None
        return dets

    by_day = defaultdict(list)
    for r in src.query(Recording).filter(Recording.trigger_timestamp >= since, *usable).yield_per(500):
        dets = ok(r)
        if dets:
            day = r.trigger_timestamp.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz).date()
            by_day[day].append((len({d.common_name for d in dets}), max(d.confidence for d in dets), r.id))
    recent = []
    for day, rows in by_day.items():
        rows.sort(reverse=True)
        recent += [rid for _, _, rid in rows[:PER_DAY]]

    # Each species' first recording (outside the window), for history.
    first = {}
    q = (src.query(Detection.common_name, Recording.id, Recording.trigger_timestamp)
         .join(Recording, Detection.recording_id == Recording.id)
         .filter(Detection.confidence >= min_conf, Recording.trigger_timestamp < since, *usable)
         .order_by(Recording.trigger_timestamp))
    for name, rid, ts in q.yield_per(2000):
        if name and name not in first and not NOT_BIRDS.search(name):
            first[name] = rid
    history = []
    for rid in dict.fromkeys(first.values()):
        r = src.get(Recording, rid)
        if r and ok(r):
            history.append(rid)
    return recent, history


def _copy_file(path, dest_dir):
    if not path or not os.path.exists(path):
        return None
    os.makedirs(dest_dir, exist_ok=True)
    out = os.path.join(dest_dir, os.path.basename(path))
    if not os.path.exists(out):
        shutil.copy2(path, out)
    return out


def _match_owner(paths, like: str) -> None:
    """Gives paths (folders recursively) the owner of `like`."""
    try:
        st = os.stat(like)
    except OSError:
        return
    if os.geteuid() != 0:
        return
    for p in paths:
        if not os.path.exists(p):
            continue
        todo = [p]
        if os.path.isdir(p):
            for root, dirs, fs in os.walk(p):
                todo += [os.path.join(root, n) for n in dirs + fs]
        for x in todo:
            try:
                os.chown(x, st.st_uid, st.st_gid)
            except OSError:
                pass


def build(source_name: str) -> str:
    """Builds (or rebuilds) the demo from the location named source_name.
    Returns the demo instance id."""
    from ..api.auth import _get_crypt
    from ..instance_registry import get_engine_for_instance, new_db_filename, provision_instance_database
    from ..models import (AppSettings, BirdProfile, Detection, Device, MonthlyDiversityStats, Recording,
                          RegionalSpecies, User)
    from ..registry_db import RegistrySessionLocal, init_registry_db
    from ..registry_models import GlobalUser, Instance, Membership

    init_registry_db()
    reg = RegistrySessionLocal()
    try:
        source = reg.query(Instance).filter(Instance.name == source_name).first()
        if not source:
            raise SystemExit(f"No location named {source_name!r}")
        old = demo_instance(reg)
        if old:                                           # rebuild from scratch
            reg.query(Membership).filter(Membership.instance_id == old.id).delete()
            shutil.rmtree(_demo_dir(old.id), ignore_errors=True)
            reg.delete(old)
            reg.commit()
        user = reg.query(GlobalUser).filter(GlobalUser.username == DEMO_USER).first()
        if not user:
            user = GlobalUser(username=DEMO_USER, hashed_pw=_get_crypt().hash(secrets.token_urlsafe(24)))
            reg.add(user)
            reg.commit()
        fname = new_db_filename("demo0000")
        inst = Instance(name=DEMO_NAME, location_name=DEMO_PLACE, db_filename=fname, is_demo=True,
                        created_by_user_id=None)
        reg.add(inst)
        reg.commit()
        reg.add(Membership(user_id=user.id, instance_id=inst.id, role="viewer"))
        reg.commit()
        inst_id, src_file, demo_hash = inst.id, source.db_filename, user.hashed_pw
    finally:
        reg.close()

    provision_instance_database(fname)
    S = sessionmaker(bind=get_engine_for_instance(src_file))()
    D = sessionmaker(bind=get_engine_for_instance(fname))()
    files = _demo_dir(inst_id)
    try:
        ss = S.query(AppSettings).first()
        min_conf = float(ss.min_confidence_display or 0)
        recent, history = _pick(S, min_conf)
        ids = list(dict.fromkeys(recent + history))
        logger.info("Demo: %d recent and %d history recordings", len(recent), len(history))

        # Settings: copy, blank anything secret, move to the demo place.
        cols = [c for c in AppSettings.__table__.columns if c.name != "id"]
        vals = {}
        for c in cols:
            v = getattr(ss, c.name)
            if _SECRET.search(c.name) and c.name not in _KEEP:
                v = None
            vals[c.name] = v
        vals.update(location_name=DEMO_PLACE, latitude=DEMO_LAT, longitude=DEMO_LON, birdnet_lat=DEMO_LAT,
                    birdnet_lon=DEMO_LON, auth_enabled=True, notifications_enabled=False, auto_backup_enabled=False,
                    allow_manual_reanalyze=False, activity_log_track_ip=False, auto_delete_recordings_days=None,
                    auto_archive_recordings_days=None, haikubox_enabled=False, bird_buddy_enabled=False,
                    birdweather_enabled=False, inat_auto_refresh_enabled=False, ai_enhance_auto_apply=False,
                    server_reanalyze_on_upload=False, daily_summary_text=_scrub_text(ss.daily_summary_text),
                    weekly_summary_text=_scrub_text(ss.weekly_summary_text))
        D.execute(update(AppSettings).where(AppSettings.id == 1).values(**{k: vals[k] for k in vals
                                                                           if hasattr(AppSettings, k)}))

        # Stations as placeholders: what they are, never how to reach them.
        dev_ids = {r.device_id for r in S.query(Recording.device_id).filter(Recording.id.in_(ids)) if r.device_id}
        for d in S.query(Device).filter(Device.id.in_(dev_ids)):
            D.add(Device(id=d.id, name=_scrub_text(d.name), api_key_id=DEMO_KEY_ID, platform=d.platform, os_version=d.os_version, mic_count=d.mic_count,
                         mic_names=d.mic_names, birdnet_backend=d.birdnet_backend, coral_present=d.coral_present,
                         coral_form_factor=d.coral_form_factor, device_version=d.device_version, status="online",
                         last_seen=datetime.utcnow(), created_at=d.created_at))

        # Recordings and their detections, files copied.
        rcols = [c.name for c in Recording.__table__.columns]
        dcols = [c.name for c in Detection.__table__.columns]
        for i in range(0, len(ids), 200):
            chunk = ids[i:i + 200]
            for r in S.query(Recording).filter(Recording.id.in_(chunk)):
                row = {c: getattr(r, c) for c in rcols}
                row.update(wav_path=_copy_file(r.wav_path, os.path.join(files, "audio")) or "",
                           filename="recording-" + r.id[:8] + (os.path.splitext(r.filename or r.wav_path)[1] or ".wav"),
                           json_path=None,
                           spectrogram_path=_copy_file(r.spectrogram_path, os.path.join(files, "spectrograms")),
                           latitude=DEMO_LAT if r.latitude is not None else None,
                           longitude=DEMO_LON if r.longitude is not None else None,
                           place_name=None, notes=None, label=None, inat_observation_id=None,
                           inat_observation_url=None, is_saved=False, bird_buddy_video_path=None,
                           ai_reanalysis_note=_scrub_text(r.ai_reanalysis_note))
                D.execute(insert(Recording).values(**row))
                for d in r.detections:
                    drow = {c: getattr(d, c) for c in dcols}
                    drow["clip_path"] = _copy_file(d.clip_path, os.path.join(files, "clips"))
                    D.execute(insert(Detection).values(**drow))
            D.commit()

        # Bird profiles for the species in it; shared media paths work as is.
        names = {n for (n,) in D.query(Detection.common_name).distinct() if n}
        pcols = [c.name for c in BirdProfile.__table__.columns]
        for p in S.query(BirdProfile).filter(BirdProfile.common_name.in_(names)):
            row = {c: getattr(p, c) for c in pcols}
            row.update(notes=None, ai_presence_summary=_scrub_text(p.ai_presence_summary))
            D.execute(insert(BirdProfile).values(**row))
        for M in (RegionalSpecies, MonthlyDiversityStats):
            mcols = [c.name for c in M.__table__.columns]
            for x in S.query(M):
                D.execute(insert(M).values(**{c: getattr(x, c) for c in mcols}))

        # The local user the demo sign-in reads as.
        from ..config import settings as cfg
        try:
            ver = open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "VERSION")).read().strip()
        except OSError:
            ver = None
        D.add(User(username=DEMO_USER, hashed_pw=demo_hash, role="viewer", display_name="Demo visitor",
                   dashboard_mode="standard", ui_mode="pro", last_seen_whats_new_version=ver,
                   notify_new_bird=False, notify_daily_digest=False, notify_daily_digest_push=False,
                   notify_new_bird_push=False, notify_device_offline_push=False, notify_device_offline_email=False,
                   notify_daily_journal_push=False, notify_weekly_journal_push=False))
        D.commit()

        os.makedirs(files, exist_ok=True)
        cutoff = datetime.utcnow() - timedelta(days=WINDOW_DAYS)
        with open(_state_path(inst_id), "w") as f:
            json.dump({"history_before": cutoff.isoformat(), "window_days": WINDOW_DAYS,
                       "source": source_name, "built_at": datetime.utcnow().isoformat(),
                       "recent": len(recent), "history": len(history)}, f)
    finally:
        S.close()
        D.close()
    # Built from a shell as root: hand everything to the server's own user.
    from ..instance_registry import INSTANCES_DIR, _instance_db_path
    _match_owner([_instance_db_path(fname) + x for x in ("", "-wal", "-shm")], INSTANCES_DIR)
    _match_owner([files], INSTANCES_DIR)
    roll_instance(inst_id)
    _match_owner([_instance_db_path(fname) + x for x in ("", "-wal", "-shm")], INSTANCES_DIR)
    logger.info("Demo built: %s", inst_id)
    return inst_id


# ── roll ─────────────────────────────────────────────────────────────────────

def _shift_fields(D, Model, ids, field_names, delta):
    table = Model.__table__
    for rid in ids:
        row = D.execute(select(*[table.c[f] for f in field_names]).where(table.c.id == rid)).first()
        vals = {f: (v + delta) for f, v in zip(field_names, row) if v is not None}
        if vals:
            D.execute(update(table).where(table.c.id == rid).values(**vals))


def roll_instance(inst_id: str, now: datetime = None) -> dict:
    """Moves the demo's recent recordings into the last WINDOW_DAYS before
    now (whole days, time of day kept) and freshens journals and stations."""
    from ..instance_registry import get_engine_for_instance
    from ..models import AppSettings, Device, Recording, User
    from ..registry_db import RegistrySessionLocal
    from ..registry_models import Instance
    now = now or datetime.utcnow()
    reg = RegistrySessionLocal()
    try:
        inst = reg.get(Instance, inst_id)
        fname = inst.db_filename
    finally:
        reg.close()
    try:
        state = json.load(open(_state_path(inst_id)))
    except (OSError, ValueError):
        return {"moved": 0}
    cutoff = datetime.fromisoformat(state["history_before"])
    window = timedelta(days=state.get("window_days", WINDOW_DAYS))

    D = sessionmaker(bind=get_engine_for_instance(fname))()
    moved = 0
    try:
        rows = (D.query(Recording.id, Recording.trigger_timestamp)
                .filter(Recording.trigger_timestamp >= cutoff, Recording.is_live_detect_clip.isnot(True)).all())
        for rid, ts in rows:
            delta = timedelta(0)
            while ts + delta > now:
                delta -= window
            while ts + delta <= now - window:
                delta += window
            if delta:
                _shift_fields(D, Recording, [rid], ["trigger_timestamp", "created_at", "ai_reanalysis_generated_at"], delta)
                moved += 1
        # The window must stay above history, whatever the clock does.
        new_cutoff = now - window - timedelta(days=1)
        if new_cutoff > cutoff:
            state["history_before"] = new_cutoff.isoformat()

        s = D.query(AppSettings).first()
        tz = ZoneInfo(s.timezone or "UTC")
        local = now.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
        evening = local.replace(hour=18, minute=0, second=0, microsecond=0)
        if evening > local:
            evening -= timedelta(days=1)
        to_utc = lambda d: d.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)  # noqa: E731
        s.daily_summary_generated_at = to_utc(evening)
        sunday = (local - timedelta(days=(local.weekday() + 1) % 7)).replace(hour=12, minute=0, second=0, microsecond=0)
        if sunday > local:
            sunday -= timedelta(days=7)
        s.weekly_summary_generated_at = to_utc(sunday)
        s.weekly_summary_period_end = to_utc(sunday - timedelta(days=1))
        s.weekly_summary_period_start = to_utc(sunday - timedelta(days=7))
        if not state.get("loop_recording_id"):
            state["loop_recording_id"] = _pick_loop(D, cutoff)
        for i, d in enumerate(D.query(Device).order_by(Device.name)):
            d.last_seen, d.status, d.offline_since = now - timedelta(minutes=1 + i), "online", None
        try:
            ver = open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "VERSION")).read().strip()
            D.query(User).filter(User.username == DEMO_USER).update({"last_seen_whats_new_version": ver})
        except OSError:
            pass
        D.commit()
    finally:
        D.close()
    with open(_state_path(inst_id), "w") as f:
        json.dump(state, f)
    try:
        from ..cache import invalidate_detection_caches, invalidate_settings
        invalidate_settings()
        invalidate_detection_caches()
    except Exception:
        pass
    return {"moved": moved}


def roll() -> dict:
    from ..registry_db import RegistrySessionLocal
    reg = RegistrySessionLocal()
    try:
        inst = demo_instance(reg)
        iid = inst.id if inst else None
    finally:
        reg.close()
    return roll_instance(iid) if iid else {"moved": 0}


# ── The demo station: Live Detect through a station replays one recording ──
#
# Every station listen (Live Detect, Chirp Live, the TV) asks for the last
# few seconds a mic heard. In the demo that's a slice of one recording,
# looped on the wall clock, so everyone hears the same moment; and what
# "the station heard" is that recording's own detections in the slice, with
# no BirdNET run.

LISTEN_SECONDS = 4.0
_loop_cache: dict = {}


def _pick_loop(D, since) -> str:
    """The recent recording with the most species (20–90 s long)."""
    from ..models import AppSettings, Recording
    mc = float(D.query(AppSettings).first().min_confidence_display or 0)
    best = None
    for r in D.query(Recording).filter(Recording.trigger_timestamp >= since,
                                       Recording.duration_seconds.between(20, 90)):
        dets = [d for d in r.detections if (d.confidence or 0) >= mc and d.start_time is not None]
        key = (len({d.common_name for d in dets}), max((d.confidence for d in dets), default=0))
        if dets and (best is None or key > best[0]):
            best = (key, r.id)
    return best[1] if best else None


def set_loop(recording_id: str) -> None:
    """Choose the station's recording (python -m app.services.demo loop ID)."""
    from ..registry_db import RegistrySessionLocal
    reg = RegistrySessionLocal()
    try:
        iid = demo_instance(reg).id
    finally:
        reg.close()
    state = json.load(open(_state_path(iid)))
    state["loop_recording_id"] = recording_id
    with open(_state_path(iid), "w") as f:
        json.dump(state, f)
    _loop_cache.clear()


def _loop(db):
    """(recording, samples, sample rate) for the demo station, cached."""
    import numpy as np
    import soundfile as sf
    from ..models import Recording
    is_demo_db()
    try:
        rid = json.load(open(_state_path(_demo_files["id"]))).get("loop_recording_id")
    except (OSError, ValueError, TypeError):
        rid = None
    rec = db.get(Recording, rid) if rid else None
    if not rec or not rec.wav_path or not os.path.exists(rec.wav_path):
        return None
    if _loop_cache.get("path") != rec.wav_path:
        data, sr = sf.read(rec.wav_path, dtype="float32", always_2d=True)
        _loop_cache.update(path=rec.wav_path, samples=np.ascontiguousarray(data.mean(axis=1)), sr=sr)
    return rec, _loop_cache["samples"], _loop_cache["sr"]


def _loop_window(total: float, now: float, seconds: float):
    """[start, end) of the slice ending now, in loop time (may wrap)."""
    end = now % total
    return end - seconds, end


def demo_listen_clip(db, now: float = None) -> bytes:
    """The last LISTEN_SECONDS of the demo station's loop, as a WAV."""
    import io
    import time
    import numpy as np
    import soundfile as sf
    from fastapi import HTTPException
    got = _loop(db)
    if not got:
        raise HTTPException(503, "The demo station isn't playing right now.")
    _, x, sr = got
    n, want = len(x), int(LISTEN_SECONDS * sr)
    end = int(((now or time.time()) % (n / sr)) * sr)
    idx = np.arange(end - want, end) % n
    buf = io.BytesIO()
    sf.write(buf, x[idx], sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def demo_station_heard(db, min_confidence: float = None, now: float = None) -> dict:
    """What the demo station 'heard' in the slice demo_listen_clip() returns:
    the loop recording's detections that overlap it, one per species."""
    import time
    from ..models import AppSettings, BirdProfile
    got = _loop(db)
    if not got:
        return {"detected": False, "detections": []}
    rec, x, sr = got
    total = len(x) / sr
    start, end = _loop_window(total, now or time.time(), LISTEN_SECONDS)
    if min_confidence is None:
        min_confidence = float(db.query(AppSettings).first().min_confidence_display or 0)

    def overlaps(d):
        a, b = d.start_time or 0, d.end_time if d.end_time is not None else (d.start_time or 0) + 3
        ranges = [(start, end)] if start >= 0 else [(0, end), (total + start, total)]
        return any(a < hi and b > lo for lo, hi in ranges)

    best = {}
    for d in rec.detections:
        if (d.confidence or 0) >= min_confidence and d.common_name and overlaps(d):
            if d.common_name not in best or d.confidence > best[d.common_name].confidence:
                best[d.common_name] = d
    if not best:
        return {"detected": False, "detections": []}
    out = []
    for d in sorted(best.values(), key=lambda d: -d.confidence):
        p = db.query(BirdProfile).filter(BirdProfile.common_name == d.common_name).first()
        photo = None
        if p and p.photo_path and os.path.exists(p.photo_path):
            photo = f"/api/v1/birds/{p.id}/photo"
        elif p:
            photo = p.photo_url
        out.append({"common_name": d.common_name, "scientific_name": d.scientific_name, "confidence": d.confidence,
                    "profile_id": p.id if p else None, "photo_url": photo})
    return {"detected": True, "recording_id": None, "detections": out}


def touch_devices() -> None:
    """Keeps the demo's stations online between hourly rolls."""
    from ..instance_registry import get_engine_for_instance
    from ..models import Device
    from ..registry_db import RegistrySessionLocal
    reg = RegistrySessionLocal()
    try:
        inst = demo_instance(reg)
        fname = inst.db_filename if inst else None
    finally:
        reg.close()
    if not fname:
        return
    D = sessionmaker(bind=get_engine_for_instance(fname))()
    try:
        now = datetime.utcnow()
        for i, d in enumerate(D.query(Device).order_by(Device.name)):
            d.last_seen, d.status, d.offline_since = now - timedelta(seconds=5 + i), "online", None
            d.api_key_id = d.api_key_id or DEMO_KEY_ID
        D.commit()
    finally:
        D.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build" and len(sys.argv) > 2:
        print("demo", build(sys.argv[2]))
    elif cmd == "roll":
        print(roll())
    elif cmd == "loop" and len(sys.argv) > 2:
        set_loop(sys.argv[2])
        print("loop", sys.argv[2])
    else:
        print(__doc__)
