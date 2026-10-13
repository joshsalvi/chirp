"""
Shared detection filters for the statistics, Dashboard and Life List queries.

Species heard only through Haikubox are left out of species counts (they
were never heard by this Chirp install). The queries used to express that
as `common_name IN (SELECT DISTINCT common_name ... non-Haikubox)`; SQLite
evaluated that subquery inside every statistics query and, with a
(common_name, recording_id) index present, probed every species for every
recording (7-10 s per query on 60k recordings). The Haikubox-only list is
short (usually empty), so it's computed once, cached, and excluded with
NOT IN instead. Same rows either way: every species is either Haikubox-only
or has a non-Haikubox detection.
"""
from sqlalchemy import text

from ..cache import species_filter_cache
from ..models import Detection

# Species with a Haikubox detection, then those with no other detection.
# CROSS JOIN fixes the join order (SQLite never reorders it): detections by
# species first, stopping at the first non-Haikubox row. Left to itself the
# planner walked every non-Haikubox recording per species (8.7 s at 60k).
_SQL = text("""
    WITH hb AS (
        SELECT DISTINCT d.common_name AS name
        FROM recordings r CROSS JOIN detections d ON d.recording_id = r.id
        WHERE r.haikubox_detection_id IS NOT NULL)
    SELECT name FROM hb WHERE NOT EXISTS (
        SELECT 1 FROM detections d2 CROSS JOIN recordings r2 ON r2.id = d2.recording_id
        WHERE d2.common_name = hb.name AND r2.haikubox_detection_id IS NULL)
""")


def haikubox_only_species(db) -> list:
    """Species whose every detection comes from a Haikubox import."""
    cached = species_filter_cache.get("haikubox_only")
    if cached is not None:
        return cached
    names = sorted(r[0] for r in db.execute(_SQL).fetchall() if r[0])
    species_filter_cache.set("haikubox_only", names)
    return names


def exclude_haikubox_only(query, db):
    """query filtered to species with at least one non-Haikubox detection."""
    names = haikubox_only_species(db)
    return query.filter(~Detection.common_name.in_(names)) if names else query
