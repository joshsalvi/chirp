"""
Scheduled database backups. Builds directly on the same sqlite3
.backup() approach already used by the existing manual
/api/settings/backup/download endpoint — a live, consistency-safe
snapshot (safe to run while the app is actively writing to the DB),
not a plain file copy that could grab a half-written page.

Scope note: this backs up the SQLite DATABASE only (all detections,
life list, settings, comments, users) — not the recordings/media
directory. That's a deliberate scope decision, not an oversight: media
can run into many GB-TB depending on retention settings, and copying
that wholesale every night isn't a sensible "backup" strategy for an
application to reimplement — that's what Unraid's own array/backup
tooling is for, operating at the filesystem level where it belongs.
The database is the right thing for Chirp itself to protect
automatically: it's comparatively tiny, and it's the part that can't
be regenerated at all if lost (unlike a recording file, which — worst
case — is just gone, not corrupted-and-silently-wrong).
"""
import sqlite3
import os
import glob
import logging
from datetime import datetime

logger = logging.getLogger("chirp.backup")

BACKUP_SUBDIR = "backups"
FILENAME_PATTERN = "chirp_auto_%Y%m%d_%H%M%S.db"
GLOB_PATTERN = "chirp_auto_*.db"


def backup_dir_path(data_dir: str) -> str:
    path = os.path.join(data_dir, BACKUP_SUBDIR)
    os.makedirs(path, exist_ok=True)
    return path


def create_backup(db_path: str, data_dir: str) -> str:
    """
    Creates one timestamped backup file using SQLite's own online
    backup API (same approach as the existing manual download
    endpoint) — safe to call while the app is live and writing.
    Returns the full path to the created file.
    """
    out_dir = backup_dir_path(data_dir)
    filename = datetime.utcnow().strftime(FILENAME_PATTERN)
    out_path = os.path.join(out_dir, filename)

    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(out_path)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    logger.info(f"Created automatic backup: {filename} ({size_mb:.1f} MB)")
    return out_path


def list_backups(data_dir: str) -> list:
    """
    Returns backups sorted newest-first, each as
    {"filename", "size_bytes", "created_at"} — created_at parsed from
    the filename's own timestamp rather than the file's mtime, since
    mtime can be altered by anything that touches the file (a restore
    of the backups directory itself, a filesystem migration, etc.)
    while the filename's timestamp is set once, at creation, and never
    changes.
    """
    out_dir = backup_dir_path(data_dir)
    results = []
    for path in glob.glob(os.path.join(out_dir, GLOB_PATTERN)):
        filename = os.path.basename(path)
        try:
            ts_part = filename.replace("chirp_auto_", "").replace(".db", "")
            created_at = datetime.strptime(ts_part, "%Y%m%d_%H%M%S")
        except ValueError:
            created_at = datetime.fromtimestamp(os.path.getmtime(path))
        results.append({
            "filename": filename,
            "size_bytes": os.path.getsize(path),
            "created_at": created_at.isoformat() + "Z",
        })
    results.sort(key=lambda r: r["created_at"], reverse=True)
    return results


def prune_old_backups(data_dir: str, retention_count: int) -> int:
    """
    Deletes the oldest backups beyond retention_count. Returns how many
    were deleted (0 is the common case — nothing to prune yet on a
    fresh install, or already at/under the limit).
    """
    backups = list_backups(data_dir)
    to_delete = backups[retention_count:]  # list_backups() is newest-first, so this is everything past the keep-count
    out_dir = backup_dir_path(data_dir)
    deleted = 0
    for b in to_delete:
        try:
            os.remove(os.path.join(out_dir, b["filename"]))
            deleted += 1
        except OSError as e:
            logger.warning(f"Failed to prune old backup {b['filename']}: {e}")
    if deleted:
        logger.info(f"Pruned {deleted} backup(s) beyond retention count {retention_count}")
    return deleted


def run_scheduled_backup(db_path: str, data_dir: str, retention_count: int) -> dict:
    """Entry point called from the scheduler loop in main.py — creates one backup, then prunes."""
    path = create_backup(db_path, data_dir)
    deleted = prune_old_backups(data_dir, retention_count)
    return {"created": os.path.basename(path), "pruned": deleted}


def record_backup_result(db, app_settings, db_path: str, data_dir: str, retention_count: int) -> dict:
    """
    Runs run_scheduled_backup() and writes the result to
    AppSettings.auto_backup_last_run_at/last_success_at/last_error,
    committing on `db` — shared by both the scheduler loop (main.py)
    and the manual "Run Now" endpoint (api/app_settings.py) so both
    paths leave an identical, real trail of what actually happened,
    not just a server-log line nobody but a container-log reader would
    ever see.

    `app_settings` is the already-loaded AppSettings row for `db`'s
    session — callers own fetching/creating it (via _get_or_create in
    the API case, or a plain query in the scheduler-loop case) since
    the two callers use different SQLAlchemy session lifecycles.

    Returns {"created": ..., "pruned": ...} on success or {"error":
    ...} on failure — the caller decides how to surface that further
    (an HTTP error for the manual endpoint, a log line for the
    scheduler loop, which already had one).
    """
    from datetime import datetime as _dt
    app_settings.auto_backup_last_run_at = _dt.utcnow()
    try:
        result = run_scheduled_backup(db_path, data_dir, retention_count)
        app_settings.auto_backup_last_success_at = app_settings.auto_backup_last_run_at
        app_settings.auto_backup_last_error = None
        db.commit()
        return result
    except Exception as e:
        err = str(e)[:500]
        app_settings.auto_backup_last_error = err
        db.commit()
        return {"error": err}

