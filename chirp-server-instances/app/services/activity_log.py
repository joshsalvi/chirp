"""
Chirp Server — Activity Log

Records login and page-view events for admin visibility. Deliberately
minimal in scope — see models.ActivityLog for exactly what is and isn't
stored. This module has two pieces:

1. log_activity() — a small best-effort helper called from api/auth.py at
   the moment a login, failed login, logout, or page-view happens. Never
   raises: a logging failure must never break the request that triggered
   it (identical philosophy to storage_manager.py's cleanup pass).

2. ActivityLogManager — a background thread (same pattern as
   StorageManager) that purges rows older than
   AppSettings.activity_log_retention_days on startup and then every hour.
   Retention of 0 means "keep forever" — no purging happens.
"""

import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

logger = logging.getLogger("chirp.activity_log")

# Paths never worth logging even if the frontend beacons them (health checks,
# the beacon endpoint itself if ever called in a loop, etc.) — belt-and-braces
# against a runaway feedback loop, not expected to trigger in normal use.
_NOISY_PATH_PREFIXES = ("/api/v1/auth/activity/ping",)

_MAX_PATH_LEN = 300
_MAX_UA_LEN = 300


def _get_settings(db: Session):
    from ..models import AppSettings
    return db.query(AppSettings).filter(AppSettings.id == 1).first()


def _client_ip(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    # Respect a reverse-proxy header if present (e.g. behind nginx/Traefik),
    # falling back to the direct connection address.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def log_activity(
    db: Session,
    event_type: str,
    user=None,
    username: Optional[str] = None,
    path: Optional[str] = None,
    request: Optional[Request] = None,
) -> None:
    """
    Best-effort activity log write. Silently does nothing if:
      - activity_log_enabled is False
      - the path is in the noisy-path skip list

    IP/user-agent are only recorded when activity_log_track_ip is True.
    Never raises — a failure here must not break login/navigation.
    """
    try:
        if path and path.startswith(_NOISY_PATH_PREFIXES):
            return

        s = _get_settings(db)
        if s is not None and s.activity_log_enabled is False:
            return
        track_ip = True if (s is None or s.activity_log_track_ip is None) else bool(s.activity_log_track_ip)

        from ..models import ActivityLog

        row = ActivityLog(
            user_id=getattr(user, "id", None),
            username=username or getattr(user, "username", None),
            event_type=event_type,
            path=(path[:_MAX_PATH_LEN] if path else None),
            ip_address=(_client_ip(request) if track_ip else None),
            user_agent=((request.headers.get("user-agent", "")[:_MAX_UA_LEN] or None) if (track_ip and request) else None),
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
    except Exception as e:
        # Never let activity logging break the caller's actual request.
        logger.warning("activity log write failed (event_type=%s): %s", event_type, e)
        try:
            db.rollback()
        except Exception:
            pass


class ActivityLogManager:
    """
    Background purge loop for the activity log, mirroring
    storage_manager.StorageManager's start()/stop()/threaded-loop shape.
    """

    PURGE_INTERVAL_SECONDS = 3600  # run every hour, same cadence as StorageManager

    def __init__(self, db_factory):
        self._db_factory = db_factory
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._thread = threading.Thread(
            target=self._loop, name="ActivityLogManager", daemon=True
        )
        self._thread.start()
        logger.info("ActivityLogManager started")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)

    def run_purge_now(self) -> dict:
        """Run a purge pass synchronously and return a summary dict. Safe to call from an API endpoint."""
        return self._run_purge()

    def _loop(self):
        self._stop_event.wait(20)  # let the DB finish initializing first
        while not self._stop_event.is_set():
            try:
                self._run_purge()
            except Exception as e:
                logger.error("ActivityLogManager purge error: %s", e, exc_info=True)
            self._stop_event.wait(self.PURGE_INTERVAL_SECONDS)

    def _run_purge(self) -> dict:
        summary = {"purged": 0, "retention_days": None}
        try:
            with self._db_factory() as db:
                s = _get_settings(db)
                retention = s.activity_log_retention_days if s else 90
                summary["retention_days"] = retention
                if not retention:  # 0 or None => keep forever
                    return summary
                from ..models import ActivityLog
                cutoff = datetime.utcnow() - timedelta(days=retention)
                deleted = (
                    db.query(ActivityLog)
                    .filter(ActivityLog.created_at < cutoff)
                    .delete(synchronize_session=False)
                )
                db.commit()
                summary["purged"] = deleted
                if deleted:
                    logger.info("ActivityLogManager purged %d event(s) older than %d days", deleted, retention)
        except Exception as e:
            logger.error("ActivityLogManager purge failed: %s", e, exc_info=True)
        return summary
