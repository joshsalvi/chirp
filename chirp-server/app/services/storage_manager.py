"""
Chirp Server — Storage Manager

Handles two concerns:

1. COMPRESSION
   Transcodes incoming WAV recordings to FLAC on arrival (lossless, ~50% smaller)
   or OPUS/MP3 for lossy savings (~90% smaller).
   Spectrogram generation continues to work because librosa reads FLAC/OGG.
   WAV originals are removed after successful transcode.

   Quality presets:
     "lossless" → FLAC   (via ffmpeg, ~50% WAV size, bit-exact)
     "medium"   → OPUS   (via ffmpeg, 64 kbps, ~10% WAV size, excellent quality)
     "low"      → OPUS   (via ffmpeg, 24 kbps, ~4% WAV size, acceptable quality)

2. CLEANUP / PRUNING
   Runs periodically (startup + every hour) to enforce storage limits.
   Strategy:
     a. Compute total size of recordings directory
     b. While over limit, delete oldest recordings first (by trigger_timestamp)
     c. Recordings with a user-supplied label or notes are NEVER pruned
        (unless storage_cleanup_keep_flagged is False)
     d. Removes: DB row, WAV/FLAC file, spectrogram PNG, clip WAVs

   Both limits are checked:
     - storage_max_dir_gb   — hard directory size cap (0 = disabled)
     - auto_delete_recordings_days — age-based deletion (0 = disabled)

All operations are logged at INFO level. The service never raises — it logs
errors and continues, since a cleanup failure should not crash the server.
"""

import logging
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("chirp.storage_manager")


# ── Directory reporting / orphan detection ─────────────────────────────────────
# Shared by api/recordings.py's /storage/status endpoint and api/diagnostics.py's
# report generator — single source of truth for "how big is this directory and
# what's in it" instead of two separate implementations drifting apart.

def fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def dir_stats(path: str) -> dict:
    """Recursively size + count every file under `path`, broken down by extension."""
    if not path or not os.path.exists(path):
        return {"exists": False, "path": path}
    total_bytes = 0
    by_ext: dict = {}
    count = 0
    try:
        for entry in Path(path).rglob("*"):
            if not entry.is_file():
                continue
            try:
                size = entry.stat().st_size
            except OSError:
                continue
            total_bytes += size
            count += 1
            ext = entry.suffix.lower() or "(no ext)"
            if ext not in by_ext:
                by_ext[ext] = {"count": 0, "bytes": 0}
            by_ext[ext]["count"] += 1
            by_ext[ext]["bytes"] += size
    except Exception as e:
        return {"exists": True, "path": path, "error": str(e)}

    by_ext_sorted = dict(sorted(by_ext.items(), key=lambda x: x[1]["bytes"], reverse=True))
    for ext_data in by_ext_sorted.values():
        ext_data["size_human"] = fmt_bytes(ext_data["bytes"])

    return {
        "exists":     True,
        "path":       path,
        "size_bytes": total_bytes,
        "size_human": fmt_bytes(total_bytes),
        "file_count": count,
        "by_ext":     by_ext_sorted,
    }


def _walk_files(dir_path: str):
    """(path, DirEntry) for every file under dir_path. os.scandir reuses the
    directory listing's file type, where Path.rglob + is_file + resolve made
    two or three extra system calls per file (minutes on a folder of
    100k+ clips on an Unraid share)."""
    stack = [dir_path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file():
                            yield entry.path, entry
                    except OSError:
                        continue
        except OSError:
            continue


def _is_referenced(path: str, referenced_paths: set) -> bool:
    ap = os.path.abspath(path)
    return ap in referenced_paths or os.path.realpath(ap) in referenced_paths


def find_orphaned_files(dir_path: str, referenced_paths: set, sample_limit: int = 25) -> dict:
    """
    Walk `dir_path` and split every file into "referenced" (its absolute path
    appears in `referenced_paths`, e.g. every Recording.wav_path/Detection.
    clip_path currently in the DB — soft-deleted rows included, since their
    files are still real files taking up real space until something actually
    unlinks them) vs "orphaned" (no DB row references this exact path at all —
    a leftover from a failed cleanup, an interrupted compression, a pre-
    migration artifact, etc.). Returns counts/sizes for both groups plus a
    small sample of orphaned filenames so an admin can spot-check before
    deleting anything — deliberately read-only, never deletes.
    """
    if not dir_path or not os.path.exists(dir_path):
        return {"exists": False, "path": dir_path}

    referenced_count = 0
    referenced_bytes = 0
    orphaned_count = 0
    orphaned_bytes = 0
    orphaned_sample = []

    try:
        for path, entry in _walk_files(dir_path):
            try:
                size = entry.stat().st_size
            except OSError:
                continue
            if _is_referenced(path, referenced_paths):
                referenced_count += 1
                referenced_bytes += size
            else:
                orphaned_count += 1
                orphaned_bytes += size
                if len(orphaned_sample) < sample_limit:
                    orphaned_sample.append({
                        "name": entry.name,
                        "size_bytes": size,
                        "size_human": fmt_bytes(size),
                        "modified": entry.stat().st_mtime,
                    })
    except Exception as e:
        return {"exists": True, "path": dir_path, "error": str(e)}

    return {
        "exists": True,
        "path": dir_path,
        "referenced_count": referenced_count,
        "referenced_bytes": referenced_bytes,
        "referenced_human": fmt_bytes(referenced_bytes),
        "orphaned_count": orphaned_count,
        "orphaned_bytes": orphaned_bytes,
        "orphaned_human": fmt_bytes(orphaned_bytes),
        "orphaned_sample": orphaned_sample,
    }


def delete_orphaned_files(dir_path: str, referenced_paths: set) -> dict:
    """
    Actually delete files under `dir_path` whose absolute path is NOT in
    `referenced_paths`. Same matching logic as find_orphaned_files (call
    that first for a dry-run preview) — this is the destructive twin,
    only ever invoked after the admin has seen the preview and confirmed.
    """
    if not dir_path or not os.path.exists(dir_path):
        return {"exists": False, "path": dir_path, "deleted_count": 0, "deleted_bytes": 0, "errors": 0}

    deleted_count = 0
    deleted_bytes = 0
    errors = 0
    try:
        for path, entry in _walk_files(dir_path):
            try:
                if _is_referenced(path, referenced_paths):
                    continue
                size = entry.stat().st_size
                os.unlink(path)
                deleted_count += 1
                deleted_bytes += size
            except OSError as e:
                logger.warning("delete_orphaned_files: could not delete %s: %s", entry, e)
                errors += 1
    except Exception as e:
        logger.error("delete_orphaned_files error under %s: %s", dir_path, e)
        errors += 1

    return {
        "exists": True, "path": dir_path,
        "deleted_count": deleted_count, "deleted_bytes": deleted_bytes,
        "deleted_human": fmt_bytes(deleted_bytes), "errors": errors,
    }

# ── Derived-audio cache (enhanced_dir) ─────────────────────────────────────────
# Every file in enhanced_dir is named "<recording-or-detection uuid>_<variant>",
# e.g. "{rec}_v3_enhanced.wav", "{det}_rumbleremoved_v3_enhanced.wav",
# "{rec}_v4_aienhanced.wav", "{rec}_dewobbled.wav".

_UUID_PREFIX_RE = re.compile(
    r"^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})_", re.I)
_VERSION_TOKEN_RE = re.compile(r"_(v\d+)_")


def sweep_derived_files(owner_ids, enhanced_dir: str) -> int:
    """Remove every enhanced_dir file whose name starts with "<id>_" for any
    of `owner_ids` (a recording id plus its detection ids). Returns the
    number of files removed."""
    if not enhanced_dir or not os.path.isdir(enhanced_dir):
        return 0
    prefixes = tuple(f"{i}_" for i in owner_ids if i)
    if not prefixes:
        return 0
    removed = 0
    try:
        with os.scandir(enhanced_dir) as it:
            for entry in it:
                if entry.is_file() and entry.name.startswith(prefixes):
                    try:
                        os.unlink(entry.path)
                        removed += 1
                    except OSError as e:
                        logger.warning("sweep_derived_files: could not delete %s: %s", entry.path, e)
    except OSError as e:
        logger.warning("sweep_derived_files: scan of %s failed: %s", enhanced_dir, e)
    return removed


def sweep_recording_derived(rec, enhanced_dir: str) -> int:
    """sweep_derived_files for a Recording row and all of its detections."""
    ids = [rec.id] + [d.id for d in (getattr(rec, "detections", None) or [])]
    return sweep_derived_files(ids, enhanced_dir)


def _stale_version(name: str, dsp_version: str, ai_version: str) -> bool:
    m = _VERSION_TOKEN_RE.search(name)
    if not m:
        return False
    current = ai_version if name.endswith("_aienhanced.wav") else dsp_version
    return m.group(1) != current


def scan_enhanced_cache(enhanced_dir: str, live_ids: set, dsp_version: str,
                        ai_version: str, delete: bool = False, sample_limit: int = 25) -> dict:
    """Split enhanced_dir into kept vs removable files. Removable = owner uuid
    no longer belongs to a live (not soft-deleted, not archived) recording or
    one of its detections, or the file is from an older DSP / AI Enhance
    version. Files without a uuid prefix are left alone. With delete=True
    the removable files are unlinked."""
    if not enhanced_dir or not os.path.exists(enhanced_dir):
        return {"exists": False, "path": enhanced_dir}
    kept = kept_bytes = 0
    orphaned = orphaned_bytes = stale = stale_bytes = 0
    deleted = deleted_bytes = errors = 0
    sample = []
    with os.scandir(enhanced_dir) as it:
        for entry in it:
            if not entry.is_file():
                continue
            try:
                st = entry.stat()
            except OSError:
                continue
            m = _UUID_PREFIX_RE.match(entry.name)
            reason = None
            if m and m.group(1) not in live_ids:
                reason = "orphaned"
            elif m and _stale_version(entry.name, dsp_version, ai_version):
                reason = "stale version"
            if reason is None:
                kept += 1
                kept_bytes += st.st_size
                continue
            if reason == "orphaned":
                orphaned += 1
                orphaned_bytes += st.st_size
            else:
                stale += 1
                stale_bytes += st.st_size
            if len(sample) < sample_limit:
                sample.append({"name": entry.name, "reason": reason,
                               "size_bytes": st.st_size, "size_human": fmt_bytes(st.st_size),
                               "modified": st.st_mtime})
            if delete:
                try:
                    os.unlink(entry.path)
                    deleted += 1
                    deleted_bytes += st.st_size
                except OSError as e:
                    logger.warning("scan_enhanced_cache: could not delete %s: %s", entry.path, e)
                    errors += 1
    total_bytes = orphaned_bytes + stale_bytes
    out = {
        "exists": True, "path": enhanced_dir,
        "referenced_count": kept, "referenced_bytes": kept_bytes,
        "referenced_human": fmt_bytes(kept_bytes),
        "orphaned_count": orphaned + stale, "orphaned_bytes": total_bytes,
        "orphaned_human": fmt_bytes(total_bytes),
        "no_owner_count": orphaned, "stale_version_count": stale,
        "orphaned_sample": sample,
    }
    if delete:
        out.update({"deleted_count": deleted, "deleted_bytes": deleted_bytes,
                    "deleted_human": fmt_bytes(deleted_bytes), "errors": errors})
    return out


# ffmpeg quality presets
COMPRESS_PRESETS = {
    "lossless": {
        "ext": "flac",
        "args": ["-c:a", "flac", "-compression_level", "5"],
        "description": "FLAC lossless (~50% of WAV size)",
    },
    "medium": {
        "ext": "opus",
        "args": ["-c:a", "libopus", "-b:a", "64k", "-vbr", "on"],
        "description": "Opus 64 kbps (~10% of WAV size)",
    },
    "low": {
        "ext": "opus",
        "args": ["-c:a", "libopus", "-b:a", "24k", "-vbr", "on"],
        "description": "Opus 24 kbps (~4% of WAV size)",
    },
}

_DEFAULT_PRESET = "lossless"


def _ffmpeg_available() -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def compress_recording(wav_path: str, quality: str = "lossless") -> Optional[str]:
    """
    Transcode a WAV file to a compressed format in-place.

    Returns the path of the compressed file on success, or None on failure.
    On success the original WAV is removed.
    On failure the original WAV is preserved.

    The compressed file lands alongside the original:
      /app/data/recordings/abc.wav → /app/data/recordings/abc.flac  (lossless)
      /app/data/recordings/abc.wav → /app/data/recordings/abc.opus  (medium/low)
    """
    if not _ffmpeg_available():
        logger.warning("ffmpeg not found — compression skipped for %s", wav_path)
        return None

    preset = COMPRESS_PRESETS.get(quality, COMPRESS_PRESETS[_DEFAULT_PRESET])
    src = Path(wav_path)
    if not src.exists():
        logger.warning("compress_recording: source not found: %s", wav_path)
        return None

    # Already compressed?
    if src.suffix.lower() in (".flac", ".opus", ".ogg", ".mp3"):
        logger.debug("compress_recording: already compressed: %s", wav_path)
        return wav_path

    dst = src.with_suffix("." + preset["ext"])

    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(src),
            *preset["args"],
            str(dst),
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        if result.returncode != 0:
            err = result.stderr.decode(errors="replace")[-300:]
            logger.error(
                "ffmpeg transcode failed for %s: %s", wav_path, err
            )
            # Clean up partial output
            if dst.exists():
                dst.unlink()
            return None

        orig_size = src.stat().st_size
        new_size  = dst.stat().st_size
        ratio = new_size / orig_size * 100 if orig_size else 0

        # Sanity check: compressed file must be at least 1 KB and non-empty
        if new_size < 1024:
            logger.error(
                "Compressed output suspiciously small (%d bytes), keeping original: %s",
                new_size, wav_path,
            )
            if dst.exists():
                dst.unlink()
            return None

        src.unlink()
        logger.info(
            "Compressed %s → %s (%.0f%% of original, preset=%s)",
            src.name, dst.name, ratio, quality,
        )
        return str(dst)

    except subprocess.TimeoutExpired:
        logger.error("ffmpeg timed out compressing %s", wav_path)
        if dst.exists():
            dst.unlink()
        return None
    except Exception as e:
        logger.error("compress_recording error for %s: %s", wav_path, e)
        if dst.exists():
            dst.unlink()
        return None


def get_directory_size_gb(directory: str, force_refresh: bool = False) -> float:
    """
    Return total size of a directory tree in GB.

    Cached for 60s (see cache.py:dir_size_cache) — walking the full tree on
    every call gets slower as recordings accumulate over weeks/months of
    real use, especially over network-attached/spinning-disk storage. Pass
    force_refresh=True for callers that need a guaranteed-fresh value (e.g.
    right after a bulk delete), bypassing the cache for that one call.
    """
    from ..cache import dir_size_cache

    if not force_refresh:
        cached = dir_size_cache.get(directory)
        if cached is not None:
            return cached

    total = 0
    try:
        for dirpath, _, filenames in os.walk(directory):
            for fname in filenames:
                fp = os.path.join(dirpath, fname)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    except Exception as e:
        logger.warning("get_directory_size_gb error: %s", e)

    result = total / (1024 ** 3)
    dir_size_cache.set(directory, result)
    return result


def _delete_recording_files(rec, recordings_dir: str, spectrograms_dir: str, clips_dir: str):
    """Delete all files associated with a recording object (audio and its
    compressed twin, JSON, every spectrogram variant, clips, Enhanced
    caches). Prefer file_cleanup.delete_recordings, which also removes the
    rows in committed batches."""
    from .file_cleanup import collect_files, remove_files
    files_removed, _ = remove_files(collect_files([rec]))
    clip_dir = Path(clips_dir) / rec.id
    if clip_dir.is_dir():
        try:
            shutil.rmtree(str(clip_dir))
            files_removed += 1
        except OSError as e:
            logger.warning("Could not remove clips dir %s: %s", clip_dir, e)
    return files_removed


class StorageManager:
    """
    Background storage manager. Call start() once at server startup.
    Runs cleanup on startup and then every CLEANUP_INTERVAL_SECONDS.
    """

    CLEANUP_INTERVAL_SECONDS = 3600  # run every hour

    def __init__(self, db_factory, recordings_dir: str, spectrograms_dir: str, clips_dir: str):
        """
        :param db_factory: Callable returning a SQLAlchemy Session (use SessionLocal)
        :param recordings_dir: Absolute path to recordings directory
        :param spectrograms_dir: Absolute path to spectrograms directory
        :param clips_dir: Absolute path to clips directory
        """
        self._db_factory = db_factory
        self._recordings_dir = recordings_dir
        self._spectrograms_dir = spectrograms_dir
        self._clips_dir = clips_dir

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start the background cleanup loop."""
        self._thread = threading.Thread(
            target=self._loop, name="StorageManager", daemon=True
        )
        self._thread.start()
        logger.info("StorageManager started (recordings: %s)", self._recordings_dir)

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)

    def run_cleanup_now(self) -> dict:
        """
        Run a full cleanup pass synchronously and return a summary dict.
        Safe to call from an API endpoint.
        """
        return self._run_cleanup()

    # ── Background loop ────────────────────────────────────────────────────────

    def _loop(self):
        # Small delay on startup so the DB is fully initialized
        self._stop_event.wait(15)
        while not self._stop_event.is_set():
            try:
                self._run_cleanup()
            except Exception as e:
                logger.error("StorageManager cleanup error: %s", e, exc_info=True)
            self._stop_event.wait(self.CLEANUP_INTERVAL_SECONDS)

    # ── Core cleanup logic ─────────────────────────────────────────────────────

    def _get_settings(self, db):
        from ..models import AppSettings
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        return s

    def _run_cleanup(self) -> dict:
        summary = {
            "archived": 0,
            "age_pruned": 0,
            "size_pruned": 0,
            "errors": 0,
            "dir_size_gb_before": 0.0,
            "dir_size_gb_after": 0.0,
        }
        try:
            with self._db_factory() as db:
                s = self._get_settings(db)
                if not s:
                    return summary

                max_archive_age_days = getattr(s, "auto_archive_recordings_days", 0) or 0
                max_age_days    = getattr(s, "auto_delete_recordings_days", 0) or 0
                max_dir_gb      = getattr(s, "storage_max_dir_gb", 0.0) or 0.0
                keep_flagged    = getattr(s, "storage_cleanup_keep_flagged", True)

                summary["dir_size_gb_before"] = get_directory_size_gb(self._recordings_dir, force_refresh=True)

                # ── Pass 0: Age-based archiving ─────────────────────────────
                # Runs before the two delete passes below — archiving is the
                # lighter-touch, reversible-in-status (though not in audio)
                # action, and naturally reduces how often size-based
                # deletion needs to fire at all, since archived recordings'
                # audio is already gone by the time that pass would run.
                if max_archive_age_days > 0:
                    archived = self._archive_by_age(db, max_archive_age_days, keep_flagged)
                    summary["archived"] = archived

                # ── Pass 1: Age-based deletion ──────────────────────────────
                if max_age_days > 0:
                    pruned = self._prune_by_age(db, max_age_days, keep_flagged)
                    summary["age_pruned"] = pruned

                # ── Pass 2: Size-based deletion ─────────────────────────────
                if max_dir_gb > 0:
                    current_gb = get_directory_size_gb(self._recordings_dir, force_refresh=True)
                    if current_gb > max_dir_gb:
                        pruned = self._prune_by_size(db, max_dir_gb, keep_flagged, current_gb)
                        summary["size_pruned"] = pruned

                summary["dir_size_gb_after"] = get_directory_size_gb(self._recordings_dir, force_refresh=True)

                if summary["archived"] or summary["age_pruned"] or summary["size_pruned"]:
                    logger.info(
                        "Storage cleanup: archived=%d age_pruned=%d size_pruned=%d "
                        "%.2f GB → %.2f GB (limit=%.1f GB)",
                        summary["archived"], summary["age_pruned"], summary["size_pruned"],
                        summary["dir_size_gb_before"], summary["dir_size_gb_after"],
                        max_dir_gb,
                    )

                # Investigated directly, in response to a "is database size
                # the bottleneck?" question: this hourly cycle already
                # deletes/archives rows continuously, but nothing anywhere
                # in the app ever ran ANALYZE — SQLite's query planner picks
                # join order and index usage from statistics that only
                # ANALYZE refreshes, and those can go stale as a table's
                # data (and how skewed it is) changes over months of
                # continuous use. Cheap and safe to run every cycle — unlike
                # VACUUM, ANALYZE doesn't rewrite the database file or need
                # exclusive access, just re-samples each table and updates
                # the planner's own stats. VACUUM (reclaiming space from
                # deleted rows) is deliberately NOT done automatically here
                # — it locks the whole database for the full rewrite, which
                # for a database that's grown large could be a
                # multi-minute stall on an hourly cycle; that one's better
                # run deliberately during low-traffic hours, not silently
                # on a schedule.
                try:
                    from sqlalchemy import text as _text
                    db.execute(_text("ANALYZE"))
                except Exception as e:
                    logger.warning("ANALYZE failed during storage cleanup: %s", e)
        except Exception as e:
            logger.error("_run_cleanup error: %s", e, exc_info=True)
            summary["errors"] += 1
        return summary

    def _archive_by_age(self, db, max_archive_age_days: int, keep_flagged: bool) -> int:
        """
        Auto-archive: delete only the audio file (and detection clips) for
        recordings older than the threshold, leaving everything else —
        spectrogram, detections, statistics contribution — fully intact.
        See Recording.archived_at's model docstring for why this is a
        distinct, deliberately gentler action from the age/size delete
        passes below, which remove the entire DB row and every file.
        Already-archived recordings (archived_at already set) and, when
        keep_flagged is True, anything with a user-supplied label/notes
        are skipped — same "don't touch what the user explicitly cared
        about" rule the delete passes already follow.
        """
        from datetime import datetime, timedelta
        from ..models import Recording
        cutoff = datetime.utcnow() - timedelta(days=max_archive_age_days)
        q = db.query(Recording).filter(
            Recording.trigger_timestamp < cutoff,
            Recording.archived_at.is_(None),
            Recording.deleted_at.is_(None),
        )
        if keep_flagged:
            q = q.filter(Recording.label.is_(None), Recording.notes.is_(None))
        recs = q.order_by(Recording.trigger_timestamp.asc()).all()
        count = 0
        # Committed batches with the files removed after each commit, so the
        # database isn't locked while the files go (see file_cleanup).
        for i in range(0, len(recs), 20):
            batch = recs[i:i + 20]
            paths = []
            try:
                with db.no_autoflush:
                    for rec in batch:
                        if rec.wav_path:
                            paths.append(rec.wav_path)
                        for det in rec.detections:
                            if det.clip_path:
                                paths.append(det.clip_path)
                            det.clip_path = None
                        rec.wav_path = ""
                        rec.archived_at = datetime.utcnow()
                db.commit()
            except Exception as e:
                db.rollback()
                logger.warning("Auto-archive batch failed: %s", e)
                break
            count += len(batch)
            for p in paths:
                try:
                    os.unlink(p)
                except FileNotFoundError:
                    pass
                except OSError as e:
                    logger.debug("Auto-archive could not delete %s: %s", p, e)
        if count:
            logger.info("Auto-archived %d recording(s) older than %d day(s)", count, max_archive_age_days)
        return count

    def _prune_by_age(self, db, max_age_days: int, keep_flagged: bool) -> int:
        from datetime import datetime, timedelta
        from ..models import Recording
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        q = db.query(Recording).filter(
            Recording.trigger_timestamp < cutoff,
            # Haikubox-sourced rows have no audio file to free (wav_path
            # is "" by design — see haikubox_sync.py's _import_detection)
            # so deleting them here serves no disk-space purpose while
            # destroying real detection history the user explicitly
            # synced in. Confirmed as a real gap: a Haikubox detection's
            # trigger_timestamp can easily predate this cutoff on the
            # very first sync after enabling, since the cloud API can
            # return detections from well in the past.
            Recording.haikubox_detection_id.is_(None),
        )
        if keep_flagged:
            q = q.filter(Recording.label.is_(None), Recording.notes.is_(None))
        recs = q.order_by(Recording.trigger_timestamp.asc()).all()
        from .file_cleanup import delete_recordings
        return delete_recordings(db, recs)["purged"] if recs else 0

    def _prune_by_size(self, db, max_dir_gb: float, keep_flagged: bool, current_gb: float) -> int:
        from ..models import Recording
        q = db.query(Recording).filter(
            # Same exclusion as _prune_by_age above — a Haikubox row has
            # no file on disk to free, so even though it would
            # self-limit (file_size_gb computes to 0 for it, contributing
            # nothing toward the target), it would still be deleted for
            # zero actual benefit once iteration reaches it. Excluding it
            # outright is correct, not just harmless.
            Recording.haikubox_detection_id.is_(None),
        )
        if keep_flagged:
            q = q.filter(Recording.label.is_(None), Recording.notes.is_(None))
        recs = q.order_by(Recording.trigger_timestamp.asc()).all()

        # Pick the oldest recordings until the folder would be at 90% of the
        # limit (sizes read first, nothing written), then delete them in
        # committed batches.
        targets = []
        gb = current_gb
        for rec in recs:
            if gb <= max_dir_gb * 0.90:  # prune to 90% of limit for headroom
                break
            file_size_gb = 0.0
            if rec.wav_path:
                for ext in ("", ".flac", ".opus", ".ogg"):
                    candidate = Path(rec.wav_path).with_suffix(ext) if ext else Path(rec.wav_path)
                    if candidate.exists():
                        file_size_gb = candidate.stat().st_size / (1024 ** 3)
                        break
            targets.append(rec)
            gb -= file_size_gb
        from .file_cleanup import delete_recordings
        return delete_recordings(db, targets)["purged"] if targets else 0




def compress_on_upload(rec_id: str, wav_path: str, quality: str, db_factory) -> Optional[str]:
    """
    Called as a background task immediately after a recording is saved.
    Compresses the WAV, then updates the DB row's wav_path to the new file.
    Returns the new path, or None if compression was skipped/failed.
    """
    new_path = compress_recording(wav_path, quality)
    if new_path and new_path != wav_path:
        # Update DB
        try:
            with db_factory() as db:
                from ..models import Recording
                rec = db.query(Recording).filter(Recording.id == rec_id).first()
                if rec:
                    rec.wav_path = new_path
                    db.commit()
        except Exception as e:
            logger.warning("compress_on_upload: DB update failed for %s: %s", rec_id, e)
    return new_path
