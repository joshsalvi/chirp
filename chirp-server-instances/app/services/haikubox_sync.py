"""
Haikubox Sync Service
=====================
Polls the Haikubox public REST API every 15 minutes and imports detections
into Chirp as lightweight Recording + Detection rows, attributed to a virtual
Device so they appear alongside real Pi recordings in every view.

API facts (from https://api.haikubox.com/docs):
  - No authentication required — serial number in URL is the only credential.
  - /detections?hours=N  returns up to 5 most recent detections per species,
    N ≤ 24. No historical replay beyond 24 hours.
  - No audio files are available — Haikubox does not expose audio.
  - CC BY-NC-SA 4.0 license (non-commercial self-hosted use is fine).

Because there is no audio, imported recordings have:
  - wav_path = "" (empty string — no file on disk)
  - processing_status = "done" (nothing to process)
  - duration_seconds = 3.0  (synthetic; BirdNET analysis window length)
  - No spectrogram (spectrogram_path = None)

Detection confidence is not returned by the API, so we use 0.90 as a
placeholder (Haikubox only reports verified detections).

Deduplication key: "<serial>:<common_name>:<unix_timestamp>" stored in
Recording.haikubox_detection_id — prevents re-importing the same detection
if it appears in two consecutive polling windows.
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger("chirp.haikubox_sync")

HAIKUBOX_API_BASE = "https://api.haikubox.com"
POLL_INTERVAL_SECONDS = 15 * 60   # 15 minutes
DETECTION_WINDOW_HOURS = 24        # max the API allows
DEFAULT_CONFIDENCE = 0.90          # placeholder — API doesn't return confidence


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class HaikuboxSyncService:
    """Background thread that polls the Haikubox API and imports detections."""

    def __init__(self):
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # Tracks the real DB row count as of the end of the previous sync,
        # used to detect a drop that happened BETWEEN two sync cycles —
        # see _run_sync's comment for why a within-the-same-call
        # before/after comparison can't catch this (confirmed directly:
        # by the time a sync measures its own "before" count, this
        # service's own dedup/re-import logic has often already started
        # correcting for whatever was deleted before that call began,
        # so the within-call numbers never show the actual drop).
        self._last_known_count: Optional[int] = None
        # Per-instance version of the same value — keyed by db_filename via
        # the same context the multi-tenant fork already tracks (see
        # instance_registry.py). Only relevant when this service is
        # actually looping over multiple real instances (see
        # _run_sync_all_instances() below); _last_known_count above stays
        # as the single-instance fallback for chirp-server's own build,
        # which never defines this context at all. Without per-instance
        # keying here, syncing instance B right after instance A would
        # compare B's real count against A's previous count — not a data
        # bug (nothing gets written wrong), just a spurious one-off
        # "count dropped" log line on the first sync after this existed.
        self._last_known_count_by_instance: dict = {}

    # ── Public control ─────────────────────────────────────────────────────────

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="haikubox-sync"
        )
        self._thread.start()
        logger.info("Haikubox sync service started (poll every %dm)", POLL_INTERVAL_SECONDS // 60)

    def stop(self):
        self._stop.set()

    # ── Internal loop ──────────────────────────────────────────────────────────

    def _loop(self):
        # Run immediately on start, then every POLL_INTERVAL_SECONDS
        while not self._stop.is_set():
            try:
                self._run_sync_all_instances()
            except Exception as e:
                logger.warning("Haikubox sync error: %s", e)
            self._stop.wait(POLL_INTERVAL_SECONDS)

    def _run_sync_all_instances(self):
        """
        Same real gap and fix as bird_buddy_sync.py's own equivalent
        method — see that one's docstring for the full story. Without
        this, Haikubox sync never actually ran against any real
        instance's own settings/data, only the single unused legacy
        database.
        """
        from ..instance_registry import iter_instance_sessions
        for instance, db in iter_instance_sessions():
            db.close()
            try:
                self._run_sync()
            except Exception as e:
                logger.warning("Haikubox sync error for instance %s (%s): %s", instance.id, instance.name, e)

    def _current_scope_key(self):
        try:
            from ..instance_registry import _current_instance_db_filename
            return _current_instance_db_filename.get()
        except Exception:
            return None

    def _get_last_known_count(self) -> Optional[int]:
        scope = self._current_scope_key()
        if scope is None:
            return self._last_known_count
        return self._last_known_count_by_instance.get(scope)

    def _set_last_known_count(self, value: int):
        scope = self._current_scope_key()
        if scope is None:
            self._last_known_count = value
        else:
            self._last_known_count_by_instance[scope] = value

    def _run_sync(self):
        from ..database import SessionLocal
        from ..models import AppSettings

        with SessionLocal() as db:
            s = db.query(AppSettings).filter(AppSettings.id == 1).first()
            serial = s.haikubox_serial if s else None
            enabled = bool(getattr(s, "haikubox_enabled", False)) if s else False

        if not enabled:
            # Master toggle is off — checked fresh every poll cycle (this
            # function runs every POLL_INTERVAL_SECONDS) rather than only
            # at service startup, so disabling it in Settings takes effect
            # within one cycle, no server restart needed. Does not touch
            # last_seen/status — an already-paired virtual device just
            # stops updating, which is the correct "paused" behavior, not
            # an active "mark offline" signal (that's reserved for actual
            # sync failures — see the except blocks below).
            return

        if not serial:
            return  # Nothing configured — do nothing

        serial = serial.strip()
        logger.debug("Haikubox sync: polling serial %s", serial)

        try:
            device_info = self._fetch_device_info(serial)
        except Exception as e:
            logger.warning("Haikubox: could not reach API for serial %s: %s", serial, e)
            # Genuinely mark offline on a real API failure — previously
            # this just returned, leaving last_seen stale with no signal
            # that anything had actually gone wrong. A real failure should
            # be distinguishable from "just hasn't synced in the last 15
            # minutes yet," which is_online()'s platform-aware threshold
            # (see models.py) now correctly tolerates on its own.
            self._update_device_status(serial, online=False)
            return

        hb_name = device_info.get("haikuboxName") or f"Haikubox {serial[:8]}"
        hb_tz   = device_info.get("tz") or "UTC"

        try:
            detections_payload = self._fetch_detections(serial, DETECTION_WINDOW_HOURS)
        except Exception as e:
            logger.warning("Haikubox: detections fetch failed for %s: %s", serial, e)
            self._update_device_status(serial, online=False)
            return

        detections = detections_payload.get("detections") or []
        if not detections:
            logger.debug("Haikubox sync: no detections returned for %s", serial)
            self._update_device_status(serial, online=True)
            return

        # Diagnostic: log the literal shape of the first detection object
        # once per sync, at WARNING (visible without DEBUG enabled). The
        # existing "0 new, X already seen, DB row count 0 -> 0" pattern
        # has exactly two possible explanations: a genuine dedup false
        # positive, or every detection silently failing the
        # common_name/timestamp validation check near the top of
        # _import_detection and being counted as "already seen" even
        # though nothing was actually found in the database — that
        # function returns False for both cases, with no way to tell them
        # apart from the caller's side. This shows the real payload shape
        # directly rather than continuing to guess from API documentation
        # that may not reflect what this specific firmware actually sends.
        logger.warning(
            "Haikubox raw detection sample (sync diagnostic): %r",
            detections[0] if detections else None,
        )

        from ..models import Recording as _RecordingCount
        with SessionLocal() as _count_db:
            count_before = _count_db.query(_RecordingCount).filter(
                _RecordingCount.haikubox_detection_id.isnot(None)
            ).count()

        # Compare against the END of the PREVIOUS sync, not this call's
        # own "before" count — a deletion that happens between two sync
        # cycles is exactly what this is meant to catch, and this call's
        # own dedup/re-import logic will have already started correcting
        # for it by the time count_before above is measured. None on the
        # very first sync after startup (nothing to compare against yet).
        previous_count = self._get_last_known_count()

        imported = 0
        skipped  = 0
        with SessionLocal() as db:
            device = self._ensure_virtual_device(db, serial, hb_name)
            for det_raw in detections:
                try:
                    result = self._import_detection(db, det_raw, device, serial, hb_tz)
                    if result:
                        imported += 1
                    else:
                        skipped += 1
                except Exception as e:
                    logger.debug("Haikubox: could not import detection %s: %s", det_raw, e)
            db.commit()

        with SessionLocal() as _count_db:
            count_after = _count_db.query(_RecordingCount).filter(
                _RecordingCount.haikubox_detection_id.isnot(None)
            ).count()
        self._set_last_known_count(count_after)

        logger.info(
            "Haikubox sync (%s): %d new, %d already seen (total in payload: %d) | "
            "actual DB row count: %d -> %d (previous sync ended at: %s)",
            serial[:8], imported, skipped, len(detections), count_before, count_after,
            previous_count,
        )
        if previous_count is not None and count_before < previous_count:
            # This is the actual symptom under investigation: real
            # Haikubox rows disappearing from the database SOMETIME
            # BETWEEN the end of the last sync and the start of this one
            # — with no deletion logic anywhere in this sync service
            # itself (confirmed by code inspection — this loop only ever
            # calls db.add(), never db.delete()). Logging this explicitly
            # at WARNING level turns "someone happens to run a SQL query
            # at the right moment" into something directly visible in
            # normal logs the next time this happens.
            logger.warning(
                "Haikubox row count DROPPED between sync cycles: %d (end of last sync) "
                "-> %d (start of this sync) — this sync service never deletes rows "
                "itself, so something else removed %d row(s) in the gap between syncs. "
                "Check storage_manager and any manual delete/purge endpoints called "
                "around this timestamp.",
                previous_count, count_before, previous_count - count_before,
            )

    # ── API calls ──────────────────────────────────────────────────────────────

    def _fetch_device_info(self, serial: str) -> dict:
        url = f"{HAIKUBOX_API_BASE}/haikubox/{serial}"
        with httpx.Client(timeout=15) as client:
            r = client.get(url)
            r.raise_for_status()
            return r.json()

    def _fetch_detections(self, serial: str, hours: int) -> dict:
        url = f"{HAIKUBOX_API_BASE}/haikubox/{serial}/detections"
        with httpx.Client(timeout=15) as client:
            r = client.get(url, params={"hours": hours})
            r.raise_for_status()
            return r.json()

    # ── Virtual device management ──────────────────────────────────────────────

    def _ensure_virtual_device(self, db, serial: str, hb_name: str):
        """Return (or create) the virtual Device row for this Haikubox."""
        from ..models import Device, AppSettings

        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        device_id = s.haikubox_device_id if s else None

        device = None
        if device_id:
            device = db.query(Device).filter(Device.id == device_id).first()

        if device is None:
            # No existing virtual device — search by hostname sentinel
            device = db.query(Device).filter(
                Device.hostname == f"haikubox:{serial}"
            ).first()

        if device is None:
            device = Device(
                name=hb_name,
                api_key_id=None,          # virtual device — no API key
                hostname=f"haikubox:{serial}",
                platform="Haikubox",
                birdnet_backend="haikubox",
                status="online",
                last_seen=_utcnow(),
            )
            db.add(device)
            db.flush()  # get the generated id
            logger.info("Haikubox: created virtual device '%s' (id=%s)", hb_name, device.id)
        else:
            device.name = hb_name
            device.last_seen = _utcnow()
            device.status = "online"

        # Persist device_id reference back to settings
        if s and s.haikubox_device_id != device.id:
            s.haikubox_device_id = device.id

        return device

    def _update_device_status(self, serial: str, online: bool):
        from ..database import SessionLocal
        from ..models import Device, AppSettings

        with SessionLocal() as db:
            s = db.query(AppSettings).filter(AppSettings.id == 1).first()
            device_id = s.haikubox_device_id if s else None
            if not device_id:
                return
            device = db.query(Device).filter(Device.id == device_id).first()
            if device:
                device.last_seen = _utcnow()
                device.status = "online" if online else "offline"
                db.commit()

    # ── Detection import ───────────────────────────────────────────────────────

    def _import_detection(self, db, det_raw: dict, device, serial: str, hb_tz: str = "UTC") -> bool:
        """
        Create a Recording + Detection row for one Haikubox detection.
        Returns True if a new row was created, False if already exists (dedup).

        Real det_raw shape, confirmed directly from a live payload capture
        (previous versions of this code assumed verbose field names like
        "commonName"/"timestamp" that the actual API never sends, which
        silently failed validation on every single detection — see the
        history note below):
          {
            "cn": "Black-capped Chickadee",      # common name
            "sn": "Poecile atricapillus",        # scientific name
            "spCode": "bkcchi",                  # eBird species code
            "dt": "2026-06-24T20:22:57Z",         # UTC, explicit Z suffix
            "wav": "https://...flac?...",         # presigned audio URL (FLAC, not WAV)
            "offset": 6.0,                        # seconds into the clip
          }

        History: every prior version of this function checked for
        "commonName"/"common_name" and "timestamp"/"detectedAt" — none of
        which exist in the real payload, confirmed by capturing and
        logging the literal raw detection objects from a live sync. Every
        detection silently (or only at DEBUG level) failed the "missing
        required fields" check and was counted as "already seen" in the
        sync summary, identical to genuine dedup — which is exactly what
        produced "0 new, 161 already seen" on every single sync, forever,
        with zero rows ever actually written to the database despite the
        summary log looking like dedup was working correctly.
        """
        from ..models import Recording, Detection
        from ..services.bird_enricher import BirdEnricher

        common_name = (
            det_raw.get("cn") or det_raw.get("commonName") or det_raw.get("common_name") or ""
        )
        scientific_name = (
            det_raw.get("sn") or det_raw.get("scientificName") or det_raw.get("scientific_name") or ""
        )
        ts_str = (
            det_raw.get("dt") or det_raw.get("timestamp") or det_raw.get("detectedAt") or ""
        )
        confidence = float(det_raw.get("confidence") or DEFAULT_CONFIDENCE)

        if not common_name or not ts_str:
            # This path returns False — the exact same value _run_sync's
            # caller uses to mean "already seen via dedup" — with no row
            # ever written or looked up. Previously silent (no log at
            # all), making this indistinguishable from genuine dedup at
            # the "X already seen" count in the sync summary, which is
            # exactly the ambiguity that made "0 new, X already seen, DB
            # row count staying at 0" look identical whether dedup was
            # working correctly or every detection was failing this
            # check before ever reaching the database. Logged at WARNING
            # (not DEBUG) so it's visible without enabling debug logging.
            logger.warning(
                "Haikubox: detection missing required field(s), skipped (NOT a dedup skip) — "
                "common_name=%r ts_str=%r raw=%r",
                common_name, ts_str, det_raw,
            )
            return False

        # The API returns device-local time without a UTC offset. Convert
        # properly using the device's reported IANA timezone (e.g.
        # "America/New_York") instead of the previous approach of treating
        # it as already-UTC, which drifted by the local UTC offset.
        # The real payload's "dt" field is explicit UTC (every sample
        # captured from a live sync ends in "Z", confirmed directly, not
        # assumed) — fromisoformat handles "Z" natively in Python 3.11+,
        # but to stay compatible with the explicit "+HH:MM"-style offsets
        # some firmware may also send, detect any timezone marker rather
        # than only "Z" specifically. Only fall through to the
        # device-timezone interpretation below when the string is
        # genuinely naive (no offset at all) — applying that
        # interpretation to an already-UTC timestamp was a real,
        # separate bug (silently shifting every dedup key, and therefore
        # every record's displayed time, by the device's UTC offset) that
        # existed before this fix and is now corrected.
        had_explicit_utc = ts_str.endswith("Z") or ts_str.endswith("+00:00")
        had_explicit_offset = not had_explicit_utc and (
            len(ts_str) > 6 and ts_str[-6] in "+-" and ts_str[-3] == ":"
        )
        try:
            ts_parsed = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            logger.warning(
                "Haikubox: unparseable timestamp, skipped (NOT a dedup skip) — ts_str=%r raw=%r",
                ts_str, det_raw,
            )
            return False

        if had_explicit_utc or had_explicit_offset:
            # Already timezone-aware and correct — just normalize to
            # naive-UTC, the convention this codebase uses everywhere
            # else (see Recording.trigger_timestamp and every other
            # DateTime column in models.py).
            ts = ts_parsed.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            # Genuinely naive — no offset info at all. Interpret using
            # the device's reported IANA timezone (e.g. "America/New_York"),
            # the one case where this conversion is actually correct.
            try:
                from zoneinfo import ZoneInfo
                ts = ts_parsed.replace(tzinfo=ZoneInfo(hb_tz)).astimezone(timezone.utc).replace(tzinfo=None)
            except Exception:
                # Unknown/invalid tz name — fall back to treating it as
                # already-UTC rather than failing the import outright.
                ts = ts_parsed

        # Build dedup key
        dedup_key = f"{serial}:{common_name}:{int(ts.timestamp())}"
        existing = db.query(Recording).filter(
            Recording.haikubox_detection_id == dedup_key
        ).first()
        if existing:
            return False  # already imported (genuine dedup — a real row was found)

        # Build BirdNET-style label: "Common Name_Scientific Name"
        label = f"{common_name}_{scientific_name}" if scientific_name else common_name

        # Ensure a Recording row
        rec = Recording(
            filename=f"haikubox_{serial[:8]}_{ts.strftime('%Y%m%d_%H%M%S')}_{common_name.replace(' ', '_')}.haikubox",
            wav_path="",               # no audio file available from Haikubox API
            spectrogram_path=None,
            trigger_timestamp=ts,
            duration_seconds=3.0,      # synthetic; single BirdNET window
            sample_rate=48000,
            channels=1,
            pre_roll_seconds=0.0,
            device_id=device.id,
            device_count=1,
            processing_status="done",  # nothing to process — no audio
            haikubox_detection_id=dedup_key,
        )
        db.add(rec)
        db.flush()

        # Ensure a Detection row
        det = Detection(
            recording_id=rec.id,
            common_name=common_name,
            scientific_name=scientific_name,
            label=label,
            confidence=confidence,
            start_time=0.0,
            end_time=3.0,
            source="haikubox",
        )
        db.add(det)

        # Ensure bird profile (kicks off enrichment if species is new)
        try:
            enricher = BirdEnricher(db)
            enricher.ensure_profile(label)
        except Exception as e:
            logger.debug("Haikubox: enrichment failed for '%s': %s", common_name, e)

        return True


# ── Module-level singleton ─────────────────────────────────────────────────────

_sync_service: Optional[HaikuboxSyncService] = None


def get_sync_service() -> HaikuboxSyncService:
    global _sync_service
    if _sync_service is None:
        _sync_service = HaikuboxSyncService()
    return _sync_service
