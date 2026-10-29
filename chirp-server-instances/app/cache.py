"""
Chirp — Simple in-process cache for hot, rarely-changing data.

Used to eliminate repeated DB round-trips for:
  - AppSettings (auth_enabled, display flags) — cached 30s
  - JWT-validated user sessions — cached per token, 5 min TTL

All caches are module-level so they survive across requests in the same worker.
Thread-safe: uses threading.Lock for writes, atomic reads on CPython.
"""

import threading
import time
from typing import Any

_NOT_SET = object()


class TTLCache:
    """Simple dict-based TTL cache. Thread-safe for CPython.

    Investigated and fixed directly after a real report: a Dashboard
    kept reverting to "no detections" every ~30 seconds on a real,
    populated location. Root cause was two layers deep. First: every
    cache key in this module (statistics_cache, life_list_cache,
    settings_cache, etc.) was built with no instance identifier at
    all — "dashboard_stats:24h" is the same string regardless of which
    of this server's locations asked for it, so in a multi-tenant
    deployment, whichever location's request ran most recently
    silently overwrote what every OTHER location's dashboard would
    see next. Second, and what made it specifically "every 30
    seconds": DashboardCacheWarmer proactively re-populates this exact
    cache on a timer, using the ORIGINAL, single, legacy database
    (never any real location's own data, since a periodic timer has
    no request context to resolve which location it should even be
    for) — so every 30 seconds, EVERY location's dashboard cache got
    overwritten with empty data from a database nothing real uses.

    Fixed here, once, transparently, rather than touching every
    caller: every key gets the current location's own identifier
    folded in automatically, using the same per-request context this
    app already tracks for exactly this kind of cross-cutting need
    (see instance_registry.py's _current_instance_db_filename). Falls
    back to no prefix at all — byte-identical original behavior —
    whenever that context isn't available, which is always true for
    chirp-server's own single-tenant deployment, so that one is
    completely unaffected by this change.
    """

    def __init__(self, ttl_seconds: float = 30.0, maxsize: int = 512):
        self._ttl = ttl_seconds
        self._maxsize = maxsize
        self._data: dict = {}       # key → (value, expires_at)
        self._lock = threading.Lock()

    def _scoped_key(self, key: Any) -> Any:
        try:
            from .instance_registry import _current_instance_db_filename
            scope = _current_instance_db_filename.get()
        except Exception:
            scope = None
        return key if scope is None else (scope, key)

    def get(self, key: Any, default=_NOT_SET):
        key = self._scoped_key(key)
        entry = self._data.get(key)
        if entry is None:
            return None if default is _NOT_SET else default
        value, expires_at = entry
        if time.monotonic() > expires_at:
            with self._lock:
                self._data.pop(key, None)
            return None if default is _NOT_SET else default
        return value

    def set(self, key: Any, value: Any) -> None:
        key = self._scoped_key(key)
        expires_at = time.monotonic() + self._ttl
        with self._lock:
            # Evict oldest entry if at capacity
            if len(self._data) >= self._maxsize and key not in self._data:
                oldest = min(self._data, key=lambda k: self._data[k][1])
                del self._data[oldest]
            self._data[key] = (value, expires_at)

    def delete(self, key: Any) -> None:
        key = self._scoped_key(key)
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __contains__(self, key: Any) -> bool:
        return self.get(key, _NOT_SET) is not _NOT_SET


# ── Singleton caches ──────────────────────────────────────────────────────────

# AppSettings row — 30s TTL; invalidated on PUT /settings
settings_cache: TTLCache = TTLCache(ttl_seconds=30.0, maxsize=4)

# JWT → user object — 5 min TTL; invalidated on logout / user disable
user_token_cache: TTLCache = TTLCache(ttl_seconds=300.0, maxsize=256)


# Directory size scan (os.walk + per-file getsize) — 60s TTL.
# Walking the full recordings directory on every settings-page load gets
# slower as recordings accumulate over weeks/months of real use, especially
# over network-attached/spinning-disk storage (e.g. an Unraid array without
# an SSD cache) — this was a genuine "settings page takes forever to load"
# bug, not just a theoretical concern. Storage usage doesn't change quickly
# enough in practice to need a fresh walk on every single page load.
dir_size_cache: TTLCache = TTLCache(ttl_seconds=60.0, maxsize=8)


# Life List and Statistics aggregates — 45s TTL each.
# Both run an unbounded GROUP BY over the full detections/recordings join
# (by design — a life list has to see every historical detection), which
# SQLite executes as two temp B-tree sorts with no useful index to lean on.
# Confirmed by timing against a realistic 50,000-recording/80-species
# dataset: ~1.4-1.6s cold. That gets worse, not better, as more recordings
# accumulate over time. A 45s cache makes repeated visits instant without
# the correctness risk of trying to incrementally maintain these aggregates
# (which would need to stay in sync with two filter settings that can change
# independently — show_deleted_detections and min_confidence_display).
life_list_cache: TTLCache = TTLCache(ttl_seconds=45.0, maxsize=4)
statistics_cache: TTLCache = TTLCache(ttl_seconds=45.0, maxsize=8)
# Statistics page, Yard Pulse and species streaks — 2 min TTL, and NOT cleared
# on every new detection: an active station uploads every minute or so, which
# kept statistics_cache empty and made these (the slowest aggregates, 0.3-2 s
# each) run cold on almost every visit. A couple of minutes behind is fine for
# monthly charts and multi-day streaks. Cleared on settings changes.
slow_stats_cache: TTLCache = TTLCache(ttl_seconds=120.0, maxsize=16)
# Species heard only through Haikubox (see services/species_filters.py).
species_filter_cache: TTLCache = TTLCache(ttl_seconds=300.0, maxsize=64)

# Regional Library (Field Guide) — 60s TTL, canonical no-filter request only.
# Same shape of problem as life_list/statistics above: computes
# locally_detected fresh from the full Detection table on every request,
# plus a batched BirdProfile photo lookup across up to 2000 species rows.
# eBird regional data itself only changes on a periodic sync, and
# locally_detected going 60s stale is a non-issue for a field guide page —
# nobody needs sub-minute freshness on "have I detected this species
# before". Only the canonical fetch (no search, detected_only=False, the
# one the Field Guide page actually loads on mount) is cached; a search
# query is an effectively unbounded key space not worth caching.
regional_library_cache: TTLCache = TTLCache(ttl_seconds=60.0, maxsize=2)


def invalidate_settings():
    """Call after any write to AppSettings."""
    settings_cache.clear()
    # show_deleted_detections / min_confidence_display affect both of these
    # aggregates directly — don't let a settings change wait out the TTL.
    life_list_cache.clear()
    statistics_cache.clear()
    regional_library_cache.clear()
    slow_stats_cache.clear()


def invalidate_detection_caches():
    """
    Call after any new detection is saved (device upload, manual upload,
    live-detect save, reanalyze producing a new detection) — statistics_cache
    backs the Dashboard's "Seen Today" grid, including each species' is_new
    flag (first-ever-detection check). Without this, a species detected for
    the first time today could still show as not-new for up to the cache's
    45s TTL if the Dashboard was loaded (and cached) moments before that
    detection landed. Also clears life_list_cache, since a genuinely new
    species changes the life list itself, not just today's summary.
    """
    statistics_cache.clear()
    life_list_cache.clear()
    species_filter_cache.clear()


def invalidate_user(username: str):
    """Call when a user is disabled or password changed."""
    # We don't store token→username mapping, so just clear the whole cache
    user_token_cache.clear()
