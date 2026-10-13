"""
Chirp Server — Dashboard Cache Warmer

Reported directly: Dashboard's "last detection" text, today's detections
list, and the stat cards all noticeably lagged on load. Traced this to a
real gap in the caching added earlier: /stats and /statistics/dashboard-
summary cache their result for 45 seconds, but that only helps a REPEAT
request within that window — a person's very first Dashboard visit of a
session (or the first one after the cache has gone cold) still pays the
full 8-11 query cost, which is exactly what "an extra couple seconds"
sounds like.

This background thread proactively re-runs those same two queries every
30 seconds — comfortably under the 45-second cache TTL, so the cache
entry a visit would read is never more than 30 seconds stale and
never fully expires between refreshes. The two endpoint functions are
called directly (they're still plain Python functions under FastAPI's
@router.get decorator; nothing prevents invoking them outside an HTTP
request), which populates statistics_cache exactly as if a browser had
just requested them — a real Dashboard visit becomes a cache hit
essentially all the time, at the cost of one extra query cycle every 30
seconds regardless of whether anyone's looking.

Same start()/stop()/threaded-loop shape as StorageManager and
ActivityLogManager, deliberately — one consistent pattern for every
background task in this app, not a new one invented per feature.
"""

import logging
import threading
from typing import Optional

logger = logging.getLogger("chirp.dashboard_cache_warmer")


class DashboardCacheWarmer:
    WARM_INTERVAL_SECONDS = 30  # comfortably under statistics_cache's 45s TTL

    def __init__(self, db_factory):
        self._db_factory = db_factory
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._thread = threading.Thread(
            target=self._loop, name="DashboardCacheWarmer", daemon=True
        )
        self._thread.start()
        logger.info("DashboardCacheWarmer started (every %ds)", self.WARM_INTERVAL_SECONDS)

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)

    def warm_now(self) -> dict:
        """Run one warming pass synchronously. Safe to call from an API endpoint."""
        return self._warm()

    def _loop(self):
        self._stop_event.wait(15)  # let the DB finish initializing first
        while not self._stop_event.is_set():
            try:
                self._warm()
            except Exception as e:
                logger.error("DashboardCacheWarmer error: %s", e, exc_info=True)
            self._stop_event.wait(self.WARM_INTERVAL_SECONDS)

    def _warm(self) -> dict:
        # Local imports — avoids a circular import at module load time
        # (recordings.py itself imports from several places that could
        # plausibly import this module back in the future).
        from ..api.recordings import recording_stats, dashboard_summary, yard_pulse

        summary = {"stats_warmed": 0, "dashboard_summary_warmed": 0, "yard_pulse_warmed": 0, "instances_seen": 0, "error": None}
        # Iterates every real instance's own database — the original
        # single self._db_factory() call always operated on the one
        # legacy database nothing real ever uses, so this warmer was
        # never actually helping any real location's dashboard; see
        # this file's own top-of-module docstring for the full story
        # on how that surfaced as a dashboard reverting to empty on a
        # fixed timer. iter_instance_sessions() also now sets the same
        # per-instance context TTLCache uses to scope its own keys, so
        # each instance's warm pass correctly reaches only its own
        # cache entries, not any other instance's.
        from ..instance_registry import iter_instance_sessions
        for instance, db in iter_instance_sessions():
            summary["instances_seen"] += 1
            try:
                # Only the default 24h period — the one every Dashboard load
                # requests. Other periods are only ever requested by
                # someone explicitly switching the chart's own time filter,
                # which is a deliberate, infrequent action already fine
                # paying its own one-time query cost rather than every
                # period being kept warm at all times for no benefit.
                recording_stats(period="24h", db=db)
                summary["stats_warmed"] += 1
                dashboard_summary(db=db)
                summary["dashboard_summary_warmed"] += 1
                # yard_pulse() has had its own 45s statistics_cache entry
                # for a while but was never actually included here —
                # a real gap, not a deliberate omission: it's Dashboard-
                # facing exactly like the two calls above, loads on
                # every visit, and does its own genuine per-species
                # day-by-day computation, so it deserves the same
                # proactive keep-warm treatment, per instance.
                yard_pulse(db=db)
                summary["yard_pulse_warmed"] += 1
            except Exception as e:
                summary["error"] = f"{instance.name}: {e}"
                logger.warning("Dashboard cache warm pass failed for instance %s (%s): %s", instance.id, instance.name, e)
        return summary
