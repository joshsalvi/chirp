"""
The shared species library: one copy of each bird's profile data for every
location on this server, kept in the registry database.

When a location first hears a species, bird_enricher.ensure_profile() fills
its profile from here instead of the web (Wikipedia, iNaturalist, eBird,
All About Birds, range maps); after any full enrichment it writes the result
back, so a refresh in one location freshens it for all. Photos, sounds and
range maps are files in the shared media folder, so their paths work
everywhere.

Kept per location (never copied): the seasonal chart (eBird's bar chart is
regional), notes, the AI presence summary, and the enrichment timestamps.

Only in the multi-location server; chirp-server has no registry, and
bird_enricher treats a missing module as "no library".
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import JSON, Column, DateTime, String

from ..registry_db import RegistryBase, RegistrySessionLocal, registry_engine

logger = logging.getLogger("chirp.species_library")

MAX_AGE_DAYS = 30          # same as BirdEnricher.ENRICH_INTERVAL_DAYS
LOCAL_FIELDS = {
    "id", "label", "monthly_frequency", "notes",
    "ai_presence_summary", "ai_presence_summary_generated_at", "ai_presence_summary_error",
    "last_enriched", "enrichment_complete",
}
FILE_FIELDS = ("photo_path", "photo_thumb_path")


class SpeciesLibraryEntry(RegistryBase):
    __tablename__ = "species_library"

    label = Column(String, primary_key=True)          # BirdNET label, as BirdProfile.label
    common_name = Column(String, nullable=True, index=True)
    data = Column(JSON, nullable=False)                # shared BirdProfile fields
    enriched_at = Column(DateTime, nullable=False)
    source_db = Column(String, nullable=True)          # database file of the location that fetched it


_ready = False


def _ensure_table():
    global _ready
    if not _ready:
        SpeciesLibraryEntry.__table__.create(bind=registry_engine, checkfirst=True)
        _ready = True


def _shared_columns():
    from ..models import BirdProfile
    return [c.name for c in BirdProfile.__table__.columns if c.name not in LOCAL_FIELDS]


def _jsonable(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _from_json(name, v):
    from ..models import BirdProfile
    col = BirdProfile.__table__.columns.get(name)
    if v is not None and col is not None and col.type.python_type is datetime and isinstance(v, str):
        try:
            return datetime.fromisoformat(v)
        except ValueError:
            return None
    return v


def get(label: str) -> Optional[SpeciesLibraryEntry]:
    """A fresh, usable entry for this label, or None."""
    try:
        _ensure_table()
        reg = RegistrySessionLocal()
        try:
            e = reg.query(SpeciesLibraryEntry).filter(SpeciesLibraryEntry.label == label).first()
            if not e or datetime.utcnow() - e.enriched_at > timedelta(days=MAX_AGE_DAYS):
                return None
            # A photo that's gone from disk means the copy isn't whole: let the
            # location fetch its own (and write a fresh entry back).
            if any(e.data.get(f) and not os.path.exists(e.data[f]) for f in FILE_FIELDS):
                return None
            reg.expunge(e)
            return e
        finally:
            reg.close()
    except Exception as ex:
        logger.warning("Species library read for %s failed: %s", label, ex)
        return None


def apply(profile, entry: SpeciesLibraryEntry) -> None:
    """Copies the shared fields onto a location's profile (not committed)."""
    for name in _shared_columns():
        if name in entry.data:
            setattr(profile, name, _from_json(name, entry.data[name]))


def put(profile, source: Optional[str] = None) -> None:
    """Stores a fully enriched profile's shared fields."""
    if not getattr(profile, "enrichment_complete", False) or getattr(profile, "is_bat", False):
        return
    try:
        _ensure_table()
        data = {name: _jsonable(getattr(profile, name, None)) for name in _shared_columns()}
        reg = RegistrySessionLocal()
        try:
            e = reg.query(SpeciesLibraryEntry).filter(SpeciesLibraryEntry.label == profile.label).first()
            if not e:
                e = SpeciesLibraryEntry(label=profile.label)
                reg.add(e)
            e.common_name, e.data = profile.common_name, data
            e.enriched_at = profile.last_enriched or datetime.utcnow()
            e.source_db = source
            reg.commit()
        finally:
            reg.close()
    except Exception as ex:
        logger.warning("Species library write for %s failed: %s", getattr(profile, "label", "?"), ex)


def stats() -> dict:
    try:
        _ensure_table()
        reg = RegistrySessionLocal()
        try:
            from sqlalchemy import func
            n, newest = reg.query(func.count(SpeciesLibraryEntry.label), func.max(SpeciesLibraryEntry.enriched_at)).one()
            return {"species": n or 0, "newest": newest.isoformat() + "Z" if newest else None}
        finally:
            reg.close()
    except Exception:
        return {"species": 0, "newest": None}


def backfill() -> int:
    """Seeds the library from every location's complete profiles (newest
    wins). Runs once in the background at startup; cheap when already full."""
    from ..instance_registry import iter_instance_sessions
    from ..models import BirdProfile
    _ensure_table()
    reg = RegistrySessionLocal()
    try:
        have = {label: at for label, at in reg.query(SpeciesLibraryEntry.label, SpeciesLibraryEntry.enriched_at)}
    finally:
        reg.close()
    added = 0
    for item in iter_instance_sessions():
        db, source = (item[1], item[0]) if isinstance(item, tuple) else (item, None)
        try:
            for p in db.query(BirdProfile).filter(BirdProfile.enrichment_complete == True,   # noqa: E712
                                                  BirdProfile.is_bat == False).all():          # noqa: E712
                if not p.last_enriched or datetime.utcnow() - p.last_enriched > timedelta(days=MAX_AGE_DAYS):
                    continue
                if p.label in have and have[p.label] >= p.last_enriched:
                    continue
                if any(getattr(p, f) and not os.path.exists(getattr(p, f)) for f in FILE_FIELDS):
                    continue
                put(p, getattr(source, "db_filename", None) if source is not None else None)
                have[p.label] = p.last_enriched
                added += 1
        except Exception as e:
            logger.warning("Species library backfill skipped a location: %s", e)
    if added:
        logger.info("Species library: %d species added or refreshed from existing locations", added)
    return added
