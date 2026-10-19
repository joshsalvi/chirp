"""Chirp Server — FastAPI Application"""
import asyncio, json, logging, os, re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Set

# Investigated directly after two separate reports where an attached
# server log turned out to contain thousands of lines of numba's own
# internal JIT-compilation trace (a librosa dependency) and nothing
# else useful — no HTTP access log, no application events, nothing
# that actually helped diagnose what was reported. numba was logging
# at DEBUG level, and since this app's own root-logger level (set
# further down, only inside `if __name__ == "__main__":`, which a
# production `uvicorn` launch never actually hits) doesn't reliably
# control every third-party logger's own level, something in the
# deployment environment — most likely a NUMBA_DEBUG-style env var, not
# anything in this codebase — was independently cranking numba's own
# logger up. Set here, unconditionally, at import time, specifically
# for numba's own logger, so this can't happen again regardless of
# what enables it or how the app gets launched.
logging.getLogger("numba").setLevel(logging.WARNING)

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from .database import init_db, get_db
from .api import recordings, birds
from .api import app_settings
from .api import auth as auth_router
from .api import instances as instances_router
from .api import admin_panel as admin_panel_router
from .api import devices as devices_router
from .api import logs as logs_router
from .api import bat_activity as bat_activity_router
from .api import night_calls as night_calls_router
from .api import diagnostics as diagnostics_router
from .api import push as push_router
from .api import notifications as notifications_router
from .api import techdocs as techdocs_router
from .api import live_detect as live_detect_router
from .api import watch as watch_router
from .api import near_misses as near_misses_router
from .services import log_buffer
from .cache import settings_cache, user_token_cache

logger = logging.getLogger("chirp.server")


class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)

    async def broadcast(self, message: dict):
        if not self.active:
            return
        text = json.dumps(message)
        dead = set()
        for ws in list(self.active):
            try:
                await ws.send_text(text)
            except Exception:
                dead.add(ws)
        self.active -= dead


manager = ConnectionManager()
_main_loop = None   # set at startup; used to schedule broadcasts from sync threads


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_buffer.install()   # capture all log records into ring buffer

    # ─── Multi-instance addition (see ARCHITECTURE.md) ─────────────────────
    # Two lines, deliberately: initialize the real registry database, and
    # register the dependency override that makes every existing endpoint's
    # own `Depends(get_db)` resolve to the instance-aware session instead —
    # nothing below this block, or anywhere else in chirp-server's own
    # ~168 endpoints, needed to change for this to take effect.
    from .registry_db import init_registry_db
    from .instance_registry import get_instance_db, patch_session_local_for_instance_awareness
    init_registry_db()
    app.dependency_overrides[get_db] = get_instance_db
    patch_session_local_for_instance_awareness()
    # ─────────────────────────────────────────────────────────────────────

    # Global-admin bootstrap — promotes CHIRP_GLOBAL_ADMIN_USERNAME (if
    # set) to is_global_admin=True on every startup, so the very first
    # global admin can be established without ever needing direct
    # database access. Idempotent and safe to leave set permanently: it
    # only ever adds the flag, never removes it, so it can't be used to
    # accidentally demote someone by clearing an env var. Every
    # subsequent promotion/demotion goes through the admin panel itself
    # once at least one global admin exists.
    import os
    _global_admin_username = os.environ.get("CHIRP_GLOBAL_ADMIN_USERNAME", "").strip()
    if _global_admin_username:
        from .registry_db import RegistrySessionLocal
        from .registry_models import GlobalUser
        _reg_db = RegistrySessionLocal()
        try:
            _gu = _reg_db.query(GlobalUser).filter(GlobalUser.username == _global_admin_username).first()
            if _gu and not _gu.is_global_admin:
                _gu.is_global_admin = True
                _reg_db.commit()
                logger.info("Global admin bootstrap: promoted %s", _global_admin_username)
            elif not _gu:
                logger.warning(
                    "CHIRP_GLOBAL_ADMIN_USERNAME=%s is set but no matching account exists yet — "
                    "register that account, then restart the container to promote it.",
                    _global_admin_username,
                )
        finally:
            _reg_db.close()

    # Retroactive column migration for every EXISTING instance — must
    # run BEFORE the auth_enabled fix-up directly below, which itself
    # queries AppSettings and would silently fail with the exact same
    # "no such column" error otherwise (confirmed: this is precisely
    # what was happening — that fix-up's own try/except was swallowing
    # the failure every startup, so it looked like it ran successfully
    # but never actually could reach its own fix logic). See
    # _migrate_columns's own updated docstring in database.py for the
    # full reasoning on why this never reached instance databases
    # before now — only chirp-server's original, single, legacy engine.
    from .database import _migrate_columns
    from .instance_registry import get_engine_for_instance
    from .registry_db import RegistrySessionLocal
    from .registry_models import Instance
    _reg_db_mig = RegistrySessionLocal()
    try:
        _all_instances = _reg_db_mig.query(Instance).all()
    finally:
        _reg_db_mig.close()
    for _inst_mig in _all_instances:
        try:
            _migrate_columns(get_engine_for_instance(_inst_mig.db_filename))
        except Exception as _e:
            logger.warning("Column migration failed for instance %s (%s): %s", _inst_mig.id, _inst_mig.name, _e)

    # Retroactive auth_enabled fix-up — every EXISTING instance (created
    # before provision_instance_database started seeding this at
    # creation time) may still have no AppSettings row, or one with
    # auth_enabled left None/False. Runs once per startup, idempotent,
    # cheap even with many instances (a single-row check per instance
    # database). See provision_instance_database's own comment for the
    # full reasoning on why this needs to be forced true here.
    from .instance_registry import iter_instance_sessions
    from .models import AppSettings
    for _inst, _idb in iter_instance_sessions():
        try:
            _s = _idb.query(AppSettings).filter(AppSettings.id == 1).first()
            if _s is None:
                _idb.add(AppSettings(id=1, auth_enabled=True))
                _idb.commit()
            elif not _s.auth_enabled:
                _s.auth_enabled = True
                _idb.commit()
        except Exception as _e:
            logger.warning("auth_enabled fix-up failed for instance %s (%s): %s", _inst.id, _inst.name, _e)

    init_db()
    logger.info("Chirp Server starting on %s:%d", settings.host, settings.port)
    # Clear any mangled IP addresses stored by the old IPv6 port-stripping bug.
    # A valid stored IP must be either a dotted-quad IPv4 or empty.
    # Fragments like "2600" (truncated IPv6) will be nulled so the next heartbeat fixes them.
    try:
        from .database import SessionLocal as _SL_ip
        from .models import Device as _Dev_ip
        import re as _re_ip
        with _SL_ip() as _db_ip:
            _fixed = 0
            for _dev in _db_ip.query(_Dev_ip).all():
                _ip = _dev.ip_address or ""
                _valid = bool(_re_ip.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", _ip))
                if _ip and not _valid:
                    logger.info("Clearing bad device IP '%s' for %s — will update on next heartbeat", _ip, _dev.name)
                    _dev.ip_address = None
                    _fixed += 1
            if _fixed:
                _db_ip.commit()
    except Exception as _e:
        logger.debug("IP cleanup error: %s", _e)
    app.state.ws_manager = manager

    from .database import SessionLocal
    from .api.auth import ensure_default_admin
    with SessionLocal() as db:
        ensure_default_admin(db)
        # Re-seed SMTP/email settings from env vars on every startup.
        # Ensures .env values survive container rebuilds even if the DB row exists.
        try:
            from .api.app_settings import _get_or_create as _goc, _seed_from_env as _sfe
            _s = _goc(db)
            if _sfe(_s):
                db.commit()
                logger.info("Seeded email/SMTP settings from environment variables")
        except Exception as _se:
            logger.debug("SMTP seed on startup failed: %s", _se)

    # Clear stale range map cache files
    import glob as _glob2
    removed_maps = 0
    range_map_dir = os.path.join(settings.media_dir, "range_maps")
    if os.path.isdir(range_map_dir):
        for f in _glob2.glob(os.path.join(range_map_dir, "*")):
            try: os.remove(f); removed_maps += 1
            except OSError: pass
    birds_media_dir = os.path.join(settings.media_dir, "birds")
    for svg_path in _glob2.glob(os.path.join(birds_media_dir, "*", "range_map.svg")):
        try: os.remove(svg_path); removed_maps += 1
        except OSError: pass
    if removed_maps:
        logger.info("Cleared %d cached range map files", removed_maps)
    logger.info("Spectrogram cache preserved across restart.")

    # Reset stale/broken range map URLs
    from .models import BirdProfile as _BP_startup
    from .instance_registry import iter_instance_sessions
    try:
        for _instance_rm, _db_s in iter_instance_sessions():
            reset_count = 0
            for bird in _db_s.query(_BP_startup).all():
                # The "Bat" pseudo-species (is_bat=True) has no real
                # geographic range map from any external provider — it's
                # a fixed stock representation, not subject to the same
                # "stale external URL" concerns real species have. Found
                # the hard way, connecting two separate-looking bug
                # reports: this sweep had no exclusion for it, so an
                # empty range_map_url (which the Bat profile is created
                # with deliberately) could flip its enrichment_complete
                # to False here — which then let it fall through into
                # the GENERAL enrichment pipeline (via whatever normal
                # "needs enrichment" check runs on page view), whose own
                # generic iNaturalist photo step has no is_bat awareness
                # and can overwrite the Bat profile's own carefully-set
                # representative photo with an unrelated one.
                if bird.is_bat:
                    continue
                url = bird.range_map_url or ""
                needs_reset = (
                    (url.startswith("file://") and not os.path.exists(url[7:])) or
                    ("inaturalist.org" in url and "/range.png" in url) or
                    (not url and not bird.enrichment_complete)
                )
                if needs_reset:
                    bird.range_map_url = None
                    bird.enrichment_complete = False
                    reset_count += 1
            if reset_count:
                _db_s.commit()
                logger.info("Queued %d birds for range map re-enrichment (instance %s)", reset_count, _instance_rm.name)
    except Exception as _e:
        logger.warning("Startup bird reset error: %s", _e)

    # Bat profile photo: retry if profile exists but photo is missing
    try:
        from .models import BirdProfile as _BP_bat
        from .services.bird_enricher import BirdEnricher
        from .instance_registry import iter_instance_sessions
        for _instance_bat, _db_bat in iter_instance_sessions():
            bat = _db_bat.query(_BP_bat).filter(_BP_bat.label == "Bat").first()
            if bat and (not bat.photo_path or not os.path.exists(bat.photo_path or "")):
                enricher = BirdEnricher(_db_bat)
                enricher._fetch_bat_photo(bat)
                logger.info("Bat profile photo refresh on startup for instance %s", _instance_bat.name)
    except Exception as _be:
        logger.debug("Bat photo startup refresh failed (non-fatal): %s", _be)

    # Storage manager
    from .services.storage_manager import StorageManager
    from .config import settings as _settings
    storage_mgr = StorageManager(
        db_factory=SessionLocal,
        recordings_dir=_settings.recordings_dir,
        spectrograms_dir=_settings.spectrograms_dir,
        clips_dir=_settings.clips_dir,
    )
    storage_mgr.start()
    app.state.storage_manager = storage_mgr

    # Server-side Tailscale/Headscale — the counterpart to chirp-device's
    # own manager, and identical in spirit to chirp-server's own
    # equivalent (see that project's main.py / tailscale_manager.py),
    # but backed by the registry database instead of any one instance's
    # AppSettings — one Tailscale identity per container, shared by
    # every instance this server hosts, configured from Global Admin
    # only.
    #
    # Precedence, highest to lowest: RegistrySettings (an admin
    # explicitly saved something via Global Admin's own "Save &
    # Connect") > CHIRP_TAILSCALE_AUTH_KEY env var (a real Tailscale.com
    # account, set by hand) > the bundled Headscale's own auto-generated
    # key at /shared/authkey (see the "headscale" docker-compose
    # service and headscale/entrypoint.sh) — the zero-manual-steps
    # default this whole feature exists to provide. Each level is only
    # consulted if the one above it didn't already provide a key, so a
    # deliberately-set RegistrySettings/env value is never silently
    # overridden by the bundled Headscale's own key.
    from .services.tailscale_manager import TailscaleManager
    tailscale_mgr = TailscaleManager(_settings)
    if not tailscale_mgr.auth_key:
        try:
            with open("/shared/authkey") as _hs_f:
                _hs_key = _hs_f.read().strip()
            if _hs_key:
                tailscale_mgr.enabled = True
                tailscale_mgr.auth_key = _hs_key
                logger.info("Using auto-provisioned key from the bundled Headscale service")
        except FileNotFoundError:
            pass
        except Exception as _hs_e:
            logger.warning("Could not read bundled Headscale key from /shared/authkey: %s", _hs_e)
    tailscale_mgr.start()
    app.state.tailscale_manager = tailscale_mgr
    from .services.device_net import set_tailscale_manager as _set_ts_mgr
    _set_ts_mgr(tailscale_mgr)
    try:
        from .registry_db import RegistrySessionLocal
        from .registry_models import RegistrySettings
        _ts_db = RegistrySessionLocal()
        _ts_s = _ts_db.query(RegistrySettings).filter(RegistrySettings.id == 1).first()
        if _ts_s and _ts_s.tailscale_auth_key:
            tailscale_mgr.reconfigure(
                enabled=bool(_ts_s.tailscale_enabled),
                auth_key=_ts_s.tailscale_auth_key,
                login_server=_ts_s.tailscale_login_server or "",
                hostname=_ts_s.tailscale_hostname or "",
            )
        _ts_db.close()
    except Exception as _ts_e:
        logger.warning("Could not load saved Tailscale config from RegistrySettings, using env vars: %s", _ts_e)

    # Activity log — background purge loop (respects activity_log_retention_days)
    from .services.activity_log import ActivityLogManager
    activity_log_mgr = ActivityLogManager(db_factory=SessionLocal)
    activity_log_mgr.start()
    app.state.activity_log_manager = activity_log_mgr

    # Dashboard cache warmer — keeps /stats and dashboard-summary's cache
    # fresh proactively (see the module's own docstring for why: the
    # existing 45s cache only helps a REPEAT request, not a person's
    # first Dashboard visit of the session, which is exactly the "extra
    # couple seconds" that was reported).
    from .services.dashboard_cache_warmer import DashboardCacheWarmer
    dashboard_cache_warmer = DashboardCacheWarmer(db_factory=SessionLocal)
    dashboard_cache_warmer.start()
    app.state.dashboard_cache_warmer = dashboard_cache_warmer

    # Daily digest scheduler — fires at configurable UTC hour (default 7)
    import threading as _threading
    _stop_digest = _threading.Event()

    from .services.notify_off import notifications_off as _notifications_off
    if _notifications_off():
        logger.info("CHIRP_NOTIFICATIONS_OFF: no pushes, emails, journals or digests from this server")

    def _digest_loop():
        # Digest push and email, each at the location's own local hour
        # (services/scheduled_push.daily_digest_tick keeps the day sent).
        from .instance_registry import iter_instance_sessions
        from .services.scheduled_push import daily_digest_tick
        from .services.device_alerts import device_offline_tick
        while not _stop_digest.wait(60):
            for instance, _db_dh in iter_instance_sessions():
                try:
                    sent = daily_digest_tick(_db_dh)
                    if sent:
                        logger.info("Daily digest sent for %s: %s", instance.name, ", ".join(sent))
                    alerts = device_offline_tick(_db_dh)
                    if alerts:
                        logger.info("Station alerts for %s: %s", instance.name, ", ".join(alerts))
                except Exception as _de:
                    logger.warning("Daily digest error for instance %s: %s", instance.name, _de)

    _digest_thread = _threading.Thread(target=_digest_loop, daemon=True, name="digest")
    if not _notifications_off():
        _digest_thread.start()

    # Night flight calls (Experimental): finish chunks a restart left
    # waiting and drop failed audio (services/nighthawk_service.py).
    def _night_calls_loop():
        from .instance_registry import iter_instance_sessions
        from .services import nighthawk_service as _nh
        while not _stop_digest.wait(300):
            if _nh.available():
                continue
            for instance, _db_nc in iter_instance_sessions():
                try:
                    _nh.cleanup(_db_nc)
                    for _cid in _nh.pending_ids(_db_nc):
                        _nh.process_chunk(_cid)
                except Exception as _ne:
                    logger.warning("Night calls error for instance %s: %s", instance.name, _ne)

    _threading.Thread(target=_night_calls_loop, daemon=True, name="night-calls").start()

    # BirdNET v3 is the default detection model: fetch it (557 MB, once, to
    # ai_models_dir) in the background. Until it's there, recordings use 2.4.
    try:
        from .services import birdnet3 as _bn3
        _bn3.ensure_downloaded()
    except Exception as _e:
        logger.warning("BirdNET v3 download not started: %s", _e)

    # Scheduled pushes: Daily Journal 6 pm, Weekly Journal Sunday noon,
    # watched-bird summaries 7 pm (local time per location). See
    # services/scheduled_push.py.
    _stop_sched_push = _threading.Event()

    def _scheduled_push_loop():
        from .instance_registry import iter_instance_sessions
        from .services.scheduled_push import tick as _sp_tick
        while not _stop_sched_push.wait(60 - _dt_mod.datetime.utcnow().second % 60 or 60):
            for _inst_sp, _db_sp in iter_instance_sessions():
                try:
                    _sent = _sp_tick(_db_sp)
                    if _sent:
                        logger.info("Scheduled pushes for %s: %s", _inst_sp.name, ", ".join(_sent))
                except Exception as _spe:
                    logger.warning("Scheduled push error for %s: %s", _inst_sp.name, _spe)

    import datetime as _dt_mod
    if not _notifications_off():
        _threading.Thread(target=_scheduled_push_loop, daemon=True, name="scheduled-push").start()

    # Daily summary (AI-written "birder's journal") scheduler — experimental
    # feature, see services/daily_summary.py. Fires once at whatever
    # HH:MM is configured (AppSettings.daily_summary_schedule_time),
    # interpreted in AppSettings.timezone — not UTC like the digest loop
    # above, since this is meant to read like "your morning journal entry
    # showed up," which should mean the same local time regardless of
    # where the server itself happens to be hosted.
    _stop_summary = _threading.Event()

    def _daily_summary_loop():
        import time as _time
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo as _ZoneInfo
        from .instance_registry import iter_instance_sessions
        from .models import AppSettings as _AS_ds
        while not _stop_summary.wait(60):  # check every minute
            _fired_ds = False
            for _instance_ds, _db_ds in iter_instance_sessions():
                try:
                    _s_ds = _db_ds.query(_AS_ds).filter(_AS_ds.id == 1).first()
                    # Prefer the multi-time list when set; fall back to
                    # wrapping the older single-time field in a one-item
                    # list, so an existing single-time config keeps working
                    # unchanged without needing a data migration.
                    _sched_list = (getattr(_s_ds, "daily_summary_schedule_times", None) if _s_ds else None) or []
                    if not _sched_list:
                        _single = (_s_ds.daily_summary_schedule_time if _s_ds else None) or "07:00"
                        _sched_list = [_single]
                    _sched_times = []
                    for _t in _sched_list:
                        try:
                            _h, _m = (int(x) for x in _t.split(":"))
                            _sched_times.append((_h, _m))
                        except Exception:
                            continue
                    if not _sched_times:
                        _sched_times = [(7, 0)]
                    try:
                        _tz_ds = _ZoneInfo(_s_ds.timezone or "UTC") if _s_ds else _ZoneInfo("UTC")
                    except Exception:
                        _tz_ds = _ZoneInfo("UTC")
                except Exception:
                    _sched_times, _tz_ds = [(7, 0)], _ZoneInfo("UTC")
                now_local = _dt.now(_ZoneInfo("UTC")).astimezone(_tz_ds)
                if (now_local.hour, now_local.minute) in _sched_times:
                    _fired_ds = True
                    try:
                        from .services.daily_summary import generate_daily_summary
                        generate_daily_summary(_db_ds)
                    except Exception as _se:
                        logger.warning("Daily summary scheduler error for instance %s: %s", _instance_ds.name, _se)
            if _fired_ds:
                _time.sleep(61)  # skip the rest of this minute

    _summary_thread = _threading.Thread(target=_daily_summary_loop, daemon=True, name="daily-summary")
    if not _notifications_off():
        _summary_thread.start()

    # Weekly Journal scheduler — same local-timezone-aware pattern as
    # the daily loop above, gated on day-of-week too (Python's
    # datetime.weekday(): 0=Monday..6=Sunday, matching how
    # weekly_summary_schedule_day is documented in models.py) since this
    # should fire once a week, not once a day.
    _stop_weekly = _threading.Event()

    def _weekly_summary_loop():
        import time as _time
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo as _ZoneInfo
        from .instance_registry import iter_instance_sessions
        from .models import AppSettings as _AS_ws
        while not _stop_weekly.wait(60):  # check every minute
            _fired_ws = False
            for _instance_ws, _db_ws in iter_instance_sessions():
                try:
                    _s_ws = _db_ws.query(_AS_ws).filter(_AS_ws.id == 1).first()
                    _day_ws = int(_s_ws.weekly_summary_schedule_day) if _s_ws and _s_ws.weekly_summary_schedule_day is not None else 6
                    _hour_ws = int(_s_ws.weekly_summary_schedule_hour) if _s_ws and _s_ws.weekly_summary_schedule_hour is not None else 7
                    try:
                        _tz_ws = _ZoneInfo(_s_ws.timezone or "UTC") if _s_ws else _ZoneInfo("UTC")
                    except Exception:
                        _tz_ws = _ZoneInfo("UTC")
                except Exception:
                    _day_ws, _hour_ws, _tz_ws = 6, 7, _ZoneInfo("UTC")
                now_local_ws = _dt.now(_ZoneInfo("UTC")).astimezone(_tz_ws)
                if now_local_ws.weekday() == _day_ws and now_local_ws.hour == _hour_ws and now_local_ws.minute == 0:
                    _fired_ws = True
                    try:
                        from .services.weekly_summary import generate_weekly_summary
                        generate_weekly_summary(_db_ws)
                    except Exception as _se:
                        logger.warning("Weekly summary scheduler error for instance %s: %s", _instance_ws.name, _se)
            if _fired_ws:
                _time.sleep(61)  # skip the rest of this minute

    _weekly_thread = _threading.Thread(target=_weekly_summary_loop, daemon=True, name="weekly-summary")
    if not _notifications_off():
        _weekly_thread.start()

    # Bird Profile presence-summary refresh scheduler — off by default
    # (AppSettings.profile_summary_auto_refresh). Without this, a
    # profile's AI presence summary only ever generates once, on first
    # view, and sits unchanged indefinitely — see
    # services/profile_summary.py's refresh_stale_profile_summaries for
    # the actual staleness/selection logic; this loop just fires it once
    # a day at the configured local hour, same local-timezone-aware
    # pattern as the daily summary loop above rather than the digest
    # loop's fixed-UTC-hour one, for the same reason: "runs at 3am" should
    # mean 3am where the yard actually is, not 3am UTC.
    _stop_profile_refresh = _threading.Event()

    def _profile_summary_refresh_loop():
        import time as _time
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo as _ZoneInfo
        from .instance_registry import iter_instance_sessions
        from .models import AppSettings as _AS_pr
        while not _stop_profile_refresh.wait(60):  # check every minute
            _fired_pr = False
            for _instance_pr, _db_pr in iter_instance_sessions():
                try:
                    _s_pr = _db_pr.query(_AS_pr).filter(_AS_pr.id == 1).first()
                    if not (_s_pr and _s_pr.profile_summary_auto_refresh):
                        continue
                    _hour_pr = int(_s_pr.profile_summary_refresh_hour) if _s_pr.profile_summary_refresh_hour is not None else 3
                    _days_pr = int(_s_pr.profile_summary_refresh_days) if _s_pr.profile_summary_refresh_days is not None else 7
                    try:
                        _tz_pr = _ZoneInfo(_s_pr.timezone or "UTC")
                    except Exception:
                        _tz_pr = _ZoneInfo("UTC")
                except Exception as _pe:
                    logger.warning("Profile summary refresh scheduler config error for instance %s: %s", _instance_pr.name, _pe)
                    continue
                now_local_pr = _dt.now(_ZoneInfo("UTC")).astimezone(_tz_pr)
                if now_local_pr.hour == _hour_pr and now_local_pr.minute == 0:
                    _fired_pr = True
                    try:
                        from .services.profile_summary import refresh_stale_profile_summaries
                        refresh_stale_profile_summaries(_db_pr, max_age_days=_days_pr)
                    except Exception as _pe2:
                        logger.warning("Profile summary refresh error for instance %s: %s", _instance_pr.name, _pe2)
            if _fired_pr:
                _time.sleep(61)  # skip the rest of this minute

    _profile_refresh_thread = _threading.Thread(target=_profile_summary_refresh_loop, daemon=True, name="profile-summary-refresh")
    _profile_refresh_thread.start()

    # Automatic database backup scheduler — on by default (see
    # AppSettings.auto_backup_enabled's model comment for why this one
    # defaults on unlike the AI-feature schedulers above). Same
    # local-timezone-aware daily-fire pattern as the other loops in this
    # file; the actual backup/prune work lives in services/backup_service.py.
    _stop_backup = _threading.Event()

    def _auto_backup_loop():
        import time as _time
        import os as _os_bk
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo as _ZoneInfo
        while not _stop_backup.wait(60):  # check every minute
            # Multi-instance addition (see ARCHITECTURE.md): iterates every
            # real registered instance, each with its own real backup
            # config, own real database file, and own real backup output
            # directory — not the single legacy database. A real,
            # previously-missing piece: auto_backup_enabled defaults on
            # (unlike the sync services below, which are genuinely
            # opt-in), so before this, NO real instance's data was ever
            # being automatically backed up at all.
            from .instance_registry import iter_instance_sessions, INSTANCES_DIR
            from .models import AppSettings as _AS_bk
            for _instance_bk, _db_bk in iter_instance_sessions():
                try:
                    _s_bk = _db_bk.query(_AS_bk).first()
                    if not _s_bk:
                        continue  # a freshly-created instance may not have its AppSettings row seeded yet — real, not an error, skip this cycle
                    if not (_s_bk.auto_backup_enabled if _s_bk.auto_backup_enabled is not None else True):
                        continue
                    _hour_bk = int(_s_bk.auto_backup_hour) if _s_bk.auto_backup_hour is not None else 3
                    _retain_bk = int(_s_bk.auto_backup_retention_count) if _s_bk.auto_backup_retention_count is not None else 14
                    try:
                        _tz_bk = _ZoneInfo(_s_bk.timezone or "UTC")
                    except Exception:
                        _tz_bk = _ZoneInfo("UTC")
                except Exception as _be:
                    logger.warning("Auto-backup scheduler config error for instance %s: %s", _instance_bk.name, _be)
                    continue

                now_local_bk = _dt.now(_ZoneInfo("UTC")).astimezone(_tz_bk)
                if now_local_bk.hour == _hour_bk and now_local_bk.minute == 0:
                    try:
                        from .services.backup_service import record_backup_result
                        db_path_bk = _os_bk.path.join(INSTANCES_DIR, _instance_bk.db_filename)
                        # Real, separate backup directory per instance —
                        # matches the whole design's own principle of
                        # genuine per-instance isolation, not just the
                        # live database.
                        data_dir_bk = _os_bk.path.join(INSTANCES_DIR, f"{_instance_bk.id}_backups")
                        _os_bk.makedirs(data_dir_bk, exist_ok=True)
                        # record_backup_result (see backup_service.py) writes
                        # auto_backup_last_run_at/last_success_at/last_error
                        # onto _s_bk and commits on _db_bk — this instance's
                        # own session, from iter_instance_sessions() above —
                        # so a failure is visible in THIS instance's own
                        # Settings, not just a server-log line naming the
                        # instance after the fact.
                        result = record_backup_result(_db_bk, _s_bk, db_path_bk, data_dir_bk, _retain_bk)
                        if "error" in result:
                            logger.warning("Automatic backup failed for instance %s: %s", _instance_bk.name, result["error"])
                        else:
                            logger.info("Automatic backup complete for instance %s: %s", _instance_bk.name, result)
                    except Exception as _be2:
                        logger.warning("Automatic backup failed for instance %s: %s", _instance_bk.name, _be2)
            _time.sleep(61)  # skip the rest of this minute

    _auto_backup_thread = _threading.Thread(target=_auto_backup_loop, daemon=True, name="auto-backup")
    _auto_backup_thread.start()

    # Sweeps every instance's own database for orphaned Live Detect
    # poll clips — see services/live_detect_cleanup.py's own module
    # docstring for the full story on why these need sweeping at all,
    # not just hiding from the list. Runs far less often than the
    # backup loop above (these accumulate on the order of minutes of
    # someone leaving a page open, not something that needs
    # minute-level responsiveness to clean up), and reuses the exact
    # same iter_instance_sessions() per-instance iteration as every
    # other real background job in this file.
    _stop_ld_cleanup = _threading.Event()

    def _live_detect_cleanup_loop():
        while not _stop_ld_cleanup.wait(3600):  # once per hour
            from .instance_registry import iter_instance_sessions
            from .services.live_detect_cleanup import cleanup_orphaned_live_detect_clips
            from .config import settings as _cfg_ld
            for _instance_ld, _db_ld in iter_instance_sessions():
                try:
                    removed = cleanup_orphaned_live_detect_clips(
                        _db_ld, _cfg_ld.recordings_dir, _cfg_ld.spectrograms_dir, _cfg_ld.clips_dir,
                    )
                    if removed:
                        logger.info("Live Detect cleanup removed %d orphaned clip(s) for instance %s", removed, _instance_ld.name)
                except Exception as _le:
                    logger.warning("Live Detect cleanup failed for instance %s: %s", _instance_ld.name, _le)

    _live_detect_cleanup_thread = _threading.Thread(target=_live_detect_cleanup_loop, daemon=True, name="live-detect-cleanup")
    _live_detect_cleanup_thread.start()

    # Auto-purge sweep: with Auto-purge on, recordings that show nothing
    # (the list's "Unknown" cards) are deleted every 15 minutes, not only
    # when they're uploaded, so ones that slipped through earlier rules or a
    # display-threshold change get cleared too (api/app_settings.py).
    def _empty_purge_loop():
        _stop_ld_cleanup.wait(120)
        while True:
            from .instance_registry import iter_instance_sessions
            from .api.app_settings import sweep_empty_recordings
            for _instance_ep, _db_ep in iter_instance_sessions():
                try:
                    n = sweep_empty_recordings(_db_ep)
                    if n:
                        logger.info("Auto-purge sweep removed %d recording(s) for instance %s", n, _instance_ep.name)
                except Exception as _ee:
                    logger.warning("Auto-purge sweep failed for instance %s: %s", _instance_ep.name, _ee)
            if _stop_ld_cleanup.wait(900):
                break

    _threading.Thread(target=_empty_purge_loop, daemon=True, name="empty-purge-sweep").start()

    # One-time (per instance), startup-triggered spectrogram regen for
    # the detection-color spread fix — see AppSettings' own
    # spectrograms_regenerated_for_color_fix column docstring for why
    # this can't just rely on the normal cache-invalidation path.
    # Genuinely background: a server with a large recordings library
    # could take a while to work through, and nothing else should wait
    # on it — existing spectrograms keep serving (with the old colors)
    # until each one's own turn comes up in this sweep.
    def _color_fix_regen_startup():
        from .instance_registry import iter_instance_sessions
        from .api.app_settings import _regenerate_spectrograms_for_color_fix_bg
        for _instance_cf, _db_cf in iter_instance_sessions():
            try:
                _regenerate_spectrograms_for_color_fix_bg()
            except Exception as _cfe:
                logger.warning("Spectrogram color-fix regen failed for instance %s: %s", _instance_cf.name, _cfe)

    _threading.Thread(target=_color_fix_regen_startup, daemon=True, name="spectrogram-color-fix-regen").start()

    # One-time (per instance), startup-triggered backfill for a real,
    # reported gap: an instance created via POST /instances/import only
    # ever created a registry Membership for the person doing the
    # import — every OTHER local account already in the imported
    # database (a whole prior deployment's real user history) was left
    # with no Membership at all, so Global Admin's own instance-member
    # list (Membership-based) and that instance's own local Users page
    # (local User table-based) permanently disagreed, and those other
    # accounts couldn't actually log in through this fork's real
    # GlobalUser-based auth. Fixed prospectively for new imports (see
    # backfill_memberships_for_local_users' own call in instances.py);
    # this sweep fixes it retroactively for instances imported before
    # that existed. See AppSettings.local_users_membership_backfilled's
    # own docstring for why this needs a checked, idempotent flag rather
    # than just re-running unconditionally every startup.
    def _membership_backfill_startup():
        from .instance_registry import iter_instance_sessions
        from .registry_db import RegistrySessionLocal
        from .api.instances import backfill_memberships_for_local_users
        from .models import AppSettings
        for _instance_mb, _db_mb in iter_instance_sessions():
            try:
                _s_mb = _db_mb.query(AppSettings).first()
                if _s_mb and _s_mb.local_users_membership_backfilled:
                    continue
                _reg_db_mb = RegistrySessionLocal()
                try:
                    _created_mb = backfill_memberships_for_local_users(_reg_db_mb, _db_mb, _instance_mb.id)
                finally:
                    _reg_db_mb.close()
                if _s_mb:
                    _s_mb.local_users_membership_backfilled = True
                    _db_mb.commit()
                if _created_mb:
                    logger.info("Startup membership backfill created %d Membership(s) for instance %s", _created_mb, _instance_mb.name)
            except Exception as _mbe:
                logger.warning("Membership backfill failed for instance %s: %s", _instance_mb.name, _mbe)

    _threading.Thread(target=_membership_backfill_startup, daemon=True, name="membership-backfill").start()

    # Haikubox sync service — polls every 15 min if a serial is configured
    from .services.haikubox_sync import get_sync_service as _get_hb_sync
    _hb_sync = _get_hb_sync()
    _hb_sync.start()

    # Bird Buddy sync service — polls every 15 min if enabled + credentials configured
    from .services.bird_buddy_sync import get_sync_service as _get_bb_sync
    _bb_sync = _get_bb_sync()
    _bb_sync.start()

    # iNaturalist token auto-refresh — keeps inat_api_token fresh if enabled + credentials configured
    from .services.inat_auth import get_service as _get_inat_auth
    _inat_auth = _get_inat_auth()
    _inat_auth.start()

    yield
    _stop_digest.set()
    _hb_sync.stop()
    _bb_sync.stop()
    _inat_auth.stop()
    storage_mgr.stop()
    tailscale_mgr.stop()
    activity_log_mgr.stop()
    logger.info("Chirp Server shutting down.")


# ── Auth middleware ────────────────────────────────────────────────────────────
UNPROTECTED = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/health",
    "/api/v1/changelog",     # readable by all users, auth or not
    "/api/v1/map-config",    # map tile key (CHIRP_CARTO_KEY), public like the tiles themselves
    "/api/v1/ios-resign/event",   # X-API-Key (stack device key), see api/ios_resign.py
    "/api/v1/support",            # support / feature form (rate-limited), see api/support.py
    "/api/v1/site-requests",      # public sign-up form on /about (rate-limited), see api/site_requests.py
    "/api/v1/push-relay/send",    # relay token, see api/push_relay.py
}

def _is_media_path(path: str) -> bool:
    import re
    return bool(re.search(
        r"/api/v1/(recordings/upload"
        r"|recordings/auth-test"
        # No \$ anchor below, so re.search() does prefix matching — e.g.
        # "recordings/{id}/audio" already matches "recordings/{id}/audio/enhanced"
        # too, since anything is allowed to follow. Verified this covers the
        # enhanced-audio endpoints without listing them separately.
        r"|recordings/[^/]+/(audio|spectrogram|clip/[^/]+|waveform)"
        r"|birds/[^/]+/(photo|range-map|range-map-legend)"
        r"|birds/[^/]+/calls/[^/]+"
        r"|birds/photos/[^/]+/file"
        r"|bat-activity/upload"
        r"|bat-activity/[^/]+/audio"
        r"|night-calls/(upload|accepting)"
        r"|night-calls/[^/]+/(audio|spectrogram)"
        r"|recordings/shared/[^/]+"
        r"|devices/pair"
        r"|devices/[^/]+/(config|heartbeat)"
        r"|devices/discover"
        r"|devices/push-credentials"
        r"|devices/[^/]+/ssh"
        r"|auth/me/photo/[^/]+"
        r"|logs/server/stream)", path
    ))

# ── Viewer accounts are read-only (plus notes) ─────────────────────────────
# Every POST/PUT/PATCH/DELETE from a "viewer" is refused unless it is one of
# the things a viewer is meant to do: their own account, switching location,
# notifications, notes, Live Detect analysis, share links and loading bird
# info. Before this, a viewer could delete or edit recordings through the API.
_VIEWER_WRITE_OK = re.compile(
    r"^/api/v1/("
    r"auth/(login|logout|register|me/.*|activity/ping)"
    r"|instances/(switch|join)"
    r"|notifications(/.*)?"
    r"|moderation/(report|blocks(/[^/]+)?)"
    r"|push/.*"
    r"|diagnostics/client"
    r"|recordings/ai-warm"
    r"|recordings/[^/]+/(comments(/[^/]+)?|share)"
    r"|birds/([^/]+/comments(/[^/]+)?|ensure/.*)"
    r"|live-detect/analyze"
    r")$"
)


def viewer_may_write(method: str, path: str) -> bool:
    return method in ("GET", "HEAD", "OPTIONS") or bool(_VIEWER_WRITE_OK.match(path))


# Apple Watch sign-ins (POST /auth/watch-token) only run Live Detect and
# play recent recordings (api/watch.py).
_WATCH_OK = re.compile(r"^/api/v1/(live-detect/(analyze|save-session)|auth/me|watch/recent|watch/audio/[0-9A-Za-z-]+)$")


def watch_may_use(path: str) -> bool:
    return bool(_WATCH_OK.match(path))


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (not path.startswith("/api/v1/")
                or path in UNPROTECTED
                or path.startswith("/assets/")
                or _is_media_path(path)):
            return await call_next(request)

        # ── Check auth_enabled (cached, avoids DB hit per request) ────────────
        cached_auth = settings_cache.get("auth_enabled")
        if cached_auth is None:
            try:
                from .database import SessionLocal
                from .models import AppSettings
                with SessionLocal() as db:
                    s = db.query(AppSettings).first()
                    cached_auth = bool(s.auth_enabled) if s and s.auth_enabled is not None \
                                  else settings.auth_enabled
            except Exception:
                cached_auth = settings.auth_enabled
            settings_cache.set("auth_enabled", cached_auth)

        if not cached_auth:
            return await call_next(request)

        # ── Verify JWT ────────────────────────────────────────────────────────
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        token = auth_header[7:]

        # Check user cache first — avoids DB query for every authenticated request
        cached_user = user_token_cache.get(token)
        if cached_user is None:
            from .api.auth import verify_token
            payload = verify_token(token)
            if not payload:
                return JSONResponse({"detail": "Invalid or expired token"}, status_code=401)
            try:
                from .database import SessionLocal
                from .models import User
                with SessionLocal() as db:
                    user = db.query(User).filter(
                        User.username == payload.get("sub")
                    ).first()
                    if not user or not user.active:
                        return JSONResponse({"detail": "User not found"}, status_code=401)
                    cached_user = {"username": user.username, "role": user.role, "active": True,
                                   "scope": payload.get("scope")}
            except Exception:
                return JSONResponse({"detail": "Auth error"}, status_code=401)
            user_token_cache.set(token, cached_user)
        elif not cached_user.get("active"):
            return JSONResponse({"detail": "User not found"}, status_code=401)

        if cached_user.get("scope") == "watch" and not watch_may_use(path):
            return JSONResponse({"detail": "The watch sign-in only works for Live Detect."}, status_code=403)

        if cached_user.get("role") == "viewer" and not viewer_may_write(request.method, path):
            return JSONResponse({"detail": "This account is view-only. Ask an admin for submitter access."},
                                status_code=403)

        return await call_next(request)


app = FastAPI(
    title="Chirp Server",
    description="Automated Bird Call Detection & Identification Server",
    # Reads the same VERSION file api/health() and settings.app_version read
    # — previously this was an independently hardcoded literal string with a
    # comment claiming it was "updated by VERSION file at runtime," which
    # was never actually true (it was a plain string, no read happening at
    # all), so this and the /health endpoint's version could silently drift
    # apart, which is exactly what caused VersionBadge.jsx in Settings to
    # keep showing a stale version long after this value had moved on.
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# GZip compression — compresses API responses and static assets >1KB
# 754KB JS bundle → ~215KB over the wire (same as what Vite reports for gzip)
# GZip compression — compresses API responses and static assets >1KB
# 754KB JS bundle → ~215KB over the wire (same as what Vite reports for gzip)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def _log_validation_errors(request: Request, exc: RequestValidationError):
    """
    Reported directly: a multipart file upload consistently 422'd with
    "file: Field required" even though the same file uploads fine via
    chirp-device to a structurally-identical endpoint, and the file was
    confirmed present client-side. FastAPI's own request validation
    happens BEFORE the route handler's own code ever runs, so nothing
    logged inside the endpoint itself can ever fire for this — this is
    the one place that reliably does, at the exact moment validation
    fails, for every endpoint in the app.
    Only inspects HEADERS, never touches the body/stream — reading the
    body here, after python-multipart has already tried and failed to
    parse it, risks either double-consuming an already-exhausted stream
    or reporting misleading bytes, neither of which this needs. Content-
    Length and Content-Type alone answer the one question that matters:
    did the request arrive at this app with the file's bytes intact and
    a correctly-formed multipart boundary, or did something upstream
    (a proxy, a tunnel, the browser itself) already drop or mangle it
    before this process ever saw it.
    """
    logger.warning(
        "Validation error on %s %s — Content-Type=%r Content-Length=%r — errors=%s",
        request.method, request.url.path,
        request.headers.get("content-type"),
        request.headers.get("content-length"),
        exc.errors(),
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.middleware("http")
async def _cache_hashed_assets(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/assets/"):
        # Vite content-hashes every filename here — the same URL never
        # changes content across deploys. Without an explicit header,
        # browsers fell back to weak heuristic caching instead of
        # treating these as immutable.
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif request.url.path == "/sw.js":
        # Opposite policy, opposite reason: this file had no explicit
        # Cache-Control at all, so it fell back to whatever policy sits
        # in front of the server. A service worker is the update
        # mechanism for a PWA; caching it defeats the whole versioning
        # scheme (see scripts/stamp-sw-version.mjs). no-cache still
        # allows storing it but forces revalidation on every request.
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    elif request.url.path in _REVALIDATE_PATHS:
        # Manifest and icons keep fixed file names, so browsers must check
        # for a new version (cheap: FileResponse sends ETag/Last-Modified).
        # The page links icons with ?v=VERSION so installs see a new URL.
        response.headers["Cache-Control"] = "no-cache"
    return response



# Retired hostnames (CHIRP_REDIRECT_HOSTS, comma list) send people to
# CHIRP_REDIRECT_TO, same path and query. Pages and media get a 301; API
# calls get 410 with the new address, so a station still pointed here
# never re-posts its uploads to a server it has a different key for.
# Other hostnames (e.g. the LAN address) are untouched. Off when unset.
_REDIRECT_HOSTS = {h.strip().lower() for h in os.environ.get("CHIRP_REDIRECT_HOSTS", "").split(",") if h.strip()}
_REDIRECT_TO = os.environ.get("CHIRP_REDIRECT_TO", "").rstrip("/")


@app.middleware("http")
async def _retired_host_redirect(request, call_next):
    if _REDIRECT_HOSTS and _REDIRECT_TO:
        host = (request.headers.get("host") or "").split(":")[0].lower()
        if host in _REDIRECT_HOSTS:
            path = request.url.path
            target = _REDIRECT_TO + path + (f"?{request.url.query}" if request.url.query else "")
            if path.startswith("/api/") and path not in ("/api/v1/health",):
                return JSONResponse(status_code=410, content={
                    "detail": f"This server has moved to {_REDIRECT_TO}.", "moved_to": _REDIRECT_TO})
            from fastapi.responses import RedirectResponse
            return RedirectResponse(target, status_code=301 if request.method in ("GET", "HEAD") else 308)
    return await call_next(request)


_REVALIDATE_PATHS = {"/manifest.json", "/favicon.ico", "/favicon.svg", "/icon-192.png",
                     "/icon-512.png", "/apple-touch-icon.png", "/logo.svg"}

app.include_router(recordings.router, prefix="/api/v1/recordings", tags=["recordings"])
from .api import ios_resign as ios_resign_router
app.include_router(ios_resign_router.router, prefix="/api/v1/ios-resign", tags=["ios-resign"])
app.include_router(birds.router, prefix="/api/v1/birds", tags=["birds"])
app.include_router(app_settings.router, prefix="/api/v1/settings", tags=["settings"])
app.include_router(auth_router.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(instances_router.router, prefix="/api/v1/instances", tags=["instances"])
app.include_router(admin_panel_router.router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(devices_router.router, prefix="/api/v1/devices", tags=["devices"])
app.include_router(bat_activity_router.router, prefix="/api/v1/bat-activity", tags=["bat-activity"])
app.include_router(night_calls_router.router, prefix="/api/v1/night-calls", tags=["night-calls"])
app.include_router(logs_router.router, prefix="/api/v1/logs", tags=["logs"])
app.include_router(diagnostics_router.router, prefix="/api/v1/diagnostics", tags=["diagnostics"])
app.include_router(push_router.router, prefix="/api/v1/push", tags=["push"])
app.include_router(notifications_router.router, prefix="/api/v1/notifications", tags=["notifications"])
from .api import moderation as moderation_router
app.include_router(moderation_router.router, prefix="/api/v1/moderation", tags=["moderation"])
app.include_router(techdocs_router.router, prefix="/api/v1/techdocs", tags=["techdocs"])
app.include_router(live_detect_router.router, prefix="/api/v1/live-detect", tags=["live-detect"])
app.include_router(watch_router.router, prefix="/api/v1/watch", tags=["watch"])
app.include_router(near_misses_router.router, prefix="/api/v1/near-misses", tags=["near-misses"])
from .api import site_requests as site_requests_router
from .api import push_relay as push_relay_router
app.include_router(site_requests_router.router, prefix="/api/v1/site-requests", tags=["site-requests"])
app.include_router(site_requests_router.admin_router, prefix="/api/v1/admin/site-requests", tags=["admin"])
app.include_router(push_relay_router.router, prefix="/api/v1/push-relay", tags=["push-relay"])
app.include_router(push_relay_router.admin_router, prefix="/api/v1/admin/relay-servers", tags=["admin"])
from .api import support as support_router
app.include_router(support_router.router, prefix="/api/v1/support", tags=["support"])
app.include_router(support_router.admin_router, prefix="/api/v1/admin/support", tags=["admin"])


@app.get("/icon.svg", include_in_schema=False)
async def serve_icon():
    import os
    logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chirp-logo.svg")
    if os.path.exists(logo_path):
        # Same missing-Cache-Control gap found and fixed across several
        # photo/file endpoints this same pass (see birds.py's
        # get_bird_photo for the full reasoning) — this one's requested
        # on every single page load by every browser, for the app's own
        # static branding asset that essentially never changes. A week
        # rather than /assets/*'s full year+immutable, since — unlike
        # those content-hashed filenames, which get a brand-new URL
        # automatically whenever their content changes — this exact URL
        # would stay cached under an old logo for the full cache
        # duration if it were ever intentionally updated.
        return FileResponse(logo_path, media_type="image/svg+xml",
                             headers={"Cache-Control": "public, max-age=604800"})
    from fastapi.responses import Response
    return Response(content="<svg xmlns='http://www.w3.org/2000/svg'/>", media_type="image/svg+xml")


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "version": settings.app_version}


@app.get("/api/v1/map-config")
async def map_config():
    """CARTO basemap key for the dark map tiles (CHIRP_CARTO_KEY). CARTO
    has required one since 2026; tiles without it carry an 'API key
    required' watermark. The key travels in every tile URL anyway, so it's
    public; restrict it to this site's domain in the CARTO dashboard."""
    return {"carto_key": os.environ.get("CHIRP_CARTO_KEY", "").strip() or None}


@app.get("/api/v1/changelog")
async def serve_changelog():
    """Serve CHANGELOG.md as plain text for the in-app changelog page."""
    import os
    from fastapi.responses import PlainTextResponse
    candidates = [
        "/app/CHANGELOG.md",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "CHANGELOG.md"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return PlainTextResponse(open(p).read(), media_type="text/plain; charset=utf-8")
    return PlainTextResponse("# Changelog\n\nNot found.", media_type="text/plain")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                if msg == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "heartbeat"}))
    except (WebSocketDisconnect, Exception):
        manager.disconnect(websocket)


STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    try:
        assets_dir = STATIC_DIR / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    except Exception:
        pass

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path.strip("/") == "about":   # public promotional page (frontend/public/about.html)
            full_path = "about.html"
        static_file = STATIC_DIR / full_path
        if static_file.is_file():
            return FileResponse(str(static_file))
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return HTMLResponse("<h1>Chirp</h1>")
else:
    @app.get("/", include_in_schema=False)
    async def root():
        return HTMLResponse("""<html><body style="font-family:monospace;background:#0a0f14;color:#4ade80;padding:2rem">
        <h1>🐦 Chirp Server Running</h1><p>API: <a href="/api/docs" style="color:#06b6d4">/api/docs</a></p>
        </body></html>""")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    uvicorn.run("app.main:app", host=settings.host, port=settings.port,
                reload=settings.debug, log_level="info")
