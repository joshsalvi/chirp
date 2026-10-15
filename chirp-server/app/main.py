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
from .database import init_db
from .api import recordings, birds
from .api import app_settings
from .api import auth as auth_router
from .api import devices as devices_router
from .api import logs as logs_router
from .api import bat_activity as bat_activity_router
from .api import night_calls as night_calls_router
from .api import diagnostics as diagnostics_router
from .api import push as push_router
from .api import notifications as notifications_router
from .api import techdocs as techdocs_router
from .api import live_detect as live_detect_router
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
    from .database import SessionLocal as _SL_startup
    from .models import BirdProfile as _BP_startup
    try:
        with _SL_startup() as _db_s:
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
                logger.info("Queued %d birds for range map re-enrichment", reset_count)
    except Exception as _e:
        logger.warning("Startup bird reset error: %s", _e)

    # Bat profile photo: retry if profile exists but photo is missing
    try:
        from .database import SessionLocal as _SL_bat
        from .models import BirdProfile as _BP_bat
        from .services.bird_enricher import BirdEnricher
        with _SL_bat() as _db_bat:
            bat = _db_bat.query(_BP_bat).filter(_BP_bat.label == "Bat").first()
            if bat and (not bat.photo_path or not os.path.exists(bat.photo_path or "")):
                enricher = BirdEnricher(_db_bat)
                enricher._fetch_bat_photo(bat)
                logger.info("Bat profile photo refresh on startup")
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
    # own manager, closing a real gap: a device could already be reached
    # over Tailscale from this server's own SSH terminal, but the server
    # itself had no Tailscale awareness at all. Starts from env vars
    # (CHIRP_TAILSCALE_ENABLED etc. — a valid bootstrap path, e.g. for a
    # docker-only setup with no interest in touching the UI), then
    # immediately overridden by whatever's saved in AppSettings if
    # anything is — the DB is the more recent, user-set value once
    # someone's used the Settings → Server Network "Save & Connect"
    # button, which is the point of making this a UI toggle instead of
    # only an env var.
    from .services.tailscale_manager import TailscaleManager
    tailscale_mgr = TailscaleManager(_settings)
    tailscale_mgr.start()
    app.state.tailscale_manager = tailscale_mgr
    from .services.device_net import set_tailscale_manager as _set_ts_mgr
    _set_ts_mgr(tailscale_mgr)
    try:
        from .models import AppSettings as _AppSettings_ts
        _ts_db = SessionLocal()
        _ts_s = _ts_db.query(_AppSettings_ts).filter(_AppSettings_ts.id == 1).first()
        if _ts_s and _ts_s.tailscale_auth_key:
            tailscale_mgr.reconfigure(
                enabled=bool(_ts_s.tailscale_enabled),
                auth_key=_ts_s.tailscale_auth_key,
                login_server=_ts_s.tailscale_login_server or "",
                hostname=_ts_s.tailscale_hostname or "",
            )
        _ts_db.close()
    except Exception as _ts_e:
        logger.warning("Could not load saved Tailscale config from AppSettings, using env vars: %s", _ts_e)

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

    def _digest_loop():
        # Digest push and email, each at its own local hour
        # (services/scheduled_push.daily_digest_tick keeps the day sent).
        from .database import SessionLocal as _SL_dh
        from .services.scheduled_push import daily_digest_tick
        from .services.device_alerts import device_offline_tick
        while not _stop_digest.wait(60):
            try:
                with _SL_dh() as _db_dh:
                    sent = daily_digest_tick(_db_dh)
                    if sent:
                        logger.info("Daily digest sent: %s", ", ".join(sent))
                    alerts = device_offline_tick(_db_dh)
                    if alerts:
                        logger.info("Station alerts: %s", ", ".join(alerts))
            except Exception as _de:
                logger.warning("Daily digest error: %s", _de)

    _digest_thread = _threading.Thread(target=_digest_loop, daemon=True, name="digest")
    _digest_thread.start()

    # Night flight calls (Experimental): finish chunks a restart left
    # waiting and drop failed audio (services/nighthawk_service.py).
    def _night_calls_loop():
        from .database import SessionLocal as _SL
        from .services import nighthawk_service as _nh
        while not _stop_digest.wait(300):
            if _nh.available():
                continue
            _db_nc = _SL()
            try:
                _nh.cleanup(_db_nc)
                for _cid in _nh.pending_ids(_db_nc):
                    _nh.process_chunk(_cid)
            except Exception as _ne:
                logger.warning("Night calls error: %s", _ne)
            finally:
                _db_nc.close()

    _threading.Thread(target=_night_calls_loop, daemon=True, name="night-calls").start()

    # Scheduled pushes: Daily Journal 6 pm, Weekly Journal Sunday noon,
    # watched-bird summaries 7 pm (local time). See services/scheduled_push.py.
    _stop_sched_push = _threading.Event()

    def _scheduled_push_loop():
        from .database import SessionLocal as _SL_sp
        from .services.scheduled_push import tick as _sp_tick
        while not _stop_sched_push.wait(60 - _dt_mod.datetime.utcnow().second % 60 or 60):
            _db_sp = _SL_sp()
            try:
                _sent = _sp_tick(_db_sp)
                if _sent:
                    logger.info("Scheduled pushes: %s", ", ".join(_sent))
            except Exception as _spe:
                logger.warning("Scheduled push error: %s", _spe)
            finally:
                _db_sp.close()

    import datetime as _dt_mod
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
        while not _stop_summary.wait(60):  # check every minute
            try:
                from .database import SessionLocal as _SL_ds
                from .models import AppSettings as _AS_ds
                with _SL_ds() as _db_ds:
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
                try:
                    from .services.daily_summary import generate_daily_summary
                    from .database import SessionLocal as _SL_ds2
                    with _SL_ds2() as _db_ds2:
                        generate_daily_summary(_db_ds2)
                except Exception as _se:
                    logger.warning("Daily summary scheduler error: %s", _se)
                _time.sleep(61)  # skip the rest of this minute

    _summary_thread = _threading.Thread(target=_daily_summary_loop, daemon=True, name="daily-summary")
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
        while not _stop_weekly.wait(60):  # check every minute
            try:
                from .database import SessionLocal as _SL_ws
                from .models import AppSettings as _AS_ws
                with _SL_ws() as _db_ws:
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
                try:
                    from .services.weekly_summary import generate_weekly_summary
                    from .database import SessionLocal as _SL_ws2
                    with _SL_ws2() as _db_ws2:
                        generate_weekly_summary(_db_ws2)
                except Exception as _se:
                    logger.warning("Weekly summary scheduler error: %s", _se)
                _time.sleep(61)  # skip the rest of this minute

    _weekly_thread = _threading.Thread(target=_weekly_summary_loop, daemon=True, name="weekly-summary")
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
        while not _stop_profile_refresh.wait(60):  # check every minute
            try:
                from .database import SessionLocal as _SL_pr
                from .models import AppSettings as _AS_pr
                with _SL_pr() as _db_pr:
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
                logger.warning("Profile summary refresh scheduler config error: %s", _pe)
                continue
            now_local_pr = _dt.now(_ZoneInfo("UTC")).astimezone(_tz_pr)
            if now_local_pr.hour == _hour_pr and now_local_pr.minute == 0:
                try:
                    from .services.profile_summary import refresh_stale_profile_summaries
                    from .database import SessionLocal as _SL_pr2
                    with _SL_pr2() as _db_pr2:
                        refresh_stale_profile_summaries(_db_pr2, max_age_days=_days_pr)
                except Exception as _pe2:
                    logger.warning("Profile summary refresh error: %s", _pe2)
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
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo as _ZoneInfo
        while not _stop_backup.wait(60):  # check every minute
            try:
                from .database import SessionLocal as _SL_bk
                from .models import AppSettings as _AS_bk
                with _SL_bk() as _db_bk:
                    _s_bk = _db_bk.query(_AS_bk).filter(_AS_bk.id == 1).first()
                    if not (_s_bk and (_s_bk.auto_backup_enabled if _s_bk.auto_backup_enabled is not None else True)):
                        continue
                    _hour_bk = int(_s_bk.auto_backup_hour) if _s_bk.auto_backup_hour is not None else 3
                    _retain_bk = int(_s_bk.auto_backup_retention_count) if _s_bk.auto_backup_retention_count is not None else 14
                    try:
                        _tz_bk = _ZoneInfo(_s_bk.timezone or "UTC")
                    except Exception:
                        _tz_bk = _ZoneInfo("UTC")
            except Exception as _be:
                logger.warning("Auto-backup scheduler config error: %s", _be)
                continue
            now_local_bk = _dt.now(_ZoneInfo("UTC")).astimezone(_tz_bk)
            if now_local_bk.hour == _hour_bk and now_local_bk.minute == 0:
                try:
                    from .services.backup_service import record_backup_result
                    from .config import settings as _cfg_bk
                    from .database import SessionLocal as _SL_bk2
                    from .models import AppSettings as _AS_bk2
                    db_path_bk = _cfg_bk.db_url.replace("sqlite:////", "/").replace("sqlite:///", "")
                    with _SL_bk2() as _db_bk2:
                        _s_bk2 = _db_bk2.query(_AS_bk2).filter(_AS_bk2.id == 1).first()
                        if _s_bk2:
                            result = record_backup_result(_db_bk2, _s_bk2, db_path_bk, _cfg_bk.data_dir, _retain_bk)
                            if "error" in result:
                                logger.warning("Automatic backup failed: %s", result["error"])
                            else:
                                logger.info("Automatic backup complete: %s", result)
                except Exception as _be2:
                    logger.warning("Automatic backup failed: %s", _be2)
                _time.sleep(61)  # skip the rest of this minute

    _auto_backup_thread = _threading.Thread(target=_auto_backup_loop, daemon=True, name="auto-backup")
    _auto_backup_thread.start()

    # Sweeps for orphaned Live Detect poll clips — see
    # services/live_detect_cleanup.py's own module docstring for the
    # full story on why these need sweeping at all, not just hiding
    # from the list. Runs far less often than the backup loop above
    # (these accumulate on the order of minutes of someone leaving a
    # page open, not something that needs minute-level responsiveness
    # to clean up).
    _stop_ld_cleanup = _threading.Event()

    def _live_detect_cleanup_loop():
        while not _stop_ld_cleanup.wait(3600):  # once per hour
            from .database import SessionLocal
            from .services.live_detect_cleanup import cleanup_orphaned_live_detect_clips
            from .config import settings as _cfg_ld
            db_ld = SessionLocal()
            try:
                removed = cleanup_orphaned_live_detect_clips(
                    db_ld, _cfg_ld.recordings_dir, _cfg_ld.spectrograms_dir, _cfg_ld.clips_dir,
                )
                if removed:
                    logger.info("Live Detect cleanup removed %d orphaned clip(s)", removed)
            except Exception as _le:
                logger.warning("Live Detect cleanup failed: %s", _le)
            finally:
                db_ld.close()

    _live_detect_cleanup_thread = _threading.Thread(target=_live_detect_cleanup_loop, daemon=True, name="live-detect-cleanup")
    _live_detect_cleanup_thread.start()

    # Auto-purge sweep: with Auto-purge on, recordings that show nothing
    # (the list's "Unknown" cards) are deleted every 15 minutes, not only
    # when they're uploaded (api/app_settings.py).
    def _empty_purge_loop():
        _stop_ld_cleanup.wait(120)
        while True:
            from .database import SessionLocal
            from .api.app_settings import sweep_empty_recordings
            db_ep = SessionLocal()
            try:
                n = sweep_empty_recordings(db_ep)
                if n:
                    logger.info("Auto-purge sweep removed %d recording(s)", n)
            except Exception as _ee:
                logger.warning("Auto-purge sweep failed: %s", _ee)
            finally:
                db_ep.close()
            if _stop_ld_cleanup.wait(900):
                break

    _threading.Thread(target=_empty_purge_loop, daemon=True, name="empty-purge-sweep").start()

    # One-time, startup-triggered spectrogram regen for the detection-
    # color spread fix — see AppSettings' own
    # spectrograms_regenerated_for_color_fix column docstring for why
    # this can't just rely on the normal cache-invalidation path.
    # Genuinely background: a server with a large recordings library
    # could take a while to work through, and nothing else should wait
    # on it — existing spectrograms keep serving (with the old colors)
    # until each one's own turn comes up in this sweep.
    def _color_fix_regen_startup():
        from .api.app_settings import _regenerate_spectrograms_for_color_fix_bg
        try:
            _regenerate_spectrograms_for_color_fix_bg()
        except Exception as _cfe:
            logger.warning("Spectrogram color-fix regen failed: %s", _cfe)

    _threading.Thread(target=_color_fix_regen_startup, daemon=True, name="spectrogram-color-fix-regen").start()

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
    "/api/v1/ios-resign/event",   # X-API-Key (stack device key), see api/ios_resign.py
    "/api/v1/support",            # support / feature form (rate-limited), see api/support.py
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


# Apple Watch sign-ins (POST /auth/watch-token) only run Live Detect.
_WATCH_OK = re.compile(r"^/api/v1/(live-detect/(analyze|save-session)|auth/me)$")


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
    Reported directly on chirp-server-instances: a multipart file upload
    consistently 422'd with "file: Field required" even though the same
    file uploads fine via chirp-device to a structurally-identical
    endpoint, and the file was confirmed present client-side. FastAPI's
    own request validation happens BEFORE the route handler's own code
    ever runs, so nothing logged inside the endpoint itself can ever
    fire for this — this is the one place that reliably does, at the
    exact moment validation fails, for every endpoint in the app. Added
    here too even though this fork doesn't have instances' multi-tenant
    get_db, for the same diagnostic value and so both forks stay
    consistent — this handler doesn't depend on which get_db is in play.
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


_REVALIDATE_PATHS = {"/manifest.json", "/favicon.ico", "/favicon.svg", "/icon-192.png",
                     "/icon-512.png", "/apple-touch-icon.png", "/logo.svg"}

app.include_router(recordings.router, prefix="/api/v1/recordings", tags=["recordings"])
from .api import ios_resign as ios_resign_router
app.include_router(ios_resign_router.router, prefix="/api/v1/ios-resign", tags=["ios-resign"])
app.include_router(birds.router, prefix="/api/v1/birds", tags=["birds"])
app.include_router(app_settings.router, prefix="/api/v1/settings", tags=["settings"])
app.include_router(auth_router.router, prefix="/api/v1/auth", tags=["auth"])
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
app.include_router(near_misses_router.router, prefix="/api/v1/near-misses", tags=["near-misses"])
from .api import support as support_router
app.include_router(support_router.router, prefix="/api/v1/support", tags=["support"])


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
