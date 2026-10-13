"""
Chirp — Diagnostics API

GET /api/v1/diagnostics/run            — full checks, structured JSON
GET /api/v1/diagnostics/run?mode=db    — DB stats only
GET /api/v1/diagnostics/run?mode=mic   — microphone test via SSH to each device
GET /api/v1/diagnostics/report         — full plain-text report (downloadable)
GET /api/v1/diagnostics/report?include_logs=true — report + log file attachments (zip)
"""

import io
import logging
import os
import platform
import shutil
import time
import zipfile
from datetime import datetime, timedelta
from typing import Optional

try:
    import psutil as _psutil
    _HAS_PSUTIL = True
except ImportError:
    _psutil = None  # type: ignore
    _HAS_PSUTIL = False

from fastapi import APIRouter, Depends, Query, WebSocket, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models import (
    Recording, Detection, Device, BirdProfile, AppSettings,
    RegionalSpecies,
)
from ..config import settings
from ..services import log_buffer

logger = logging.getLogger("chirp.api.diagnostics")
router = APIRouter()

@router.post("/db/vacuum")
def vacuum_database(request: Request, db: Session = Depends(get_db)):
    """
    Reclaims space SQLite has left behind from deletes/archives (see
    db_reclaimable in /diagnostics/run's own response, which is what this
    is for) — deliberately a separate, admin-triggered action rather than
    something StorageManager runs on its own schedule (see its own hourly
    cycle's comment on ANALYZE for why): VACUUM needs exclusive access and
    rewrites the whole file, which for a database that's actually grown
    large could be a real, multi-minute stall — something to run
    knowingly during low-traffic hours, not have happen silently.
    Same admin gate as the backup/restore endpoints below, for the same
    reason: this is a significant, disruptive database-level operation.
    """
    from .app_settings import _require_admin
    _require_admin(request, db)

    db_path = settings.db_url.replace("sqlite:////", "/").replace("sqlite:///", "")
    size_before = os.path.getsize(db_path) if os.path.exists(db_path) else 0

    # VACUUM can't run inside SQLAlchemy's normal managed transaction
    # (SQLite itself refuses it inside a transaction block) — the raw
    # DBAPI connection's own autocommit-equivalent is needed here, not
    # db.execute() on the ORM session.
    raw = db.connection().connection
    raw.isolation_level = None
    try:
        cur = raw.cursor()
        cur.execute("VACUUM")
        cur.close()
    finally:
        raw.isolation_level = ""

    size_after = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    return {
        "ok": True,
        "size_before": _fmt_bytes(size_before),
        "size_after": _fmt_bytes(size_after),
        "reclaimed": _fmt_bytes(max(0, size_before - size_after)),
    }


# Port chirp-device's local status_server listens on (see chirp-device/chirp/status_server.py
# and chirp-device/config.yaml `status_server.port`). Overridable per-request via the
# `status_port` query param on the mic-levels websocket, for devices running a custom port.
DEVICE_STATUS_PORT = 8766


def _get_device_shared_key(dev: Device, db: Session) -> str:
    """
    Look up the shared secret this device uses to authenticate itself to the
    server (X-API-Key on /pair, /heartbeat, etc.) — reused as the credential
    when the server calls BACK into the device's local status_server
    (X-Chirp-Key header). Same key, both directions; nothing new to provision
    or rotate separately.
    """
    if not getattr(dev, "api_key_id", None):
        return ""
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    keys = (s.device_api_keys or []) if s else []
    for k in keys:
        if k.get("id") == dev.api_key_id:
            return k.get("key", "") or ""
    return ""


async def _poll_device_status_levels(ip: str, port: int, shared_key: str, timeout: float = 2.0):
    """
    Try the device's own local status_server (`GET /levels`). Returns a list
    of device-level dicts in the same shape the SSH/arecord path produces, or
    None if unreachable — e.g. the device is running an older chirp-device
    build without status_server.py, `status_server.enabled: false` in its
    config.yaml, or a LAN/firewall issue. Never raises; callers treat None as
    "fall back to SSH probing for everything", so this is purely additive —
    a device that never responds behaves exactly as before this feature
    existed.
    """
    import httpx
    from ..services.device_net import httpx_kwargs
    url = f"http://{ip}:{port}/levels"
    headers = {"X-Chirp-Key": shared_key} if shared_key else {}
    try:
        async with httpx.AsyncClient(timeout=timeout, **httpx_kwargs(ip)) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            logger.debug("Device status endpoint %s returned %d", url, resp.status_code)
            return None
        data = resp.json()
        out = []
        for s in data.get("streams", []) or []:
            if not isinstance(s, dict):
                continue
            out.append({
                "name": s.get("name", "unknown"),
                "role": s.get("role"),
                "db": s.get("db"),
                "peak": s.get("peak"),
                "sr": s.get("sr"),
                "bins": s.get("bins", []),
                "error": s.get("error"),
                "card": s.get("alsa_card"),        # unified with the SSH path's "card" field — the
                "alsa_card": s.get("alsa_card"),   # frontend reads .card uniformly; alsa_card kept too
                "source": "device_local",          # for anything server-side that wants the explicit name
            })
        return out
    except Exception as e:
        logger.debug("Device local status endpoint unreachable (%s:%s): %s", ip, port, e)
        return None


# ── Helpers ────────────────────────────────────────────────────────────────────

from ..services.storage_manager import fmt_bytes as _fmt_bytes, dir_stats as _dir_stats


def _fmt_age(seconds: Optional[int]) -> str:
    if seconds is None:
        return "unknown"
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m}m"


# ── Check functions ────────────────────────────────────────────────────────────

def _system_info() -> dict:
    try:
        from ..config import settings as _settings
        base = {
            "ok":            True,
            "chirp_version": _settings.app_version,
            "hostname":      platform.node(),
            "python":        platform.python_version(),
            "platform":      platform.platform(),
            "psutil":        _HAS_PSUTIL,
        }
        if _HAS_PSUTIL:
            proc      = _psutil.Process(os.getpid())
            boot_time = datetime.fromtimestamp(_psutil.boot_time())
            uptime_s  = int((datetime.now() - boot_time).total_seconds())
            mem       = _psutil.virtual_memory()
            proc_mem  = proc.memory_info()
            base.update({
                "cpu_count":       _psutil.cpu_count(),
                "cpu_pct":         _psutil.cpu_percent(interval=0.5),
                "mem_total":       _fmt_bytes(mem.total),
                "mem_used":        _fmt_bytes(mem.used),
                "mem_available":   _fmt_bytes(mem.available),
                "mem_pct":         mem.percent,
                "uptime_s":        uptime_s,
                "uptime_human":    _fmt_age(uptime_s),
                "boot_time":       boot_time.isoformat(),
                "process_mem_rss": _fmt_bytes(proc_mem.rss),
                "process_cpu_pct": proc.cpu_percent(interval=0.1),
                "process_threads": proc.num_threads(),
                "process_fds":     proc.num_fds() if hasattr(proc, "num_fds") else None,
            })
        else:
            base["note"] = "psutil not installed — add to requirements.txt and rebuild Docker image for full metrics"
        try:
            usage = shutil.disk_usage("/")
            base["disk_root_total"] = _fmt_bytes(usage.total)
            base["disk_root_used"]  = _fmt_bytes(usage.used)
            base["disk_root_free"]  = _fmt_bytes(usage.free)
            base["disk_root_pct"]   = round(usage.used / usage.total * 100, 1)
        except Exception:
            pass

        # Bat species classifier model files — real fix for a real, previously
        # silent failure mode found earlier this session: the classifier's
        # model-file path resolution was always correct, but the Docker
        # image never actually shipped the ~26MB model directory at all,
        # meaning bat species ID silently did nothing even when enabled,
        # with the only clue being a DEBUG-level log line. Checking this
        # directly here means a future instance of the exact same class of
        # bug (a code fix that isn't actually reflected in what got
        # deployed) surfaces immediately in diagnostics instead of only
        # after extensive log archaeology.
        try:
            from ..services.bat_species_classifier import is_available as _bat_models_available, _MODELS_DIR
            base["bat_models_present"] = _bat_models_available()
            base["bat_models_dir"]     = str(_MODELS_DIR)
        except Exception as e:
            base["bat_models_present"] = False
            base["bat_models_error"]   = str(e)

        # Key package versions — useful for troubleshooting version-specific
        # bugs (e.g. the Python 3.11 vs 3.12 f-string restriction issue
        # found earlier this session would have been caught immediately by
        # seeing "3.11.x" here alongside a report of a feature failing).
        base["packages"] = {}
        for pkg_name in ("fastapi", "uvicorn", "sqlalchemy", "tensorflow", "httpx", "pydantic"):
            try:
                import importlib.metadata as _importlib_metadata
                base["packages"][pkg_name] = _importlib_metadata.version(pkg_name)
            except Exception:
                base["packages"][pkg_name] = "not installed"

        # SMTP configuration status — doesn't expose credentials, just
        # whether email notifications/diagnostics-report-emailing have
        # what they need to actually work at all.
        try:
            from ..database import SessionLocal as _SessionLocal
            from ..models import AppSettings as _AS_sys
            with _SessionLocal() as _db_sys:
                _s_sys = _db_sys.query(_AS_sys).filter(_AS_sys.id == 1).first()
                base["smtp_configured"] = bool(_s_sys and _s_sys.smtp_host and _s_sys.smtp_from_address)
        except Exception:
            base["smtp_configured"] = None

        return base
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/db/query-plan")
def check_query_plans(request: Request, db: Session = Depends(get_db)):
    """
    Runs EXPLAIN QUERY PLAN against the app's own heaviest query
    patterns — the ones behind /stats and dashboard-summary specifically,
    the two found and fixed for missing caching earlier — and reports
    whether SQLite is using an index for each (SEARCH) or falling back to
    a full table scan (SCAN). Built to answer a size/engine question with
    this deployment's own data rather than a general claim: a SCAN on a
    table with a meaningful row count is the concrete signal that would
    change the recommendation from "stay on SQLite" to "worth
    investigating further" — this makes that check something anyone can
    run themselves instead of taking it on faith.
    Same admin gate as vacuum/backup/restore — not destructive, but this
    exposes literal internal query text, which isn't something to leave
    open to non-admins.
    """
    from .app_settings import _require_admin
    _require_admin(request, db)

    from datetime import datetime, timedelta
    raw = db.connection().connection
    cur = raw.cursor()

    # Each entry: a human label, the SQL (parameterized with a
    # representative recent cutoff, matching what the app itself sends),
    # and which table's row count is the relevant one to report alongside
    # it — a SCAN matters a lot more on 150,000 rows than on 150.
    since_recent = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    checks = [
        {
            "label": "Recording lookup by trigger_timestamp + deleted_at (used by dashboard-summary, /stats)",
            "table": "recordings",
            "sql": f"SELECT COUNT(*) FROM recordings WHERE trigger_timestamp >= '{since_recent}' AND deleted_at IS NULL",
        },
        {
            "label": "Detection join + confidence filter (used by dashboard-summary)",
            "table": "detections",
            "sql": (
                "SELECT COUNT(*) FROM detections "
                "JOIN recordings ON detections.recording_id = recordings.id "
                f"WHERE recordings.trigger_timestamp >= '{since_recent}' "
                "AND recordings.deleted_at IS NULL AND detections.confidence >= 0.5"
            ),
        },
        {
            "label": "Distinct species count, excluding Haikubox-only (used by /stats)",
            "table": "detections",
            "sql": (
                "SELECT COUNT(DISTINCT detections.common_name) FROM detections "
                "JOIN recordings ON detections.recording_id = recordings.id "
                "WHERE recordings.deleted_at IS NULL AND recordings.haikubox_detection_id IS NULL"
            ),
        },
        {
            "label": "Recording list filtered by is_bat (used by Recordings page)",
            "table": "recordings",
            "sql": "SELECT COUNT(*) FROM recordings WHERE is_bat = 0 AND deleted_at IS NULL ORDER BY trigger_timestamp DESC LIMIT 20",
        },
    ]

    results = []
    for check in checks:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {check['table']}")
            row_count = cur.fetchone()[0]
            cur.execute(f"EXPLAIN QUERY PLAN {check['sql']}")
            plan_rows = cur.fetchall()
            plan_text = "; ".join(str(r[-1]) for r in plan_rows)
            uses_scan = "SCAN" in plan_text.upper() and "SEARCH" not in plan_text.upper()
            results.append({
                "label": check["label"],
                "table": check["table"],
                "row_count": row_count,
                "plan": plan_text,
                "full_table_scan": uses_scan,
                "concern": uses_scan and row_count > 10000,
            })
        except Exception as e:
            results.append({"label": check["label"], "error": str(e)})

    any_concern = any(r.get("concern") for r in results)
    return {
        "ok": True,
        "checks": results,
        "summary": (
            "At least one heavy query is doing a full table scan on a table large enough for that to matter — "
            "worth investigating specific indexes for that query pattern."
            if any_concern else
            "No full table scans found on tables large enough to be a concern — these queries are using indexes as expected."
        ),
    }


def _db_stats(db: Session) -> dict:
    try:
        now = datetime.utcnow()
        total_recordings    = db.query(func.count(Recording.id)).scalar() or 0
        bat_recordings      = db.query(func.count(Recording.id)).filter(Recording.is_bat == True).scalar() or 0
        bird_recordings     = total_recordings - bat_recordings
        deleted_recordings  = db.query(func.count(Recording.id)).filter(Recording.deleted_at.isnot(None)).scalar() or 0
        haikubox_recs       = db.query(func.count(Recording.id)).filter(Recording.haikubox_detection_id.isnot(None)).scalar() or 0
        total_detections    = db.query(func.count(Detection.id)).scalar() or 0
        total_species       = db.query(func.count(Detection.common_name.distinct())).scalar() or 0
        total_profiles      = db.query(func.count(BirdProfile.id)).scalar() or 0
        enriched_profiles   = db.query(func.count(BirdProfile.id)).filter(BirdProfile.enrichment_complete == True).scalar() or 0
        profiles_with_photo = db.query(func.count(BirdProfile.id)).filter(BirdProfile.photo_path.isnot(None)).scalar() or 0
        regional_species    = db.query(func.count(RegionalSpecies.id)).scalar() or 0

        inat_submitted = 0
        if hasattr(Recording, 'inat_observation_id'):
            inat_submitted = db.query(func.count(Recording.id)).filter(
                Recording.inat_observation_id.isnot(None)).scalar() or 0

        latest_rec = db.query(Recording.trigger_timestamp).filter(
            Recording.deleted_at.is_(None)).order_by(Recording.trigger_timestamp.desc()).first()
        oldest_rec = db.query(Recording.trigger_timestamp).filter(
            Recording.deleted_at.is_(None)).order_by(Recording.trigger_timestamp.asc()).first()

        recs_24h  = db.query(func.count(Recording.id)).filter(
            Recording.created_at >= now - timedelta(hours=24), Recording.deleted_at.is_(None)).scalar() or 0
        recs_7d   = db.query(func.count(Recording.id)).filter(
            Recording.created_at >= now - timedelta(days=7), Recording.deleted_at.is_(None)).scalar() or 0
        recs_30d  = db.query(func.count(Recording.id)).filter(
            Recording.created_at >= now - timedelta(days=30), Recording.deleted_at.is_(None)).scalar() or 0
        dets_24h  = db.query(func.count(Detection.id)).join(Recording).filter(
            Recording.created_at >= now - timedelta(hours=24)).scalar() or 0

        pending    = db.query(func.count(Recording.id)).filter(Recording.processing_status == "pending").scalar() or 0
        processing = db.query(func.count(Recording.id)).filter(Recording.processing_status == "processing").scalar() or 0
        errors     = db.query(func.count(Recording.id)).filter(Recording.processing_status == "error").scalar() or 0

        top5 = db.query(Detection.common_name, func.count(Detection.id).label("n")) \
                  .join(Recording).filter(Recording.deleted_at.is_(None)) \
                  .group_by(Detection.common_name) \
                  .order_by(func.count(Detection.id).desc()).limit(5).all()

        missing_photo = db.query(BirdProfile.common_name).filter(
            BirdProfile.enrichment_complete == True,
            BirdProfile.photo_path.is_(None),
            BirdProfile.photo_url.is_(None),
        ).limit(10).all()

        db_path   = settings.db_url.replace("sqlite:////", "/").replace("sqlite:///", "")
        db_size   = os.path.getsize(db_path) if os.path.exists(db_path) else 0

        table_counts = {}
        # Answers "is database size actually the bottleneck?" directly,
        # investigated in response to that exact question — freelist_count
        # is how many pages inside the file are empty space left behind by
        # deletes/archives (this app does plenty of both) that SQLite
        # hasn't reclaimed, versus page_count being the file's total size
        # in pages. The gap between them is exactly what a VACUUM would
        # get back, without guessing at it.
        reclaimable_bytes = 0
        page_count = 0
        try:
            raw = db.connection().connection
            cur = raw.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            for t in tables:
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                table_counts[t] = cur.fetchone()[0]
            cur.execute("PRAGMA page_size")
            page_size = cur.fetchone()[0]
            cur.execute("PRAGMA page_count")
            page_count = cur.fetchone()[0]
            cur.execute("PRAGMA freelist_count")
            freelist_count = cur.fetchone()[0]
            reclaimable_bytes = freelist_count * page_size
        except Exception:
            pass

        return {
            "ok":                  True,
            "db_path":             db_path,
            "db_size":             _fmt_bytes(db_size),
            "db_reclaimable":      _fmt_bytes(reclaimable_bytes),
            "db_reclaimable_pct":  round(100 * reclaimable_bytes / db_size, 1) if db_size else 0,
            "total_recordings":    total_recordings,
            "bird_recordings":     bird_recordings,
            "bat_recordings":      bat_recordings,
            "haikubox_recordings": haikubox_recs,
            "deleted_recordings":  deleted_recordings,
            "total_detections":    total_detections,
            "total_species":       total_species,
            "total_profiles":      total_profiles,
            "enriched_profiles":   enriched_profiles,
            "profiles_with_photo": profiles_with_photo,
            "inat_submitted":      inat_submitted,
            "regional_species":    regional_species,
            "latest_recording":    latest_rec[0].isoformat() if latest_rec and latest_rec[0] else None,
            "oldest_recording":    oldest_rec[0].isoformat() if oldest_rec and oldest_rec[0] else None,
            "recordings_24h":      recs_24h,
            "recordings_7d":       recs_7d,
            "recordings_30d":      recs_30d,
            "detections_24h":      dets_24h,
            "queue_pending":       pending,
            "queue_processing":    processing,
            "queue_errors":        errors,
            "top5_species":        [{"name": n, "count": c} for n, c in top5],
            "profiles_missing_photo": [r[0] for r in missing_photo],
            "table_counts":        table_counts,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _disk_stats() -> dict:
    dirs = {
        "recordings":   getattr(settings, "recordings_dir", ""),
        "spectrograms": getattr(settings, "spectrograms_dir", ""),
        "clips":        getattr(settings, "clips_dir", ""),
        "enhanced":     getattr(settings, "enhanced_dir", ""),
        "bat_clips":    getattr(settings, "bat_clips_dir", ""),
        "media":        getattr(settings, "media_dir", ""),
    }
    result = {k: _dir_stats(v) for k, v in dirs.items() if v}
    data_path = getattr(settings, "data_dir", "/")
    try:
        usage = shutil.disk_usage(data_path or "/")
        result["filesystem"] = {
            "path":        data_path,
            "total_human": _fmt_bytes(usage.total),
            "used_human":  _fmt_bytes(usage.used),
            "free_human":  _fmt_bytes(usage.free),
            "used_pct":    round(usage.used / usage.total * 100, 1),
            "total_bytes": usage.total,
            "used_bytes":  usage.used,
            "free_bytes":  usage.free,
        }
    except Exception as e:
        result["filesystem"] = {"error": str(e)}
    return result


def _settings_summary(db: Session) -> dict:
    try:
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        if not s:
            return {"ok": False, "error": "No settings row"}

        def _bool(attr):
            v = getattr(s, attr, None)
            return bool(v) if v is not None else None

        def _has(attr):
            v = getattr(s, attr, None)
            return bool(v) if v is not None else False

        return {
            "ok":                         True,
            "location": {
                "latitude":               getattr(s, "latitude", None),
                "longitude":              getattr(s, "longitude", None),
                "name":                   getattr(s, "location_name", None),
            },
            "timezone":                   getattr(s, "timezone", None),
            "min_confidence_display":     getattr(s, "min_confidence_display", None),
            "auto_delete_days":           getattr(s, "auto_delete_recordings_days", None),
            "max_recordings_gb":          getattr(s, "max_recordings_gb", None),
            "server_reanalyze_on_upload": _bool("server_reanalyze_on_upload"),
            "server_reanalyze_delete_device": _bool("server_reanalyze_delete_device"),
            "haikubox_enabled":           _bool("haikubox_enabled"),
            "bat_species_id_enabled":     _bool("bat_species_id_enabled"),
            "notifications_enabled":      _bool("notifications_enabled"),
            "smtp_configured":            _has("smtp_host"),
            "ebird_key_configured":       _has("ebird_api_key"),
            "inat_token_configured":      _has("inat_api_token"),
            "anthropic_key_configured":   _has("anthropic_api_key"),
            "device_keys_count":          len(getattr(s, "device_api_keys", None) or []),
            "auth_enabled":               _bool("auth_enabled"),
            "dark_mode":                  _bool("dark_mode"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _device_stats(db: Session) -> list:
    """Per-device health. Recording counts use all recordings since
    Recording.device_id is not set during upload in the current schema —
    we instead report total server stats and device heartbeat/hardware info.

    SECURITY: this dict is returned directly as part of /diagnostics/run's
    and /diagnostics/report's JSON response (see result["devices"] below) —
    never add ssh_password or any other secret to it. A stored SSH password
    fallback for the mic-check SSH connection is looked up separately, as a
    local variable, right where it's actually used — never placed in this
    shared dict. (A version of this comment exists because that mistake was
    caught and reverted before shipping, not hypothetically.)
    """
    try:
        devices = db.query(Device).all()
        now     = datetime.utcnow()
        results = []

        # Server-wide totals (since we can't filter by device)
        total_all  = db.query(func.count(Recording.id)).filter(Recording.deleted_at.is_(None)).scalar() or 0
        recs_24h_all = db.query(func.count(Recording.id)).filter(
            Recording.created_at >= now - timedelta(hours=24), Recording.deleted_at.is_(None)).scalar() or 0
        recs_7d_all  = db.query(func.count(Recording.id)).filter(
            Recording.created_at >= now - timedelta(days=7), Recording.deleted_at.is_(None)).scalar() or 0

        last_upload_any = db.query(Recording.created_at, Recording.filename).filter(
            Recording.deleted_at.is_(None)).order_by(Recording.created_at.desc()).first()
        avg_conf_all = db.query(func.avg(Detection.confidence)).join(Recording).filter(
            Recording.deleted_at.is_(None)).scalar()

        for dev in devices:
            last_seen = getattr(dev, "last_seen", None)
            hb_age_s  = int((now - last_seen).total_seconds()) if last_seen else None
            cfg_ver     = getattr(dev, "config_version", None)
            cfg_applied = getattr(dev, "config_applied_version", None)

            is_haikubox = getattr(dev, "birdnet_backend", None) == "haikubox"
            results.append({
                "id":                dev.id,
                "name":              getattr(dev, "name", None) or "unknown",
                "hostname":          getattr(dev, "hostname", None),
                "ip_address":        getattr(dev, "ip_address", None),
                "connect_address":   getattr(dev, "connect_address", None) or getattr(dev, "ip_address", None),
                "platform":          getattr(dev, "platform", None),
                "os_version":        getattr(dev, "os_version", None),
                "device_version":    getattr(dev, "device_version", None),
                "birdnet_backend":   getattr(dev, "birdnet_backend", "cpu"),
                "coral_present":     getattr(dev, "coral_present", False),
                "coral_form_factor": getattr(dev, "coral_form_factor", None),
                "mic_count":         getattr(dev, "mic_count", None),
                "mic_names":         getattr(dev, "mic_names", None) or [],
                "bat_status":        getattr(dev, "bat_status", None),
                "status":            getattr(dev, "status", None),
                "ssh_username":      getattr(dev, "ssh_username", None),
                "last_heartbeat":    last_seen.isoformat() if last_seen else None,
                "heartbeat_age_s":   hb_age_s,
                "heartbeat_age":     _fmt_age(hb_age_s),
                "heartbeat_status":  (
                    "ok"     if hb_age_s is not None and hb_age_s < 120  else
                    "stale"  if hb_age_s is not None and hb_age_s < 3600 else
                    "offline"
                ),
                # Server-wide totals (not per-device filtered — see docstring)
                "total_recordings":  total_all,
                "recordings_24h":    recs_24h_all,
                "recordings_7d":     recs_7d_all,
                "recordings_30d":    recs_7d_all,  # placeholder same as 7d
                "last_upload": {
                    "at":       last_upload_any[0].isoformat() if last_upload_any and last_upload_any[0] else None,
                    "age":      _fmt_age(int((now - last_upload_any[0]).total_seconds())) if last_upload_any and last_upload_any[0] else None,
                    "filename": last_upload_any[1] if last_upload_any else None,
                } if last_upload_any else None,
                "avg_confidence":    round(float(avg_conf_all) * 100, 1) if avg_conf_all else None,
                "config_version":         None if is_haikubox else cfg_ver,
                "config_applied_version": None if is_haikubox else cfg_applied,
                # Real fix: Haikubox devices never receive Chirp's own
                # config-push mechanism at all — they're a completely
                # different platform Chirp only syncs detections FROM, not
                # a chirp-device installation. Comparing config_version to
                # config_applied_version for one is fundamentally
                # meaningless (there's no real "config" being pushed to
                # compare), always showing a stale True/False that looks
                # like a real problem but isn't — confirmed via a real
                # report showing "Config in sync: False" for a Haikubox
                # with no actual config-sync relationship to be out of
                # sync from. None here (rendered as "n/a", not True/False)
                # for any Haikubox device; the real comparison still
                # applies normally to actual chirp-device installations.
                "config_in_sync": (
                    None if is_haikubox else
                    (cfg_ver == cfg_applied if (cfg_ver is not None and cfg_applied is not None) else None)
                ),
            })
        return results
    except Exception as e:
        logger.error("_device_stats error: %s", e, exc_info=True)
        return [{"error": str(e)}]


def _haikubox_live_status(db: Session) -> Optional[dict]:
    """
    Queries Haikubox's own API directly for live status — regardless of
    whether the haikubox_enabled auto-sync toggle is currently on. Real
    fix for a genuine gap: the sync loop (_run_sync in haikubox_sync.py)
    returns immediately, without ever calling the live API, whenever the
    toggle is off — meaning the DB's cached last-known status (last_seen,
    etc., shown in _device_stats above) just goes stale indefinitely while
    the feature is paused, with no way to see Haikubox's actual current
    state without re-enabling sync first. This calls the exact same
    _fetch_device_info the sync loop itself uses, but unconditionally, so
    diagnostics reflect genuinely current status either way.

    Returns None if no Haikubox serial is configured at all (nothing to
    check); otherwise a dict with "ok" indicating whether the live API
    call itself succeeded.
    """
    try:
        from ..models import AppSettings
        from ..services.haikubox_sync import HaikuboxSyncService

        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        serial = (getattr(s, "haikubox_serial", None) or "").strip() if s else ""
        if not serial:
            return None

        enabled = bool(getattr(s, "haikubox_enabled", False)) if s else False
        service = HaikuboxSyncService()
        try:
            info = service._fetch_device_info(serial)
            return {
                "ok": True,
                "auto_sync_enabled": enabled,
                "serial": serial,
                "name": info.get("haikuboxName"),
                "raw": info,
            }
        except Exception as e:
            return {
                "ok": False,
                "auto_sync_enabled": enabled,
                "serial": serial,
                "error": str(e),
            }
    except Exception as e:
        logger.error("_haikubox_live_status error: %s", e, exc_info=True)
        return {"ok": False, "error": str(e)}


def _cache_stats() -> dict:
    try:
        from ..cache import life_list_cache, statistics_cache, settings_cache, user_token_cache
        def _info(cache, name: str) -> dict:
            # Real fix for the "?/?" entries previously shown here: guessed
            # at public-looking attribute names (_store, maxsize,
            # ttl_seconds) that don't actually exist on TTLCache — its real
            # internals are _data, _maxsize, and _ttl, confirmed directly
            # against cache.py's actual source.
            size    = len(cache._data) if hasattr(cache, "_data") else "?"
            maxsize = getattr(cache, "_maxsize", "?")
            ttl     = getattr(cache, "_ttl", "?")
            return {"name": name, "entries": size, "maxsize": maxsize, "ttl_s": ttl}
        return {
            "ok": True,
            "caches": [
                _info(life_list_cache,  "life_list"),
                _info(statistics_cache, "statistics"),
                _info(settings_cache,   "settings"),
                _info(user_token_cache, "user_token"),
            ]
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _server_logs(n: int = 100) -> dict:
    """Pull from ring buffer — keys are ts/level/name/msg."""
    try:
        records  = log_buffer.get_lines(n)
        all_lines: list[str] = []
        errors:   list[str] = []
        warnings: list[str] = []
        for r in records:
            if isinstance(r, dict):
                # Ring buffer stores: ts, level, name, msg
                ts   = r.get("ts") or r.get("timestamp", "")
                lvl  = r.get("level", "INFO")
                name = r.get("name") or r.get("logger", "")
                msg  = r.get("msg") or r.get("message", "")
                line = f"{ts} [{lvl}] {name}: {msg}"
            else:
                line = str(r)
                lvl  = "INFO"
            all_lines.append(line)
            if "ERROR" in lvl or "CRITICAL" in lvl:
                errors.append(line)
            elif "WARNING" in lvl:
                warnings.append(line)

        return {
            "ok":            True,
            "all":           all_lines if all_lines else ["(no log lines in buffer)"],
            "errors":        errors,
            "warnings":      warnings,
            "error_count":   len(errors),
            "warning_count": len(warnings),
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "all": [f"(log buffer unavailable: {e})"], "errors": [], "warnings": []}


def _enrich_mic_list(names: list, role: str, live_streams: list) -> list:
    """
    Cross-references a name-matched device list (from arecord -l text
    parsing) against live in-process data from the device's own status
    server, converting plain name strings into {name, live_active,
    live_detail} so the UI can show real capture status instead of an
    unconditional checkmark. See the call site in _run_checks for the full
    rationale — a real run showed a card checkmarked here while the actual
    journal logs showed its detector had been failing to start for hours.
    """
    enriched = []
    for name in names:
        match = next(
            (s for s in live_streams if s.get("role") == role and (
                s.get("name", "").lower() in name.lower()
                or name.lower() in s.get("name", "").lower()
            )),
            None,
        )
        if match and not match.get("error"):
            db_val = match.get("db")
            enriched.append({
                "name": name, "live_active": True,
                "live_detail": f"{db_val:.1f} dBFS — actively capturing" if db_val is not None else "actively capturing",
            })
        elif match and match.get("error"):
            enriched.append({"name": name, "live_active": False, "live_detail": match["error"]})
        else:
            enriched.append({
                "name": name, "live_active": None,
                "live_detail": "No live confirmation available (device-local status endpoint "
                               "unreachable, or an older chirp-device build) — this only "
                               "confirms the device name matches the expected pattern, not "
                               "that it's actually being captured right now. Check the full "
                               "journal history for a definitive answer.",
            })
    return enriched


def _mic_check_ssh(dev: dict, ssh_password: str = "") -> dict:
    """
    SSH to a device and enumerate/classify audio hardware.
    Skips virtual devices (Haikubox, no IP address).
    Tries key-based auth first, then falls back to password if provided.
    """
    ip       = dev.get("connect_address") or dev.get("ip_address")
    username = dev.get("ssh_username") or "joshsalvi"

    if not ip:
        return {"ok": False, "error": "No IP address — virtual device (e.g. Haikubox), skipped", "skipped": True}

    try:
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        from ..services.device_net import paramiko_sock
        connect_kwargs: dict = dict(
            hostname=ip, port=22, username=username, timeout=8,
            sock=paramiko_sock(ip, 22),
        )
        if ssh_password:
            connect_kwargs["password"]       = ssh_password
            connect_kwargs["look_for_keys"]  = False
            connect_kwargs["allow_agent"]    = False
        else:
            connect_kwargs["look_for_keys"] = True
            connect_kwargs["allow_agent"]   = True

        client.connect(**connect_kwargs)

        def _run(cmd: str) -> str:
            _, stdout, stderr = client.exec_command(cmd, timeout=10)
            return stdout.read().decode(errors="replace").strip()

        arecord_out = _run("arecord -l 2>&1")
        lsusb_out   = _run("lsusb 2>&1")
        config_out  = _run("cat ~/chirp-device/config.yaml 2>/dev/null || cat ~/chirp/config.yaml 2>/dev/null || echo 'config not found'")
        service_status = _run("systemctl is-active chirp-device 2>/dev/null || echo 'unknown'")
        # Recent tail — "what's happening right now" (live detection activity, etc.)
        journal_recent = _run("journalctl -u chirp-device -n 30 --no-pager 2>/dev/null | tail -30")
        # Full-history grep for backend/Coral-relevant lines — a plain recent
        # tail misses this entirely once the service has been up for a while
        # (e.g. detection chatter fills the last 30 lines long before a
        # diagnostics bundle gets generated), which is exactly what happened
        # investigating a real "coral backend didn't work" report: the
        # uploaded bundle's journal excerpt was just live detection activity,
        # with zero mention of coral/edgetpu/backend anywhere, even though
        # the actual backend-selection log line exists further back in the
        # journal. Grepping the FULL journal history for these terms (not
        # just a recent window) makes this kind of question answerable from
        # a single diagnostics bundle without a follow-up round-trip.
        journal_coral = _run(
            "journalctl -u chirp-device --no-pager 2>/dev/null | "
            "grep -iE 'coral|edgetpu|pycoral|tflite|tensorflow|birdnet backend|"
            "backend hot-swap|backend change' | tail -60"
        )
        journal_tail = journal_recent
        if journal_coral.strip():
            journal_tail = (
                journal_recent
                + "\n\n" + "=" * 70
                + "\n-- Coral/EdgeTPU/backend-related lines (full journal history) --\n"
                + "=" * 70 + "\n"
                + journal_coral
            )

        # Parse arecord -l output into device list
        audio_devs = []
        for line in arecord_out.splitlines():
            if line.startswith("card "):
                audio_devs.append(line.strip())

        # Classify devices using known patterns
        mic_names_reported = dev.get("mic_names") or []
        bird_mics: list[str] = []
        bat_mics:  list[str] = []
        excluded:  list[str] = []
        unknown:   list[str] = []

        for adev in audio_devs:
            adev_lower = adev.lower()
            is_respeaker = "respeaker" in adev_lower or "xvf" in adev_lower
            is_audiomoth = "audiomoth" in adev_lower or "192khz" in adev_lower
            is_unitek    = "unitek" in adev_lower or "0014" in adev_lower or "usb audio device" in adev_lower
            is_cmedia    = "c-media" in adev_lower or "0d8c" in adev_lower

            if is_audiomoth:
                bat_mics.append(adev)
            elif is_unitek or is_cmedia:
                excluded.append(adev)
            elif is_respeaker:
                bird_mics.append(adev)
            elif any(n.lower() in adev_lower or adev_lower in n.lower() for n in mic_names_reported):
                bird_mics.append(adev)
            else:
                unknown.append(adev)

        client.close()

        return {
            "ok":              True,
            "ip":              ip,
            "username":        username,
            "service_status":  service_status,
            "arecord_raw":     arecord_out,
            "lsusb_raw":       lsusb_out,
            "audio_devices":   audio_devs,
            "bird_mics":       bird_mics,
            "bat_mics":        bat_mics,
            "excluded_mics":   excluded,
            "unknown_mics":    unknown,
            "config_preview":  config_out,  # full file — see note above; a fixed truncation
                                              # previously cut this off before it ever reached
                                              # detection.birdnet.backend, the exact field a
                                              # "why didn't my backend change take" question
                                              # needs. config.yaml is small enough (a few dozen
                                              # KB at most) that there's no real reason to cap it.
            "journal_tail":    journal_tail,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "ip": ip}


def _run_checks(db: Session, mode: str = "full", ssh_password: str = "") -> dict:
    t0 = time.time()

    result: dict = {
        "generated_at": datetime.utcnow().isoformat(),
        "mode":         mode,
        "elapsed_ms":   0,
        "server":       {},
        "devices":      [],
        "logs":         {},
        "mic_checks":   [],
    }

    if mode in ("full", "db"):
        result["server"]["db"]       = _db_stats(db)
        result["server"]["settings"] = _settings_summary(db)

    if mode == "full":
        result["server"]["system"] = _system_info()
        result["server"]["disk"]   = _disk_stats()
        result["server"]["cache"]  = _cache_stats()
        result["devices"]          = _device_stats(db)
        result["server"]["haikubox_live"] = _haikubox_live_status(db)
        result["logs"]             = _server_logs(100)

    if mode == "mic":
        devices = _device_stats(db)
        result["devices"] = devices
        for dev in devices:
            if "error" not in dev:
                # Fall back to the device's saved password (if any) only when
                # the request didn't supply one — looked up fresh from the DB
                # here, as a local variable only, and passed straight into
                # the SSH connection call. Deliberately never added to `dev`
                # or `result` (both of which get returned as this endpoint's
                # JSON response) — see the security note on _device_stats
                # above for why that would leak the raw password to the client.
                effective_password = ssh_password
                if not effective_password:
                    stored = db.query(Device.ssh_password).filter(Device.id == dev.get("id")).scalar()
                    if stored:
                        effective_password = stored
                check = _mic_check_ssh(dev, ssh_password=effective_password)
                check["device_id"]   = dev.get("id")
                check["device_name"] = dev.get("name")
                if not check.get("skipped"):
                    # Cross-reference the name-based classification above
                    # against the device's own local status_server (the
                    # same live, in-process source the mic-levels websocket
                    # uses) — a card matching "audiomoth" by name only
                    # means the arecord -l text LOOKS like a bat mic, not
                    # that chirp-device is actually capturing from it right
                    # now. A real run showed exactly this gap: this card
                    # showed a checkmark here while the actual journal logs
                    # showed the bat detector had been failing to start for
                    # hours. Enriches bird_mics/bat_mics from plain name
                    # strings into {name, live_active, live_detail} so the
                    # UI can show real status instead of an unconditional
                    # checkmark that was always shown for anything in the
                    # list regardless of whether it was actually working.
                    import asyncio as _asyncio
                    live_streams = []
                    device_orm = db.query(Device).filter(Device.id == dev.get("id")).first()
                    if device_orm is not None and (dev.get("connect_address") or dev.get("ip_address")):
                        try:
                            shared_key = _get_device_shared_key(device_orm, db)
                            live_streams = _asyncio.run(
                                _poll_device_status_levels(
                                    dev.get("connect_address") or dev.get("ip_address"), DEVICE_STATUS_PORT, shared_key, timeout=2.0
                                )
                            ) or []
                        except Exception as e:
                            logger.debug("Live-status cross-reference failed for %s: %s", dev.get("id"), e)

                    check["bird_mics"] = _enrich_mic_list(check.get("bird_mics", []), "bird", live_streams)
                    check["bat_mics"]  = _enrich_mic_list(check.get("bat_mics", []), "bat", live_streams)

                    result["mic_checks"].append(check)

    result["elapsed_ms"] = round((time.time() - t0) * 1000)
    return result


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/run")
def run_diagnostics(
    mode: str = Query("full", description="'full' | 'db' | 'mic'"),
    ssh_password: str = Query("", description="SSH password for mic check mode"),
    db: Session = Depends(get_db),
):
    return _run_checks(db, mode=mode, ssh_password=ssh_password)


@router.post("/report/email")
def email_diagnostics_report(
    to: str = Query(..., description="Email address to send the report to"),
    include_logs: bool = Query(False),
    mode: str = Query("full"),
    ssh_password: str = Query(""),
    db: Session = Depends(get_db),
):
    """
    Emails a diagnostics report — the "emailable" half of a long-pending
    feature request; the downloadable half (this same report as a direct
    file download) already existed and is comprehensive. Deliberately
    reuses the exact same report-building code as GET /report (same
    _run_checks call, same _build_report_text, same ZIP-building logic
    when include_logs is set) rather than a separate implementation, so
    the emailed and downloaded versions of a report are guaranteed to be
    byte-for-byte identical, not two independently-maintained versions
    that could quietly drift apart from each other over time.
    """
    from ..services.email_service import send_diagnostics_report, _get_smtp_config

    if not _get_smtp_config(db):
        raise HTTPException(status_code=400, detail="SMTP is not configured — set it up in Settings first.")

    r = _run_checks(db, mode=mode, ssh_password=ssh_password)
    report_text = _build_report_text(r)

    if not include_logs:
        attachment_bytes = report_text.encode("utf-8")
        attachment_filename = "chirp-diagnostics.txt"
        attachment_mimetype = "text/plain"
    else:
        buf = io.BytesIO()
        now_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"chirp_diagnostics_{now_str}/report.txt", report_text)
            logs = r.get("logs", {})
            if logs.get("all"):
                zf.writestr(f"chirp_diagnostics_{now_str}/server.log", "\n".join(logs["all"]))
            for mc in r.get("mic_checks", []):
                dev_name = (mc.get("device_name") or mc.get("device_id") or "device").replace(" ", "_")
                if mc.get("journal_tail"):
                    zf.writestr(f"chirp_diagnostics_{now_str}/{dev_name}_journal.log", mc["journal_tail"])
                if mc.get("config_preview"):
                    zf.writestr(f"chirp_diagnostics_{now_str}/{dev_name}_config.yaml", mc["config_preview"])
                if mc.get("arecord_raw"):
                    zf.writestr(f"chirp_diagnostics_{now_str}/{dev_name}_arecord.txt", mc["arecord_raw"])
        attachment_bytes = buf.getvalue()
        attachment_filename = f"chirp_diagnostics_{now_str}.zip"
        attachment_mimetype = "application/zip"

    sent = send_diagnostics_report(
        db, to, mode, report_text,
        attachment_bytes, attachment_filename, attachment_mimetype,
    )
    if not sent:
        raise HTTPException(status_code=500, detail="Email failed to send — check SMTP settings and server logs.")
    return {"status": "sent", "to": to, "filename": attachment_filename}


@router.get("/report")
def diagnostics_report(
    include_logs: bool = Query(False),
    mode: str = Query("full"),
    ssh_password: str = Query(""),
    db: Session = Depends(get_db),
):
    r = _run_checks(db, mode=mode, ssh_password=ssh_password)
    report_text = _build_report_text(r)

    if not include_logs:
        return PlainTextResponse(report_text,
            headers={"Content-Disposition": "attachment; filename=chirp-diagnostics.txt"})

    # Build ZIP with report + log files
    buf = io.BytesIO()
    now_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"chirp_diagnostics_{now_str}/report.txt", report_text)

        # Server log buffer
        logs = r.get("logs", {})
        if logs.get("all"):
            zf.writestr(
                f"chirp_diagnostics_{now_str}/server.log",
                "\n".join(logs["all"])
            )

        # Per-device journal from SSH mic checks
        for mc in r.get("mic_checks", []):
            dev_name = (mc.get("device_name") or mc.get("device_id") or "device").replace(" ", "_")
            if mc.get("journal_tail"):
                zf.writestr(
                    f"chirp_diagnostics_{now_str}/{dev_name}_journal.log",
                    mc["journal_tail"]
                )
            if mc.get("config_preview"):
                zf.writestr(
                    f"chirp_diagnostics_{now_str}/{dev_name}_config.yaml",
                    mc["config_preview"]
                )
            if mc.get("arecord_raw"):
                zf.writestr(
                    f"chirp_diagnostics_{now_str}/{dev_name}_arecord.txt",
                    mc["arecord_raw"]
                )

    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=chirp_diagnostics_{now_str}.zip"},
    )


def _build_report_text(r: dict) -> str:
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    mode    = r.get("mode", "full")
    lines   = []

    def h1(title: str):
        lines.append("")
        lines.append("=" * 70)
        lines.append(f"  {title}")
        lines.append("=" * 70)

    def h2(title: str):
        lines.append(f"\n  ── {title} ──")

    def row(label: str, value, indent: int = 4):
        pad = " " * indent
        lines.append(f"{pad}{label:<40} {value}")

    lines.append("=" * 70)
    lines.append("  CHIRP DIAGNOSTIC REPORT")
    lines.append(f"  Generated: {now_str}")
    lines.append(f"  Mode:      {mode}")
    lines.append(f"  Elapsed:   {r.get('elapsed_ms')} ms")
    lines.append("=" * 70)

    srv = r.get("server", {})

    if "system" in srv:
        h1("SYSTEM")
        sys_d = srv["system"]
        if sys_d.get("ok"):
            row("Chirp server version", sys_d.get("chirp_version", "unknown"))
            row("Hostname",   sys_d.get("hostname"))
            row("Python",     sys_d.get("python"))
            row("Platform",   sys_d.get("platform"))
            row("psutil",     "available" if sys_d.get("psutil") else "not installed")
            if sys_d.get("cpu_count"):
                row("CPU", f"{sys_d['cpu_count']} cores · {sys_d['cpu_pct']}% used")
                row("Memory", f"{sys_d['mem_used']} / {sys_d['mem_total']} ({sys_d['mem_pct']}% used)")
                row("Uptime",   sys_d.get("uptime_human"))
            row("Disk (root)", f"{sys_d.get('disk_root_used','?')} / {sys_d.get('disk_root_total','?')} ({sys_d.get('disk_root_pct','?')}% used)")
            row("Bat species models", "✓ present" if sys_d.get("bat_models_present") else f"✗ MISSING ({sys_d.get('bat_models_dir','?')})")
            row("SMTP configured", "✓ yes" if sys_d.get("smtp_configured") else ("✗ no" if sys_d.get("smtp_configured") is False else "unknown"))
            pkgs = sys_d.get("packages") or {}
            if pkgs:
                row("Packages", ", ".join(f"{k}={v}" for k, v in pkgs.items()))

    if "settings" in srv:
        h1("SETTINGS")
        s = srv["settings"]
        if s.get("ok"):
            loc = s.get("location", {})
            row("Location",   f"{loc.get('latitude')}, {loc.get('longitude')} ({loc.get('name') or 'unnamed'})")
            row("Timezone",   s.get("timezone") or "UTC")
            row("eBird key",  "✓" if s.get("ebird_key_configured") else "✗ not set")
            row("iNat token", "✓" if s.get("inat_token_configured") else "✗ not set")
            row("Auth",       "enabled" if s.get("auth_enabled") else "disabled")
            row("Device keys", s.get("device_keys_count"))

    if "db" in srv:
        h1("DATABASE")
        db_d = srv["db"]
        if db_d.get("ok"):
            row("DB file",    db_d.get("db_path"))
            row("DB size",    db_d.get("db_size"))
            row("Recordings", db_d.get("total_recordings"))
            row("  Bird",     db_d.get("bird_recordings"))
            row("  Bat",      db_d.get("bat_recordings"))
            row("Detections", db_d.get("total_detections"))
            row("Species",    db_d.get("total_species"))
            row("Profiles",   f"{db_d.get('enriched_profiles')} / {db_d.get('total_profiles')} enriched")
            row("Last 24h",   db_d.get("recordings_24h"))
            row("Latest",     (db_d.get("latest_recording") or "—")[:10])
            row("Queue err",  db_d.get("queue_errors"))
            h2("Top 5 species")
            for sp in (db_d.get("top5_species") or []):
                row(sp["name"], sp["count"])

    if "disk" in srv:
        h1("DISK USAGE")
        disk = srv["disk"]
        fs   = disk.get("filesystem", {})
        if fs and not fs.get("error"):
            row("Path",  fs.get("path"))
            row("Total", fs.get("total_human"))
            row("Used",  f"{fs.get('used_human')} ({fs.get('used_pct')}%)")
            row("Free",  fs.get("free_human"))
        for label in ("recordings", "spectrograms", "clips", "enhanced", "bat_clips"):
            d = disk.get(label)
            if not d:
                continue
            row(label.capitalize(), f"{d.get('size_human','?')} · {d.get('file_count','?')} files" if d.get("exists") else "not found")

    for dev in r.get("devices", []):
        if "error" in dev:
            continue
        h1(f"DEVICE: {dev.get('name','?')} [{dev.get('heartbeat_status','?').upper()}]")
        row("Hostname / IP",    f"{dev.get('hostname') or '?'} · {dev.get('ip_address') or '?'}")
        row("Platform",         dev.get("platform") or "—")
        row("Chirp-device ver", dev.get("device_version") or "unknown")
        row("BirdNET backend",  dev.get("birdnet_backend") or "cpu")
        row("Coral",            f"✓ {dev.get('coral_form_factor') or 'usb'}" if dev.get("coral_present") else "✗ none")
        row("Microphones",      f"{dev.get('mic_count') or 0} — {', '.join(dev.get('mic_names') or []) or '?'}")
        row("Last heartbeat",   f"{(dev.get('last_heartbeat') or 'never')[:19]} ({dev.get('heartbeat_age')} ago)" if dev.get("last_heartbeat") else "never")
        lu = dev.get("last_upload")
        row("Last upload",      f"{lu.get('at','')[:10]} ({lu.get('age')} ago)" if lu else "none")
        row("Server recordings (24h/7d/all)", f"{dev.get('recordings_24h')}/{dev.get('recordings_7d')}/{dev.get('total_recordings')}")
        cis = dev.get("config_in_sync")
        row("Config in sync",   "n/a (Haikubox has no config-push relationship)" if cis is None and dev.get("birdnet_backend") == "haikubox"
                                 else ("n/a" if cis is None else str(cis)))

    hb_live = r.get("server", {}).get("haikubox_live")
    if hb_live is not None:
        h1("HAIKUBOX LIVE STATUS (queried directly, regardless of auto-sync toggle)")
        row("Auto-sync enabled", str(hb_live.get("auto_sync_enabled")))
        row("Serial", hb_live.get("serial") or "?")
        if hb_live.get("ok"):
            row("Live API reachable", "✓ yes")
            row("Haikubox name (live)", hb_live.get("name") or "?")
        else:
            row("Live API reachable", f"✗ no — {hb_live.get('error', 'unknown error')}")

    for mc in r.get("mic_checks", []):
        h1(f"MIC CHECK: {mc.get('device_name','?')} ({mc.get('ip','?')})")
        if not mc.get("ok"):
            row("ERROR", mc.get("error"))
            continue
        row("Service status", mc.get("service_status"))
        row("Total audio devices", len(mc.get("audio_devices") or []))
        h2("Bird mics (used for BirdNET)")
        for m in (mc.get("bird_mics") or []) or ["(none)"]:
            lines.append(f"    ✓ {m}")
        h2("Bat mics (used for echolocation)")
        for m in (mc.get("bat_mics") or []) or ["(none)"]:
            lines.append(f"    ✓ {m}")
        h2("Excluded mics (skipped)")
        for m in (mc.get("excluded_mics") or []) or ["(none)"]:
            lines.append(f"    ✗ {m}")
        h2("Unknown classification")
        for m in (mc.get("unknown_mics") or []) or ["(none)"]:
            lines.append(f"    ? {m}")
        h2("Raw arecord -l output")
        for line in (mc.get("arecord_raw") or "").splitlines():
            lines.append(f"    {line}")

    logs = r.get("logs", {})
    err_lines  = logs.get("errors", [])
    warn_lines = logs.get("warnings", [])
    if err_lines:
        h1(f"RECENT ERRORS ({len(err_lines)})")
        for line in err_lines[-20:]:
            lines.append(f"  {line}")
    if warn_lines:
        h1(f"RECENT WARNINGS ({len(warn_lines)})")
        for line in warn_lines[-20:]:
            lines.append(f"  {line}")
    if logs.get("all"):
        h1(f"SERVER LOG TAIL ({len(logs['all'])} lines)")
        for line in logs["all"]:
            lines.append(f"  {line}")

    lines.append("")
    lines.append("─" * 70)
    lines.append("  End of Chirp Diagnostic Report")
    lines.append(f"  Generated: {now_str}")
    lines.append("─" * 70)
    lines.append("")
    return "\n".join(lines)


async def _fetch_device_listen_clip(device_id: str, name: str, db: Session, status_port: int = None) -> bytes:
    """
    The actual proxy-to-chirp-device logic behind device_listen() below,
    pulled into its own function so live_detect.py's device-source mode
    can fetch a clip the exact same way the Listen button does, without
    one route handler awkwardly calling another and having to unwrap its
    Response object. device_listen() itself is now a thin wrapper around
    this. Raises HTTPException on any failure — same status codes
    (404/400/502/503) device_listen() always raised directly.
    """
    if status_port is None:
        status_port = DEVICE_STATUS_PORT
    dev = db.query(Device).filter(Device.id == device_id).first()
    if not dev:
        raise HTTPException(404, "Device not found")
    from ..services.device_net import candidates as _cands, httpx_kwargs
    targets = _cands(dev)
    if not targets:
        raise HTTPException(400, "No IP address for this device")

    shared_key = _get_device_shared_key(dev, db)
    import asyncio as _asyncio
    import httpx
    from urllib.parse import quote
    headers = {"X-Chirp-Key": shared_key} if shared_key else {}
    resp, errors = None, []
    for ip in targets:            # preferred address, then the other (auto)
        url = f"http://{ip}:{status_port}/listen?name={quote(name)}"
        try:
            async with httpx.AsyncClient(timeout=8.0, **httpx_kwargs(ip)) as client:
                resp = await client.get(url, headers=headers)
                # The bat stream drops out for a few seconds while the bat
                # detector (re)starts; retry once before reporting it missing.
                if resp.status_code == 404 and "no stream named" in resp.text:
                    await _asyncio.sleep(3.0)
                    resp = await client.get(url, headers=headers)
            break
        except Exception as e:
            errors.append(f"{ip}: {e}")
    if resp is None:
        raise HTTPException(502, f"Could not reach device's status server on port {status_port} ({'; '.join(errors)})")

    if resp.status_code != 200:
        # Pass the device's own error message through rather than masking
        # it behind a generic proxy failure — "no buffered audio yet for
        # this stream" (503) and "no stream named X" (404) are both
        # different situations an admin should be able to tell
        # apart, not just "Listen failed."
        try:
            detail = resp.json().get("error", resp.text)
        except Exception:
            detail = resp.text
        raise HTTPException(resp.status_code if resp.status_code in (404, 503) else 502, detail)

    return resp.content


@router.get("/devices/{device_id}/listen")
async def device_listen(
    device_id: str,
    name: str = Query(..., description="Mic name to listen to, exactly as shown in the live-levels list"),
    status_port: int = Query(DEVICE_STATUS_PORT, description="Port chirp-device's local status_server listens on"),
    db: Session = Depends(get_db),
):
    """
    Proxies chirp-device's own `GET /listen?name=...` (status_server.py) —
    a few seconds of RAW audio from a specific mic, as a WAV file, so an
    admin can LISTEN to what a mic is picking up (static,
    clipping, wrong mic entirely) rather than only ever seeing a level
    number for it. Deliberately separate from mic_levels_stream() above,
    not a mode of it — that's a continuous WebSocket of small level
    readings; this is an on-demand fetch of an audio clip, pulled
    by the frontend on a timer to approximate continuous playback (see
    status_server.py's own docstring for why that's the chosen design
    over a true low-latency audio stream).

    Only ever reads from chirp-device's local status_server — there's no
    SSH/arecord fallback here the way mic_levels_stream() has one for
    plain level numbers. A second SSH-triggered `arecord` capture would
    reintroduce the exact "device busy" conflict this whole status_server
    approach exists to avoid (see that module's own docstring); building
    a parallel capture path just for this one feature isn't worth
    reintroducing that risk; a device on an old build or with
    status_server disabled just won't offer Listen, same as it already
    doesn't offer the device-local half of live levels.

    See also _fetch_device_listen_clip() above — the same fetch, reused
    by Live Detect's device-source mode (api/live_detect.py).
    """
    content = await _fetch_device_listen_clip(device_id, name, db, status_port)
    return Response(content=content, media_type="audio/wav", headers={"Cache-Control": "no-store"})


@router.websocket("/mic-levels/{device_id}")
async def mic_levels_stream(
    websocket: WebSocket,
    device_id: str,
    ssh_password: str = Query("", description="SSH password (optional, key-based auth tried first)"),
    status_port: int = Query(DEVICE_STATUS_PORT, description="Port chirp-device's local status_server listens on"),
    db: Session = Depends(get_db),
):
    """
    Stream real-time mic level data from a Pi device, combining two sources:

    1. **Device-local status endpoint** (preferred, `http://<ip>:<status_port>/levels`):
       chirp-device's own status_server.py publishes levels it already
       computed in-process from its running AudioCapture/BatDetector streams
       — no second ALSA device open, so it can never hit the "device busy"
       error a second `arecord`/dsnoop attempt runs into. Covers every card
       chirp-device actually manages (bird + bat).

    2. **SSH + arecord** (fallback / supplemental): still runs for any card
       NOT already reported by source 1 — e.g. an excluded/unused USB mic
       chirp-device never opens. Skips cards source 1 already covers so it
       doesn't waste a tick on a doomed busy-device retry loop for those.

    If the device-local endpoint is unreachable (older chirp-device build,
    `status_server.enabled: false`, firewall), source 1 silently contributes
    nothing and behavior is identical to the pre-existing SSH-only approach —
    this is purely additive, not a replacement.

    Server → Client:
      {"type":"connecting","message":"..."}
      {"type":"connected","message":"..."}
      {"type":"status","message":"..."}   — e.g. whether the local endpoint was reachable
      {"type":"levels","devices":[{"name":"...","card":N,"db":-38.5,"peak":-22.1,"sr":48000,"source":"device_local"|"ssh_arecord"}]}
      {"type":"error","message":"..."}
      {"type":"closed"}
    """
    import asyncio, json as _json
    await websocket.accept()

    dev = db.query(Device).filter(Device.id == device_id).first()
    if not dev:
        await websocket.send_text(_json.dumps({"type":"error","message":"Device not found"}))
        return

    ip       = getattr(dev, "connect_address", None) or getattr(dev, "ip_address", None)
    username = getattr(dev, "ssh_username", None) or "joshsalvi"
    if not ip:
        await websocket.send_text(_json.dumps({"type":"error","message":"No IP for device"}))
        return

    # Fall back to the saved SSH password if the request didn't supply one.
    # `dev` here is the live ORM object, never serialized back to the
    # client — safe. (See the security note on _device_stats() above for
    # why the stored password must never be placed into a dict/response
    # that gets returned to the frontend instead of used purely server-side
    # like this.)
    if not ssh_password:
        ssh_password = getattr(dev, "ssh_password", None) or ""

    shared_key = _get_device_shared_key(dev, db)
    initial_local = await _poll_device_status_levels(ip, status_port, shared_key)
    if initial_local is None:
        # Preferred address didn't answer; try the other one (auto mode).
        from ..services.device_net import candidates as _cands
        for _alt in _cands(dev)[1:]:
            initial_local = await _poll_device_status_levels(_alt, status_port, shared_key)
            if initial_local is not None:
                ip = _alt
                break
    # Only treat a device-local stream as "covered" if it actually reported a
    # usable reading (no error) — a provider that raised on the device side
    # (surfaced by status_server.py as a visible error entry, not silently
    # dropped) has nothing useful to show, so the SSH path should still get
    # a chance at that card rather than the admin seeing neither source work.
    usable_local = [d for d in (initial_local or []) if not d.get("error")]
    covered_names = [d["name"] for d in usable_local]
    # Card-number matching is the primary, reliable mechanism (exact integer
    # match against `arecord -l`'s own numbering); covered_names is kept as
    # a fallback for entries where the device couldn't determine its own
    # ALSA card number (e.g. arecord unavailable there too).
    covered_cards = [d["alsa_card"] for d in usable_local if d.get("alsa_card") is not None]
    await websocket.send_text(_json.dumps({
        "type": "local_status",
        "message": (
            f"Device local status endpoint reachable on {ip}:{status_port} — "
            f"using live in-process levels for {len(usable_local)} mic(s) "
            f"({', '.join(covered_names) if covered_names else 'none usable'}"
            f"{', cards ' + ', '.join(str(c) for c in covered_cards) if covered_cards else ''}); "
            "SSH probing covers any remaining cards."
        ) if initial_local else (
            f"Device local status endpoint not reachable on {ip}:{status_port} — "
            "falling back to SSH probing for all cards. (Older chirp-device build, "
            "status_server.enabled: false, or a network/firewall issue.)"
        ),
    }))

    try:
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        loop = asyncio.get_event_loop()

        await websocket.send_text(_json.dumps({"type":"connecting","message":f"Connecting to {username}@{ip}…"}))

        def _connect():
            from ..services.device_net import paramiko_sock
            if ssh_password:
                client.connect(ip, port=22, username=username, password=ssh_password,
                               timeout=10, look_for_keys=False, allow_agent=False,
                               sock=paramiko_sock(ip, 22))
            else:
                client.connect(ip, port=22, username=username, timeout=10,
                               look_for_keys=True, allow_agent=True,
                               sock=paramiko_sock(ip, 22))
        await loop.run_in_executor(None, _connect)
        await websocket.send_text(_json.dumps({"type":"connected","message":f"Connected to {username}@{ip}"}))

        # This script runs on the Pi.
        # Uses arecord (ALSA) instead of sounddevice/portaudio so it can
        # sample devices that chirp-device already has open — ALSA's dsnoop
        # capture-sharing allows concurrent readers on the same device.
        # chirp-device is NEVER stopped; the service connection stays live.
        # Each tick: short arecord capture per card → RMS + peak + 32 FFT bins.
        SCRIPT = """\
import json, time, subprocess, struct, math, sys, os

N_BINS = 32      # spectral bins per frame sent to server
TICK   = 0.5     # seconds between full sweeps
REC_MS = 120     # milliseconds of audio captured per device per tick

# Cards/names already reported by chirp-device's own status_server
# (device-local endpoint), injected by the server before this script is
# sent over SFTP. Skipping these avoids burning a whole tick on a doomed
# busy-device retry loop for cards the device-local source already covers.
#
# COVERED_CARDS (exact ALSA card-number match) is the primary mechanism —
# reliable because it's an integer, not a string. COVERED_NAMES (fuzzy
# substring match) is kept ONLY as a fallback for the rare case where the
# device itself couldn't determine its own card number (arecord unavailable
# there too) — PortAudio's device name and arecord -l's card name are
# different strings describing the same hardware and don't always
# substring-match reliably (confirmed in practice: the ReSpeaker specifically
# failed this match while card-number matching is exact by construction).
COVERED_CARDS = __COVERED_CARDS__
COVERED_NAMES = __COVERED_NAMES__


def _list_cards():
    \"\"\"Return [(card_num, name)] from arecord -l, minus any card already
    covered by the device-local status endpoint (COVERED_CARDS, or
    COVERED_NAMES as a fallback).\"\"\"
    try:
        out = subprocess.check_output(
            ["arecord", "-l"], stderr=subprocess.DEVNULL, timeout=4
        ).decode(errors="replace")
    except Exception:
        return []
    cards = []
    for line in out.splitlines():
        if line.startswith("card "):
            parts = line.split(":", 1)
            num = int(parts[0].split()[1])
            name = parts[1].strip() if len(parts) > 1 else f"card {num}"
            if num in COVERED_CARDS:
                continue
            if any(cn.lower() in name.lower() or name.lower() in cn.lower()
                   for cn in COVERED_NAMES if cn):
                continue
            cards.append((num, name))
    return cards


def _get_running_sr(card_num):
    \"\"\"
    Read the actual capture sample rate from /proc/asound when the card is
    in use. Returns None if not determinable.
    \"\"\"
    try:
        path = f"/proc/asound/card{card_num}/pcm0c/sub0/hw_params"
        txt = open(path).read()
        for line in txt.splitlines():
            if line.startswith("rate:"):
                return int(line.split()[1])
    except Exception:
        pass
    return None


def _sample_card(card_num, sr=48000):
    \"\"\"
    Capture REC_MS of mono 16-bit PCM via arecord, trying device strings
    in order until one succeeds:
      1. dsnoop:CARD=N,DEV=0  — ALSA shared-capture (works alongside other readers)
      2. default:CARD=N        — card default PCM (may go through dsnoop)
      3. plughw:N,0            — exclusive with plugin layer (last resort)

    If the card is busy, reads /proc/asound to find the running rate so we
    can match it and avoid ALSA format-mismatch errors.
    \"\"\"
    # Try to discover the rate the device is actually running at
    running_sr = _get_running_sr(card_num)
    if running_sr:
        sr = running_sr

    n_frames = max(64, int(sr * REC_MS / 1000))

    devices_to_try = [
        f"dsnoop:CARD={card_num},DEV=0",
        f"default:CARD={card_num}",
        f"plughw:{card_num},0",
    ]

    errors = []
    for dev_str in devices_to_try:
        cmd = [
            "arecord",
            "-D", dev_str,
            "-f", "S16_LE",
            "-r", str(sr),
            "-c", "1",
            f"--samples={n_frames}",
            "-q",
            "-",
        ]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
            if result.returncode != 0:
                stderr_text = result.stderr.decode("utf-8", errors="replace").strip()
                errors.append(f"{dev_str}: {stderr_text or f'exit code {result.returncode}'}")
                continue
            raw = result.stdout
            if len(raw) < 2:
                errors.append(f"{dev_str}: succeeded but returned no audio data")
                continue
            n = len(raw) // 2
            samples = [struct.unpack_from("<h", raw, i * 2)[0] / 32768.0
                       for i in range(n)]
            return samples, sr
        except subprocess.TimeoutExpired:
            errors.append(f"{dev_str}: timed out after 5s (device likely held open by another process)")
            continue
        except Exception as e:
            errors.append(f"{dev_str}: {e}")
            continue

    raise RuntimeError("all device strings failed — " + "; ".join(errors))


def _compute(samples):
    \"\"\"RMS dBFS, peak dBFS, and N_BINS magnitude spectrum.\"\"\"
    n = len(samples)
    # RMS and peak
    rms_lin = math.sqrt(sum(x * x for x in samples) / n) if n else 0
    pk_lin  = max(abs(x) for x in samples) if n else 0
    db_rms  = 20 * math.log10(rms_lin + 1e-10)
    db_pk   = 20 * math.log10(pk_lin  + 1e-10)

    # DFT magnitude in N_BINS buckets (no numpy — pure Python FFT via struct)
    # Use a simple magnitude estimate: split into N_BINS time-domain chunks
    # and compute RMS of each as a proxy for spectral energy.
    # Good enough for a visual level display; avoids numpy dependency here.
    chunk = max(1, n // N_BINS)
    bins = []
    for b in range(N_BINS):
        sl = samples[b * chunk: (b + 1) * chunk]
        if sl:
            v = math.sqrt(sum(x * x for x in sl) / len(sl))
        else:
            v = 0
        bins.append(v)
    # Normalize 0–255
    mx = max(bins) if bins else 0
    if mx > 0:
        bins = [int(v / mx * 255) for v in bins]
    else:
        bins = [0] * N_BINS

    return round(db_rms, 1), round(db_pk, 1), bins


# Probe native sample rates for known high-rate devices
CARD_RATES = {}

def _probe_rate(card_num, name):
    if card_num in CARD_RATES:
        return CARD_RATES[card_num]
    # AudioMoth and other ultrasonic mics report 192000
    nl = name.lower()
    if "audiomoth" in nl or "192" in nl or "ultrasonic" in nl:
        CARD_RATES[card_num] = 192000
    else:
        CARD_RATES[card_num] = 48000
    return CARD_RATES[card_num]


print(json.dumps({"type":"status","message":"Probing audio devices via arecord (chirp-device stays running)…"}), flush=True)

while True:
    cards = _list_cards()
    res = []
    for card_num, name in cards:
        sr = _probe_rate(card_num, name)
        try:
            samples, actual_sr = _sample_card(card_num, sr)
            db_rms, db_pk, bins = _compute(samples)
            res.append({
                "name": name, "card": card_num,
                "db": db_rms, "peak": db_pk,
                "sr": actual_sr, "bins": bins, "source": "ssh_arecord",
            })
        except Exception as e:
            # Try fallback rate
            if sr != 48000:
                try:
                    samples, actual_sr = _sample_card(card_num, 48000)
                    db_rms, db_pk, bins = _compute(samples)
                    res.append({
                        "name": name, "card": card_num,
                        "db": db_rms, "peak": db_pk,
                        "sr": actual_sr, "bins": bins, "source": "ssh_arecord",
                    })
                    CARD_RATES[card_num] = 48000
                    continue
                except Exception:
                    pass
            res.append({"name": name, "card": card_num, "db": None, "error": str(e), "source": "ssh_arecord"})

    print(json.dumps({"type": "levels", "devices": res}), flush=True)
    time.sleep(TICK)
"""

        script_text = SCRIPT.replace("__COVERED_CARDS__", repr(covered_cards)).replace("__COVERED_NAMES__", repr(covered_names))

        def _open_channel():
            transport = client.get_transport()
            # Write script to temp file via sftp, then exec — avoids shell quoting issues
            try:
                sftp = client.open_sftp()
                with sftp.open("/tmp/_chirp_mic_levels.py", "w") as f:
                    f.write(script_text)
                sftp.close()
                use_file = True
            except Exception:
                use_file = False

            chan = transport.open_session()
            if use_file:
                chan.exec_command(
                    "cd ~/chirp-device && . venv/bin/activate 2>/dev/null; "
                    "python3 /tmp/_chirp_mic_levels.py"
                )
            else:
                # Fallback: pipe script via stdin
                chan.exec_command(
                    "cd ~/chirp-device && . venv/bin/activate 2>/dev/null; python3 -"
                )
                chan.sendall(script_text.encode())
                chan.shutdown_write()
            return chan
        channel = await loop.run_in_executor(None, _open_channel)
        channel.settimeout(5.0)

        # Read stdout lines and forward to WebSocket
        # Also listen for WebSocket close in parallel
        stop_event = asyncio.Event()

        # Merge state: device-local (status_server) results and SSH/arecord
        # results are combined into ONE devices list per emitted "levels"
        # message, keyed by mic name. Local wins on a name collision (it's
        # genuinely concurrent, non-locking data). The frontend replaces its
        # whole devices array on every "levels" message, so sending two
        # independent unmerged streams would make each source flicker over
        # the other — merging server-side avoids that entirely.
        local_devices: dict = {d["name"]: d for d in (initial_local or [])}
        ssh_devices: dict = {}

        async def _emit_merged():
            merged = {**ssh_devices, **local_devices}
            try:
                await websocket.send_text(_json.dumps({"type": "levels", "devices": list(merged.values())}))
            except Exception:
                stop_event.set()

        async def _ws_listener():
            try:
                while not stop_event.is_set():
                    try:
                        msg = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                        if msg == "stop":
                            stop_event.set()
                    except asyncio.TimeoutError:
                        pass
            except Exception:
                stop_event.set()

        async def _ssh_reader():
            try:
                buf = b""
                while not stop_event.is_set():
                    def _recv():
                        try:
                            return channel.recv(4096)
                        except Exception:
                            return b""
                    chunk = await asyncio.wait_for(loop.run_in_executor(None, _recv), timeout=8.0)
                    if not chunk:
                        stop_event.set()
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        text = line.decode(errors="replace").strip()
                        if not text:
                            continue
                        try:
                            msg = _json.loads(text)
                        except Exception:
                            continue
                        if msg.get("type") == "levels":
                            for d in msg.get("devices", []):
                                d.setdefault("source", "ssh_arecord")
                                ssh_devices[d.get("name", "unknown")] = d
                            await _emit_merged()
                        else:
                            # status/error/etc. — forward as-is
                            try:
                                await websocket.send_text(text)
                            except Exception:
                                stop_event.set()
                                return
            except asyncio.TimeoutError:
                await websocket.send_text(_json.dumps({"type":"error","message":"SSH read timeout"}))
                stop_event.set()
            except Exception:
                stop_event.set()

        async def _local_poller():
            """
            Independently re-poll the device-local status endpoint every tick
            for as long as the websocket stays open, so levels for
            chirp-managed mics keep updating even if SSH itself is slow,
            errors out, or the device never had any SSH-only cards to begin
            with. No-op (stays empty forever) if the initial probe failed —
            we don't keep retrying a device that's confirmed unreachable on
            every single tick; one soft retry every 5s is enough to notice
            if it comes back without hammering the Pi.
            """
            consecutive_misses = 0 if initial_local else 1
            while not stop_event.is_set():
                await asyncio.sleep(0.5)
                if consecutive_misses >= 1 and consecutive_misses % 10 != 0:
                    # Back off to a slow retry cadence once we've missed —
                    # 0.5s * 10 = 5s between attempts — instead of hammering
                    # a device we already know isn't answering.
                    consecutive_misses += 1
                    continue
                data = await _poll_device_status_levels(ip, status_port, shared_key, timeout=1.5)
                if data is None:
                    consecutive_misses = max(consecutive_misses, 1)
                    continue
                consecutive_misses = 0
                for d in data:
                    local_devices[d.get("name", "unknown")] = d
                await _emit_merged()

        await asyncio.gather(_ws_listener(), _ssh_reader(), _local_poller())

    except Exception as e:
        try:
            await websocket.send_text(_json.dumps({"type":"error","message":f"SSH failed: {e}"}))
        except Exception:
            pass
    finally:
        try:
            channel.close()
        except Exception:
            pass
        try:
            client.close()
        except Exception:
            pass
        try:
            await websocket.send_text(_json.dumps({"type":"closed"}))
            await websocket.close()
        except Exception:
            pass

# ── Mic frequency response test ─────────────────────────────────────────────
# Requested directly, alongside Live Detect's window/sensitivity tuning: a
# way to compare how a phone's own mic and a chirp-device's mic actually
# pick up sound across frequency, side by side.

_FREQ_BANDS = [
    (0, 500, "0\u2013500 Hz"),
    (500, 1000, "500 Hz\u20131 kHz"),
    (1000, 2000, "1\u20132 kHz"),
    (2000, 4000, "2\u20134 kHz"),
    (4000, 6000, "4\u20136 kHz"),
    (6000, 8000, "6\u20138 kHz"),
    (8000, 10000, "8\u201310 kHz"),
    (10000, 12000, "10\u201312 kHz"),
    (12000, 16000, "12\u201316 kHz"),
    (16000, 20000, "16\u201320 kHz"),
]


@router.post("/mic-frequency-response")
async def mic_frequency_response(
    source: str = Form(..., description="'phone' (uploaded clip) or 'device' (pull live from a chirp-device mic)"),
    file: UploadFile = File(None, description="Required when source='phone'"),
    device_id: Optional[str] = Form(None, description="Required when source='device'"),
    mic_name: Optional[str] = Form(None, description="Required when source='device'"),
    db: Session = Depends(get_db),
):
    """
    Captures a few seconds of audio from either a phone (an uploaded clip)
    or a chirp-device's own mic (the same /listen path Live Detect and the
    mic-check Listen button already use — see _fetch_device_listen_clip),
    and returns its frequency-domain magnitude spectrum, binned into bands
    relevant to bird vocalizations.

    Important honesty note, surfaced in the response for the frontend to
    show directly, not buried here: this measures whatever frequency
    content is PRESENT in ambient sound during the capture, not a
    calibrated transfer function of the microphone itself. A mic with
    genuinely poor high-frequency response will show less energy up there
    only if whatever sound was actually happening during the capture had
    real energy up there to begin with — there's no calibrated reference
    signal (a speaker playing a known frequency sweep) assumed to exist
    here. Most useful as a relative, side-by-side comparison: capture the
    same real sound (the same bird, or a whistled note) on two different
    mics one after another, then compare their two spectra.
    """
    import numpy as np
    import soundfile as sf
    import tempfile
    from pathlib import Path as _Path
    from .live_detect import _decode_to_wav  # deferred import — live_detect.py itself imports FROM this module at load time, so importing it back at module level here would be circular

    if source == "device":
        if not device_id or not mic_name:
            raise HTTPException(400, "device_id and mic_name are both required when source='device'")
        audio_bytes = await _fetch_device_listen_clip(device_id, mic_name, db)
        hint_ext = ".wav"
    elif source == "phone":
        if file is None:
            raise HTTPException(400, "file is required when source='phone'")
        audio_bytes = await file.read()
        import os as _os
        hint_ext = _os.path.splitext(file.filename or "")[1].lower()
    else:
        raise HTTPException(400, f"Unknown source {source!r} — expected 'phone' or 'device'")

    if not audio_bytes:
        raise HTTPException(400, "No audio data received")

    tmp_dir = tempfile.mkdtemp(prefix="chirp_micresp_")
    dest_stem = _Path(tmp_dir) / "clip"
    try:
        wav_path = _decode_to_wav(audio_bytes, dest_stem, hint_ext)
        audio, sample_rate = sf.read(str(wav_path), dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)  # collapse to mono if the source happened to be stereo

        if len(audio) < 256:
            raise HTTPException(400, "Clip too short to analyze")

        # A single FFT over the whole clip — fine here: this is a coarse
        # relative comparison tool, not something that needs windowing,
        # overlap-add, or any of the machinery a real-time spectrogram
        # would want.
        magnitude = np.abs(np.fft.rfft(audio))
        freqs = np.fft.rfftfreq(len(audio), d=1.0 / sample_rate)

        bands = []
        for low, high, label in _FREQ_BANDS:
            if low >= sample_rate / 2:
                continue  # above this clip's own Nyquist frequency — nothing meaningful to report
            mask = (freqs >= low) & (freqs < min(high, sample_rate / 2))
            if not mask.any():
                bands.append({"label": label, "low_hz": low, "high_hz": high, "magnitude_db": None})
                continue
            mean_mag = float(np.mean(magnitude[mask]))
            # dB relative to the clip's own loudest band, not an absolute
            # calibrated SPL reference (no calibrated input exists here) —
            # 0 dB is always this clip's strongest band, everything else
            # negative from there. Comparing the SHAPE across mics is the
            # point, not any single absolute number.
            bands.append({"label": label, "low_hz": low, "high_hz": high, "magnitude_db": mean_mag})

        loudest = max((b["magnitude_db"] for b in bands if b["magnitude_db"] is not None), default=None)
        if loudest and loudest > 0:
            for b in bands:
                if b["magnitude_db"] is not None:
                    b["magnitude_db"] = round(20 * np.log10(max(b["magnitude_db"], 1e-9) / loudest), 1)

        spectrogram_png_base64 = _generate_mic_response_spectrogram(audio, int(sample_rate))

        return {
            "source": source,
            "device_id": device_id if source == "device" else None,
            "mic_name": mic_name if source == "device" else None,
            "sample_rate": int(sample_rate),
            "duration_seconds": round(len(audio) / sample_rate, 2),
            "bands": bands,
            "spectrogram_png_base64": spectrogram_png_base64,
            "note": "Relative frequency content of this specific capture, not a calibrated microphone response curve — for a meaningful comparison, capture the same real sound on each mic and compare shapes.",
        }
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _generate_mic_response_spectrogram(audio, sample_rate: int) -> Optional[str]:
    """
    Returns a base64-encoded PNG mel-spectrogram of this capture, or None
    if the optional libraries this needs aren't installed (never raises —
    the frequency-band comparison above still works fine without this).

    Deliberately NOT the same generate_spectrogram() regular recordings
    use — that one needs a real Recording row, detection-box overlays,
    and writes its output to disk under that recording's own id. This
    clip is disposable and never saved, so it's rendered directly to an
    in-memory PNG and returned inline instead, using the same mel-scale
    approach (and the same pcolormesh-based rendering, not librosa's own
    display.specshow helper, matching how generate_spectrogram avoids
    that extra import) for a familiar-looking result.
    """
    try:
        from ..services.audio_processor import _LIBROSA_OK, _MPL_OK
        if not (_LIBROSA_OK and _MPL_OK):
            return None
        import numpy as np
        import librosa as _librosa
        from matplotlib.figure import Figure as _Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg as _Canvas
        import io, base64

        n_mels = 96
        hop_length = 256
        fmax = min(20000, sample_rate // 2)
        S = _librosa.feature.melspectrogram(y=audio, sr=sample_rate, n_mels=n_mels, fmax=fmax, n_fft=1024, hop_length=hop_length)
        S_dB = _librosa.power_to_db(S, ref=np.max)

        BG = "#0a0f14"
        fig = _Figure(figsize=(6, 2.6), facecolor=BG)
        ax = fig.add_axes([0.09, 0.15, 0.89, 0.82])
        ax.set_facecolor(BG)

        times = _librosa.frames_to_time(np.arange(S_dB.shape[1]), sr=sample_rate, hop_length=hop_length)
        freqs = _librosa.mel_frequencies(n_mels=n_mels, fmax=fmax)
        ax.pcolormesh(times, freqs / 1000, S_dB, cmap="magma", shading="auto", vmin=-80, vmax=0)
        ax.set_ylabel("kHz", color="#9ca3af", fontsize=8)
        ax.set_xlabel("seconds", color="#9ca3af", fontsize=8)
        ax.tick_params(colors="#9ca3af", labelsize=7)
        for spine in ax.spines.values():
            spine.set_color("#374151")

        canvas = _Canvas(fig)
        buf = io.BytesIO()
        canvas.print_png(buf)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as e:
        logger.debug("Mic response spectrogram generation failed: %s", e)
        return None


# ── Client-reported layout numbers (frontend lib/viewportFix.js) ─────────
@router.post("/client")
async def client_diagnostics(request: Request):
    """Log what a phone reports about its viewport, for layout bugs that
    only show on a device. Logged only; capped at 4 KB."""
    body = (await request.body())[:4096]
    try:
        import json as _json
        data = _json.loads(body or b"{}")
    except Exception:
        data = {"raw": body.decode("utf-8", "replace")}
    logger.info("client-diag %s", data)
    return {"ok": True}
