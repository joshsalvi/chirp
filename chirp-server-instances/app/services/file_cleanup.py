"""
Removing recordings' files without holding the database write lock.

The spectrograms folder holds every cached variant of every recording
(hundreds of thousands of files on a busy server), so a glob per recording
costs seconds. Done between a delete and its commit, that kept SQLite's
write lock and every upload, heartbeat and delete failed with "database is
locked".

    job = collect_files(recs)          # paths from the rows, no writes
    for r in recs: db.delete(r)
    db.commit()                        # lock released
    remove_files(job)                  # or remove_files_in_background(job)

Spectrogram variants and the Enhanced caches are found by one scan of each
folder for the whole set of recordings.
"""
import logging
import os
import threading
from typing import Iterable

from ..config import settings

logger = logging.getLogger("chirp.file_cleanup")

_SPEC_SEP = "_spectrogram_"


def collect_files(recs: Iterable) -> dict:
    """Files belonging to these recordings, read from the rows (and their
    detections) before they are deleted."""
    paths, rec_ids, owner_ids = set(), set(), set()
    for rec in recs:
        rec_ids.add(rec.id)
        owner_ids.add(rec.id)
        for p in (rec.wav_path, getattr(rec, "json_path", None), rec.spectrogram_path,
                  getattr(rec, "bird_buddy_video_path", None)):
            if p:
                paths.add(p)
        if rec.wav_path:   # the original or compressed copy left beside it
            stem = os.path.splitext(rec.wav_path)[0]
            paths.update(stem + ext for ext in (".wav", ".flac", ".opus", ".ogg", ".mp3"))
        for det in (rec.detections or []):
            owner_ids.add(det.id)
            if det.clip_path:
                paths.add(det.clip_path)
    return {"paths": sorted(paths), "rec_ids": sorted(rec_ids), "owner_ids": sorted(owner_ids)}


def spectrogram_files(rec_ids: Iterable[str]) -> list:
    """Every "<id>_spectrogram_*.png" for these ids, from one folder scan."""
    ids = {str(i) for i in rec_ids if i}
    if not ids:
        return []
    out = []
    try:
        with os.scandir(settings.spectrograms_dir) as it:
            for entry in it:
                owner, sep, _ = entry.name.partition(_SPEC_SEP)
                if sep and owner in ids and entry.name.endswith(".png"):
                    out.append(entry.path)
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.warning("Spectrogram scan of %s failed: %s", settings.spectrograms_dir, e)
    return out


def remove_files(job: dict) -> tuple:
    """Delete a collect_files() job's files. Returns (files removed, bytes freed)."""
    if not job:
        return 0, 0
    removed = freed = 0
    for path in list(job.get("paths") or []) + spectrogram_files(job.get("rec_ids") or []):
        try:
            size = os.path.getsize(path)
            os.unlink(path)
            removed += 1
            freed += size
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.debug("Could not delete %s: %s", path, e)
    try:
        from .storage_manager import sweep_derived_files
        removed += sweep_derived_files(job.get("owner_ids") or [], settings.enhanced_dir)
    except Exception as e:
        logger.debug("Enhanced cache sweep failed: %s", e)
    return removed, freed


def delete_recordings(db, targets: list, delete_files: bool = True,
                      batch_size: int = 20, pause: float = 0.05) -> dict:
    """Hard-delete recordings and (optionally) their files.

    Small batches, one commit each, and the files removed after each commit:
    SQLite has one writer, so a long delete transaction made every upload,
    heartbeat and delete fail with "database is locked"."""
    import time
    purged = removed_files = freed_bytes = 0
    for i in range(0, len(targets), batch_size):
        batch = targets[i:i + batch_size]
        try:
            with db.no_autoflush:
                job = collect_files(batch) if delete_files else None
                for rec in batch:
                    db.delete(rec)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning("Recording delete batch failed (%d done so far): %s", purged, e)
            break
        purged += len(batch)
        if job:
            n, b = remove_files(job)
            removed_files += n
            freed_bytes += b
        if pause and i + batch_size < len(targets):
            time.sleep(pause)
    if purged:
        try:
            from ..cache import invalidate_detection_caches
            invalidate_detection_caches()
        except Exception:
            pass
    return {
        "purged": purged,
        "removed_files": removed_files,
        "freed_bytes": freed_bytes,
        "freed_mb": round(freed_bytes / 1048576, 2),
    }


def merge_jobs(jobs: Iterable[dict]) -> dict:
    out = {"paths": set(), "rec_ids": set(), "owner_ids": set()}
    for j in jobs:
        for k in out:
            out[k].update(j.get(k) or [])
    return {k: sorted(v) for k, v in out.items()}


def remove_files_in_background(job: dict, what: str = "recording") -> None:
    """remove_files on a thread, so the request returns once the row is gone."""
    if not job or not any(job.get(k) for k in ("paths", "rec_ids", "owner_ids")):
        return

    def _run():
        try:
            n, b = remove_files(job)
            logger.info("Removed %d file(s), %.1f MB, for %s", n, b / 1048576, what)
        except Exception as e:
            logger.warning("File cleanup for %s failed: %s", what, e)

    threading.Thread(target=_run, daemon=True, name="file-cleanup").start()


_NUMERIC_VARIANT = __import__("re").compile(r"^(\d+)(_thumb2|_thumb)?(_pal-[A-Za-z0-9_-]+)?\.png$")


def scan_spectrogram_cache(recordings: dict, current_key: str, palette: str,
                           delete: bool = False, sample_limit: int = 25) -> dict:
    """Split the spectrograms folder into kept vs removable files.

    `recordings` maps every recording id in the database to True when its
    audio is still stored (not archived), False otherwise. Removable:
    - files of a recording that no longer exists;
    - for a recording with audio, threshold variants other than the current
      display threshold and 0 (the stored full view), thumbnails from before
      "_thumb2", and other colour palettes. They are regenerated on request.
    An archived recording keeps every variant: with no audio, a cached
    spectrogram is all that's left of it. Enhanced, bat and rumble-removed
    images follow their own rules and are left alone."""
    pal_suffix = f"_pal-{palette}" if palette and palette != "vivid" else ""
    keep_keys = {str(current_key), "0"}
    kept = kept_bytes = 0
    removable = removable_bytes = no_owner = old_variant = 0
    deleted = deleted_bytes = errors = 0
    sample = []
    spec_dir = settings.spectrograms_dir
    if not spec_dir or not os.path.isdir(spec_dir):
        return {"exists": False, "path": spec_dir}
    with os.scandir(spec_dir) as it:
        for entry in it:
            owner, sep, rest = entry.name.partition(_SPEC_SEP)
            if not sep:
                continue
            reason = None
            has_audio = recordings.get(owner)
            if has_audio is None:
                reason = "no_owner"
            elif has_audio:
                m = _NUMERIC_VARIANT.match(rest)
                if m and (m.group(1) not in keep_keys or m.group(2) == "_thumb"
                          or (m.group(3) or "") != pal_suffix):
                    reason = "old_variant"
            try:
                size = entry.stat().st_size
            except OSError:
                continue
            if not reason:
                kept += 1
                kept_bytes += size
                continue
            removable += 1
            removable_bytes += size
            if reason == "no_owner":
                no_owner += 1
            else:
                old_variant += 1
            if len(sample) < sample_limit:
                sample.append({"name": entry.name, "size_bytes": size, "reason": reason,
                               "size_human": f"{size / 1024:.0f} KB"})
            if delete:
                try:
                    os.unlink(entry.path)
                    deleted += 1
                    deleted_bytes += size
                except OSError:
                    errors += 1
    from .storage_manager import fmt_bytes
    out = {
        "exists": True, "path": spec_dir,
        "referenced_count": kept, "referenced_bytes": kept_bytes, "referenced_human": fmt_bytes(kept_bytes),
        "orphaned_count": removable, "orphaned_bytes": removable_bytes,
        "orphaned_human": fmt_bytes(removable_bytes),
        "no_owner_count": no_owner, "old_variant_count": old_variant,
        "orphaned_sample": sample,
    }
    if delete:
        out.update({"deleted_count": deleted, "deleted_bytes": deleted_bytes,
                    "deleted_human": fmt_bytes(deleted_bytes), "errors": errors})
    return out
