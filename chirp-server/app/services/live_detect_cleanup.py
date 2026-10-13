"""
Cleanup for orphaned Live Detect poll clips — the individual, few-
second recordings a single poll creates while a session is in
progress (see live_detect.py's own analyze endpoint and its
is_live_detect_clip flag). These are meant to be transient: consumed
by save_session() when a person explicitly saves what they heard, or
otherwise left behind if they just stop listening without saving.

Added directly after a real report: leaving a Live Detect page open
for a couple of minutes created hundreds of these, and — before the
is_live_detect_clip flag existed — every one of them stayed in the
main Recordings list and dashboard counts permanently, with nothing
to ever clean them up. Hiding them from the list (see recordings.py's
own is_live_detect_clip exclusion) solves the visibility problem; this
module solves the other half — the rows and their audio files
shouldn't just sit there forever, either.
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Generous on purpose: long enough that a real, still-in-progress
# session (someone on an hours-long birding walk, phone screen off
# part of the time) is never mistaken for an abandoned one, short
# enough that orphaned clips don't linger for days before being swept.
ORPHAN_AGE_HOURS = 24


def cleanup_orphaned_live_detect_clips(db, recordings_dir: str, spectrograms_dir: str, clips_dir: str) -> int:
    """
    Deletes every is_live_detect_clip=True Recording (and its files)
    older than ORPHAN_AGE_HOURS in the given session's own database.
    Returns the number removed. Safe to call repeatedly — there's
    nothing left to find once a session's own save (or a previous
    sweep) has already cleared them.
    """
    from ..models import Recording
    from .file_cleanup import delete_recordings

    cutoff = datetime.utcnow() - timedelta(hours=ORPHAN_AGE_HOURS)
    orphans = (
        db.query(Recording)
        .filter(Recording.is_live_detect_clip.is_(True))
        .filter(Recording.trigger_timestamp < cutoff)
        .all()
    )
    removed = delete_recordings(db, orphans)["purged"] if orphans else 0
    if removed:
        logger.info("Removed %d orphaned Live Detect clip(s) older than %dh", removed, ORPHAN_AGE_HOURS)
    return removed
