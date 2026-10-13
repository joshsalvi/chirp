import re
import uuid
from datetime import datetime
"""
Chirp Server — Birds API
Bird profiles, species likelihood, and media serving.
"""
import os
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_

from ..config import settings
from ..database import get_db
from ..models import BirdProfile, Detection, Recording, AppSettings, Comment, BirdPhoto

logger = logging.getLogger("chirp.api.birds")

# In-process guard against duplicate concurrent profile-summary
# generation for the same profile — same real pattern as bird_enricher.py's
# _enriching_now. Without this, the lazy first-view trigger below fires on
# EVERY GET request where the summary isn't set yet, and since local
# providers (e.g. Ollama) can easily take 9-10+ seconds per generation, the
# frontend's own 2.5-second polling loop (BirdProfile.jsx's
# PresenceSummaryCard) was itself repeatedly re-triggering brand-new
# duplicate background generations for the same profile before the first
# one had even finished — confirmed directly from a real server log
# showing 3 separate "Profile summary generated" completions for the same
# species within about 20 seconds of a single page view. Wasteful (three
# full LLM calls for one page view) and, worse, the concurrent load could
# slow every one of them down enough that none finished inside the
# frontend's own polling window, which is the actual "can't generate"
# symptom this was reported as. Ported from the same real fix verified in
# chirp-server (files were byte-identical for this whole region before
# porting).
_summary_generating_now: set = set()

def _range_maps_enabled(db) -> bool:
    """Return True if range maps are enabled in AppSettings (default: False — experimental feature)."""
    try:
        from ..models import AppSettings
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        if s is None:
            return False
        return bool(getattr(s, 'range_maps_enabled', False))
    except Exception:
        return False


from . import moderation as _mod
from .auth import get_current_user as _current_user

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────


def _min_conf_display(db) -> float:
    """Return the minimum confidence threshold for displaying detections (0.0 = show all)."""
    try:
        from ..models import AppSettings
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        v = float(getattr(s, 'min_confidence_display', 0.0) or 0.0) if s else 0.0
        return v
    except Exception:
        return 0.0


def _show_deleted(db) -> bool:
    """Return True if deleted recordings should be included in counts."""
    try:
        from ..models import AppSettings
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        return bool(getattr(s, 'show_deleted_detections', False)) if s else False
    except Exception:
        return False


def _observation_heatmap_enabled(db) -> bool:
    """Return True if the iNaturalist observation heatmap is enabled (default: False)."""
    try:
        from ..models import AppSettings
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        if s is None:
            return False
        return bool(getattr(s, 'observation_heatmap_enabled', False))
    except Exception:
        return False


def _get_app_settings(db):
    """Return AppSettings row (id=1), or None. Uses SQLAlchemy session identity map
    so repeated calls within the same request hit memory, not the database."""
    try:
        from ..models import AppSettings
        return db.query(AppSettings).filter(AppSettings.id == 1).first()
    except Exception:
        return None

class CallMediaItem(BaseModel):
    path: Optional[str]
    url: Optional[str]
    source: Optional[str]
    quality: Optional[str]
    type: Optional[str]   # "call" or "song"


class BirdProfileOut(BaseModel):
    id: str
    label: str
    common_name: str
    scientific_name: Optional[str]
    # Server-side feature flags — passed to frontend to gate experimental UI
    range_maps_enabled: Optional[bool] = False
    observation_heatmap_enabled: Optional[bool] = False
    show_deleted_detections: Optional[bool] = False
    description: Optional[str]
    description_source: Optional[str]
    description_sections: Optional[List[dict]]  # Full multi-section article
    photo_url: Optional[str]
    photo_credit: Optional[str]
    has_local_photo: bool
    extra_photos: Optional[List[dict]]          # Additional photos
    call_media: List[dict]
    monthly_frequency: Optional[List[float]] = None
    inaturalist_url: Optional[str]
    ebird_species_code: Optional[str]
    order_name: Optional[str]
    family_name: Optional[str]
    conservation_status: Optional[str]
    conservation_authority: Optional[str]
    # Cornell Lab of Ornithology / All About Birds — real, distinct
    # content from the description above (which may itself now be
    # AAB-sourced too — see bird_enricher.py's preference logic). Kept
    # as its own separate set of fields rather than folded into
    # description_sections, since aab_cool_facts specifically is a list
    # of independent, real facts meant to be shown as distinct items in
    # the UI (e.g. one-at-a-time or as a bulleted list), not prose.
    aab_url: Optional[str] = None
    aab_description: Optional[str] = None
    aab_cool_facts: Optional[List[str]] = None
    aab_habitat: Optional[str] = None
    aab_food: Optional[str] = None
    aab_nesting: Optional[str] = None
    aab_behavior: Optional[str] = None
    aab_length_min_cm: Optional[float] = None
    aab_length_max_cm: Optional[float] = None
    aab_length_text: Optional[str] = None
    aab_conservation: Optional[str] = None
    aab_habitat_text: Optional[str] = None
    aab_food_text: Optional[str] = None
    aab_nesting_text: Optional[str] = None
    aab_behavior_text: Optional[str] = None
    aab_conservation_text: Optional[str] = None
    range_map_url: Optional[str]
    range_map_source: Optional[str] = None   # "aab" | "macaulay" | "wikipedia" | "ebird_st" | "gbif"
    is_bat: bool = False   # True for the generic "Bat" pseudo-species AND any
                            # confidently-classified specific bat species — gates
                            # range map / eBird-specific UI off in the frontend,
                            # since none of that bird-specific data applies to bats
    inaturalist_id: Optional[int]               # For observation map tiles
    enrichment_complete: Optional[bool] = False
    notes: Optional[str] = None          # User-editable free-text notes
    # Stats from recordings
    total_detections: int
    avg_confidence: float
    max_confidence: float = 0.0
    last_detected: Optional[str]
    ai_presence_summary: Optional[str] = None
    ai_presence_summary_enabled: Optional[bool] = False   # whether the profile_summary feature has a provider assigned at all — frontend gate, independent of whether text exists yet
    ai_presence_summary_error: Optional[str] = None
    ai_presence_summary_generated_at: Optional[str] = None   # ISO string — was tracked on the model and used server-side for staleness (see refresh_stale_profile_summaries) but never actually sent to the frontend, so the card had no way to show when its own text was written

    class Config:
        from_attributes = True


class BirdLikelihood(BaseModel):
    common_name: str
    scientific_name: Optional[str]
    ebird_species_code: Optional[str]
    label: Optional[str]
    detection_count: int
    last_seen: Optional[str]
    likelihood_score: float    # 0-1
    likelihood_label: str      # "Very Likely", "Likely", "Possible", "Rare"
    photo_url: Optional[str]
    has_local_photo: bool


def profile_to_out(profile: BirdProfile, db: Session) -> BirdProfileOut:
    # Detection stats — filter by min_confidence_display so counts match what the
    # user sees in the recordings list and on the dashboard.
    from sqlalchemy import distinct as _distinct
    _s_check = _get_app_settings(db)
    _show_del  = bool(getattr(_s_check, 'show_deleted_detections', False)) if _s_check else False
    _min_conf  = float(getattr(_s_check, 'min_confidence_display', 0.0) or 0.0) if _s_check else 0.0
    _deleted_filter = Recording.deleted_at.is_(None) if not _show_del else Recording.id.isnot(None)
    _stats_base = (
        db.query(
            func.count(_distinct(Detection.id)).label("count"),
            func.avg(Detection.confidence).label("avg_conf"),
            func.max(Detection.confidence).label("max_conf"),
            func.max(Recording.trigger_timestamp).label("last_seen"),
        )
        .join(Recording, Detection.recording_id == Recording.id)
        .filter(_deleted_filter if _deleted_filter is not True else Recording.id.isnot(None))
        .filter(
            (Detection.label == profile.label) |
            (Detection.common_name == profile.common_name)
        )
    )
    if _min_conf > 0:
        _stats_base = _stats_base.filter(Detection.confidence >= _min_conf)
    stats = _stats_base.first()

    photo_url = None
    has_local = False
    if profile.photo_path and os.path.exists(profile.photo_path):
        has_local = True
        photo_url = f"/api/v1/birds/{profile.id}/photo"
    elif profile.photo_url:
        photo_url = profile.photo_url

    # Fetch AppSettings ONCE for all feature flags (was 4 separate queries)
    _s = _get_app_settings(db)
    return BirdProfileOut(
        id=profile.id,
        label=profile.label,
        common_name=profile.common_name,
        scientific_name=profile.scientific_name,
        description=profile.description,
        description_source=profile.description_source,
        description_sections=profile.description_sections,
        photo_url=photo_url,
        photo_credit=profile.photo_credit,
        has_local_photo=has_local,
        extra_photos=profile.extra_photos or [],
        call_media=profile.call_media or [],
        monthly_frequency=profile.monthly_frequency,
        inaturalist_url=profile.inaturalist_url,
        ebird_species_code=profile.ebird_species_code,
        order_name=profile.order_name,
        family_name=profile.family_name,
        conservation_status=profile.conservation_status,
        conservation_authority=profile.conservation_authority,
        aab_url=getattr(profile, 'aab_url', None),
        aab_description=getattr(profile, 'aab_description', None),
        aab_cool_facts=getattr(profile, 'aab_cool_facts', None),
        aab_habitat=getattr(profile, 'aab_habitat', None),
        aab_food=getattr(profile, 'aab_food', None),
        aab_nesting=getattr(profile, 'aab_nesting', None),
        aab_behavior=getattr(profile, 'aab_behavior', None),
        aab_length_min_cm=getattr(profile, 'aab_length_min_cm', None),
        aab_length_max_cm=getattr(profile, 'aab_length_max_cm', None),
        aab_length_text=getattr(profile, 'aab_length_text', None),
        aab_conservation=getattr(profile, 'aab_conservation', None),
        aab_habitat_text=getattr(profile, 'aab_habitat_text', None),
        aab_food_text=getattr(profile, 'aab_food_text', None),
        aab_nesting_text=getattr(profile, 'aab_nesting_text', None),
        aab_behavior_text=getattr(profile, 'aab_behavior_text', None),
        aab_conservation_text=getattr(profile, 'aab_conservation_text', None),
        range_map_url=profile.range_map_url,
        range_map_source=getattr(profile, 'range_map_source', None),
        is_bat=bool(getattr(profile, 'is_bat', False)),
        inaturalist_id=profile.inaturalist_id,
        enrichment_complete=bool(profile.enrichment_complete),
        notes=profile.notes,
        range_maps_enabled=bool(getattr(_s, 'range_maps_enabled', False)) if _s else False,
        observation_heatmap_enabled=bool(getattr(_s, 'observation_heatmap_enabled', False)) if _s else False,
        show_deleted_detections=bool(getattr(_s, 'show_deleted_detections', False)) if _s else False,
        total_detections=stats.count if stats else 0,
        avg_confidence=float(stats.avg_conf) if stats and stats.avg_conf else 0.0,
        max_confidence=float(stats.max_conf) if stats and stats.max_conf else 0.0,
        last_detected=stats.last_seen.isoformat() if stats and stats.last_seen else None,
        ai_presence_summary=profile.ai_presence_summary,
        ai_presence_summary_enabled=bool((_s.ai_feature_providers or {}).get("profile_summary")) if _s else False,
        ai_presence_summary_error=profile.ai_presence_summary_error,
        ai_presence_summary_generated_at=profile.ai_presence_summary_generated_at.isoformat() if profile.ai_presence_summary_generated_at else None,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

def _get_settings_flags(db):
    """Fetch AppSettings once and return all display flags as a dict.
    SQLAlchemy identity map means the same row object is returned for repeated
    queries within a session — but we still pay the lookup cost each time.
    Calling this once and passing the result down eliminates the redundant calls."""
    try:
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        if s is None:
            return {"range_maps": False, "heatmap": False, "show_deleted": False, "min_conf": 0.0}
        return {
            "range_maps":   bool(getattr(s, "range_maps_enabled", False)),
            "heatmap":      bool(getattr(s, "observation_heatmap_enabled", False)),
            "show_deleted": bool(getattr(s, "show_deleted_detections", False)),
            "min_conf":     float(getattr(s, "min_confidence_display", 0.0) or 0.0),
        }
    except Exception:
        return {"range_maps": False, "heatmap": False, "show_deleted": False, "min_conf": 0.0}


@router.get("", response_model=List[BirdProfileOut])
def list_bird_profiles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List all bird profiles detected by Chirp."""
    q = db.query(BirdProfile)
    if search:
        q = q.filter(
            BirdProfile.common_name.ilike(f"%{search}%") |
            BirdProfile.scientific_name.ilike(f"%{search}%")
        )
    profiles = q.order_by(BirdProfile.common_name).offset(skip).limit(limit).all()
    return [profile_to_out(p, db) for p in profiles]


@router.get("/likely")
def likely_species(
    lat: Optional[float] = Query(None),
    lon: Optional[float] = Query(None),
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Return bird species most likely to be at the given location,
    combining eBird recent observations with local detection history.
    """
    # Get location from params or stored settings
    # Fetch AppSettings once for lat/lon + eBird key
    _s_likely = _get_app_settings(db)
    if lat is None or lon is None:
        if _s_likely:
            lat = _s_likely.latitude
            lon = _s_likely.longitude

    from ..services.species_likelihood import SpeciesLikelihoodService
    ebird_key = ((_s_likely.ebird_api_key if _s_likely else None) or settings.ebird_api_key)
    svc = SpeciesLikelihoodService(db, ebird_key)
    return svc.get_likely_species(lat, lon, limit=limit)



# Known Wikipedia range map color-to-label mappings (multiple conventions)
_WIKI_COLOR_LABELS = {
    # ── New Wikipedia standard (maps since ~2010) ─────────────────────────────
    # Breeding: orange variants
    "#ff7f00": "Breeding", "#ff8c00": "Breeding", "#ff6600": "Breeding",
    "#ff9900": "Breeding", "#ffa500": "Breeding", "#e07020": "Breeding",
    "#c08000": "Breeding", "#b87000": "Breeding", "#ff8000": "Breeding",
    "#f4a460": "Breeding", "#cd853f": "Breeding", "#d2691e": "Breeding",
    "#cc6600": "Breeding", "#dd7700": "Breeding", "#e88000": "Breeding",
    # Year-round: purple/violet (hue 260-320)
    "#551a8b": "Year-round", "#5500aa": "Year-round", "#800080": "Year-round",
    "#663399": "Year-round", "#7b2fbe": "Year-round", "#6a0dad": "Year-round",
    "#4b0082": "Year-round", "#6600cc": "Year-round", "#7700bb": "Year-round",
    "#5b2c8c": "Year-round", "#6633aa": "Year-round", "#7744bb": "Year-round",
    "#8855cc": "Year-round", "#9966dd": "Year-round", "#aa77ee": "Year-round",
    "#5c4a8a": "Year-round", "#6b5b95": "Year-round", "#7c6ba8": "Year-round",
    "#483d8b": "Year-round", "#6a5acd": "Year-round", "#7b68ee": "Year-round",
    "#9370db": "Year-round", "#8a2be2": "Year-round", "#9400d3": "Year-round",
    # Migration: yellow/gold
    "#ffff00": "Migration", "#ffe44b": "Migration", "#ffd700": "Migration",
    "#e8d800": "Migration", "#cccc00": "Migration", "#f0d000": "Migration",
    "#ffe066": "Migration", "#ffdd00": "Migration", "#ddbb00": "Migration",
    # Nonbreeding: blue/cyan (hue 190-240)
    "#0080ff": "Nonbreeding", "#00aaff": "Nonbreeding", "#4499cc": "Nonbreeding",
    "#6699cc": "Nonbreeding", "#5588bb": "Nonbreeding", "#4488cc": "Nonbreeding",
    "#3377bb": "Nonbreeding", "#2266aa": "Nonbreeding", "#1a90ff": "Nonbreeding",
    "#00bfff": "Nonbreeding", "#40a0ff": "Nonbreeding", "#5599dd": "Nonbreeding",
    "#6baed6": "Nonbreeding", "#74b9d8": "Nonbreeding", "#87ceeb": "Nonbreeding",
    # ── Old Wikipedia format (pre-2010) ───────────────────────────────────────
    # Old Breeding = blue
    "#0000ff": "Breeding", "#0000cc": "Breeding", "#0033cc": "Breeding",
    "#000099": "Breeding", "#0000dd": "Breeding", "#0011bb": "Breeding",
    # Old Nonbreeding = red
    "#ff0000": "Nonbreeding", "#cc0000": "Nonbreeding", "#dd0000": "Nonbreeding",
    "#ee0000": "Nonbreeding", "#bb0000": "Nonbreeding", "#ff3333": "Nonbreeding",
    # Old Year-round = green
    "#00ff00": "Year-round", "#008000": "Year-round", "#006400": "Year-round",
    "#228b22": "Year-round", "#2e8b57": "Year-round", "#3cb371": "Year-round",
    "#4caf50": "Year-round", "#32cd32": "Year-round", "#00cc00": "Year-round",
}

def _normalize_color(c: str) -> str:
    """Expand 3-digit hex to 6-digit and lowercase."""
    c = c.strip().lower()
    if re.match(r"^#[0-9a-f]{3}$", c):
        c = "#" + c[1]*2 + c[2]*2 + c[3]*2
    return c

def _closest_wiki_label(color: str) -> str:
    """Find closest known Wikipedia color label using RGB distance + HSV hue fallback."""
    import colorsys as _cs
    color = _normalize_color(color)
    if color in _WIKI_COLOR_LABELS:
        return _WIKI_COLOR_LABELS[color]
    try:
        r1 = int(color[1:3], 16) / 255
        g1 = int(color[3:5], 16) / 255
        b1 = int(color[5:7], 16) / 255
        # Weighted RGB distance (human vision: green > red > blue)
        best_label, best_dist = "", 999.0
        for ref_c, label in _WIKI_COLOR_LABELS.items():
            r2 = int(ref_c[1:3], 16) / 255
            g2 = int(ref_c[3:5], 16) / 255
            b2 = int(ref_c[5:7], 16) / 255
            dist = (0.3*(r1-r2)**2 + 0.59*(g1-g2)**2 + 0.11*(b1-b2)**2) ** 0.5
            if dist < best_dist:
                best_dist, best_label = dist, label
        if best_dist < 0.30:
            return best_label
        # Fallback: classify by HSV hue when no close RGB match found.
        # Covers grey-shifted or muted SVG colors not in the table.
        h, s, v = _cs.rgb_to_hsv(r1, g1, b1)
        h_deg = h * 360
        if s < 0.12:  # achromatic — skip
            return ""
        if v < 0.15:  # very dark — skip
            return ""
        # Hue ranges based on Wikipedia map conventions:
        if 20 <= h_deg <= 55:    return "Breeding"      # orange/amber
        if 55 <= h_deg <= 80:    return "Migration"     # yellow
        if 80 <= h_deg <= 165:   return "Year-round"    # green (old style)
        if 180 <= h_deg <= 250:  return "Nonbreeding"   # blue/cyan
        if 250 <= h_deg <= 320:  return "Year-round"    # purple/violet (new style)
        if h_deg > 320 or h_deg < 20:  return "Nonbreeding"  # red (old nonbreeding)
        return best_label
    except Exception:
        return ""

@router.get("/{profile_id}/range-map/geomodel")
def get_geomodel_range_map(profile_id: str, refresh: bool = False, db: Session = Depends(get_db)):
    """
    Render and serve a range map PNG from the locally cached iNaturalist
    GeoPackage, using the species' iNaturalist taxon ID.
    Results are cached in the bird's media directory.

    Pass ?refresh=true to force a fresh re-render rather than serving
    whatever's cached. Previously this endpoint had no way to bypass the
    cache at all — AAB and BirdLife both got on-demand refresh buttons
    already; this brings iNat in line with those, which matters in
    particular right now since anyone who already has a stale cached PNG
    from before the MultiPolygon rendering fix (the star-burst artifact)
    would otherwise keep seeing the broken image forever with no way to
    get a corrected one short of deleting the file on disk by hand.
    """
    import os as _os
    from fastapi.responses import FileResponse
    from ..config import settings as cfg
    from ..services.geomodel_service import render_range_map, get_status

    profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Bird profile not found")
    taxon_id = profile.inaturalist_id
    if not taxon_id:
        logger.info("Geomodel range map: %s has no inaturalist_id on file — nothing to render", profile.common_name)
        raise HTTPException(status_code=404, detail="No iNaturalist taxon ID for this species")

    # Check geopackages are downloaded
    status = get_status(cfg.data_dir)
    if not status.get("ready"):
        raise HTTPException(status_code=503,
                            detail="Geopackage files not downloaded. "
                                   "Go to Settings → Range Maps to download them.")

    # Cached PNG path — must match _prefetch_secondary_range_maps' own
    # convention exactly (cfg.media_dir already includes "birds"; that
    # function's own comment documents this as a previously-fixed bug for
    # itself — this endpoint just never got the same fix, so its cache
    # check here and its refresh-button writes below were both silently
    # missing every file the background prefetch already saved, and vice
    # versa. Confirmed by reading _prefetch_secondary_range_maps directly,
    # not guessed.
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", (profile.common_name or "").lower())
    species_dir = _os.path.join(cfg.media_dir, safe_name)
    _os.makedirs(species_dir, exist_ok=True)
    png_path = _os.path.join(species_dir, "range_map_geomodel.png")

    # Serve cached version if present (and geopackage hasn't been updated)
    # — unless refresh was explicitly requested.
    if not refresh and _os.path.exists(png_path) and _os.path.getsize(png_path) > 1000:
        return FileResponse(png_path, media_type="image/png",
                            headers={"Cache-Control": "public, max-age=86400"})

    # Render fresh map
    ok = render_range_map(
        taxon_id=taxon_id,
        data_dir=cfg.data_dir,
        output_path=png_path,
        common_name=profile.common_name or "",
    )
    if not ok or not _os.path.exists(png_path):
        logger.warning("Geomodel range map: render_range_map returned %s for %s (taxon_id=%s) — "
                        "either the taxon isn't in the geopackage or rendering itself failed; "
                        "see geomodel_service logs above this line for the real cause", ok, profile.common_name, taxon_id)
        raise HTTPException(status_code=404,
                            detail=f"Could not render range map for taxon {taxon_id}. "
                                   "Species may not be in the geopackage.")
    return FileResponse(png_path, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=3600" if refresh else "public, max-age=86400"})


@router.get("/{profile_id}/range-map/ebird_st")
def get_ebird_st_range_map(profile_id: str, refresh: bool = False, db: Session = Depends(get_db)):
    """
    Serve a locally-cached eBird Status & Trends abundance map, from its
    own dedicated file — same pattern as geomodel/birdlife immediately
    above, and added for the same reason: AAB/Macaulay/Wikipedia share a
    single profile.range_map_url/range_map_source pair, which is correct
    for THEM (they're genuinely interchangeable "best available image"
    fallbacks for one slot) — but eBird S&T was sharing that same slot
    too, despite being a structurally different kind of map. Whichever of
    the four was fetched or VIEWED most recently silently overwrote the
    others, so switching to the AAB or Macaulay tab after a successful
    S&T fetch would make S&T immediately report "unavailable" again, even
    though the PNG was still sitting on disk untouched. Reported directly
    as "S&T shows nothing, even after refreshing." Confirmed via the
    shared-field write sites (grep profile.range_map_source = across this
    file) before writing this — not guessed.
    """
    import os as _os
    from fastapi.responses import FileResponse
    from ..config import settings as cfg
    from ..services.range_map_service import fetch_ebird_st_map

    profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Bird profile not found")

    # Path must match _fetch_range_map_bg's own save path exactly (the
    # function that already successfully writes these files) — cfg.media_dir
    # is "/app/data/media/birds" (already includes "birds"), sanitized with
    # the same regex, not just a spaces-to-underscores replace, or a name
    # with punctuation beyond spaces/hyphens (e.g. an apostrophe) would
    # resolve to a different directory than the one already on disk.
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", (profile.common_name or "").lower())
    species_dir = _os.path.join(cfg.media_dir, safe)
    _os.makedirs(species_dir, exist_ok=True)
    png_path = _os.path.join(species_dir, "range_map_ebird_st.png")

    if not refresh and _os.path.exists(png_path) and _os.path.getsize(png_path) > 1000:
        return FileResponse(png_path, media_type="image/png",
                            headers={"Cache-Control": "public, max-age=86400"})

    from ..models import AppSettings
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    api_key = (s.ebird_st_api_key if s else None) or getattr(cfg, "ebird_st_api_key", None)
    if not api_key:
        raise HTTPException(status_code=503,
                            detail="No eBird S&T API key configured. Add one in Settings → Range Maps "
                                   "(get one free at ebird.org/st/request).")
    if not profile.ebird_species_code:
        raise HTTPException(status_code=404,
                            detail="No eBird species code on file — click Refresh All Data first.")

    logger.info("eBird S&T: fetching range map for %s (code=%s) using key %s***",
                profile.common_name, profile.ebird_species_code, api_key[:4])
    ok = fetch_ebird_st_map(profile.ebird_species_code, api_key, png_path)
    if not ok or not _os.path.exists(png_path):
        raise HTTPException(status_code=404,
                            detail=f"No eBird S&T abundance map available for {profile.common_name}.")
    logger.info("eBird S&T range map saved for %s: %s", profile.common_name, png_path)
    return FileResponse(png_path, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=3600" if refresh else "public, max-age=86400"})
def get_birdlife_range_map(profile_id: str, refresh: bool = False,
                            db: Session = Depends(get_db)):
    """
    Serve a BirdLife DataZone range map screenshot for the species.
    Captured on first request via headless Chromium and cached locally —
    though in normal operation this should already be pre-fetched and
    cached during enrichment (see BirdEnricher._prefetch_secondary_range_maps),
    so this on-demand path is mainly a fallback for species enriched before
    that existed, or where the pre-fetch attempt didn't succeed.
    Pass ?refresh=true to re-capture (also re-extracts the legend).
    """
    import os as _os
    from fastapi.responses import FileResponse

    profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Bird profile not found")
    if not profile.scientific_name:
        raise HTTPException(status_code=404,
                            detail="No scientific name — cannot resolve a BirdLife page")

    from ..config import settings as cfg

    # Same fix, same reasoning, as the geomodel endpoint immediately above —
    # this must match _prefetch_secondary_range_maps' convention exactly.
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", (profile.common_name or "").lower())
    species_dir = _os.path.join(cfg.media_dir, safe_name)
    _os.makedirs(species_dir, exist_ok=True)
    png_path = _os.path.join(species_dir, "range_map_birdlife.png")

    if not refresh and _os.path.exists(png_path) and _os.path.getsize(png_path) > 5_000:
        return FileResponse(png_path, media_type="image/png",
                            headers={"Cache-Control": "public, max-age=86400"})

    # Capture via Playwright — resolves the real factsheet URL via BirdLife's
    # own search (immune to common-name mismatches like "European Starling"
    # vs BirdLife's "Common Starling"), and explicitly checks for a 404 page
    # before screenshotting so a 404 is never saved/served as if it were a
    # real map. See fetch_birdlife_range_map_full's docstring for the full
    # rationale — this replaced a version that 404'd for a meaningful
    # fraction of species due to that common-name mismatch.
    from ..services.bird_enricher import fetch_birdlife_range_map_full_standalone
    result = fetch_birdlife_range_map_full_standalone(
        common_name=profile.common_name,
        scientific_name=profile.scientific_name,
        output_path=png_path,
        db=db,
    )
    if not result.get("ok") or not _os.path.exists(png_path):
        error = result.get("error") or "unknown_error"
        if error == "404_not_found":
            detail = (f"BirdLife has no factsheet page for {profile.common_name} "
                      f"under that name or its scientific name ({profile.scientific_name}).")
        elif error == "playwright_not_installed":
            detail = "Playwright + Chromium are not installed in this container."
        else:
            detail = f"Could not capture BirdLife range map ({error})."
        raise HTTPException(status_code=503, detail=detail)

    if result.get("legend"):
        profile.birdlife_legend = result["legend"]
        db.commit()

    return FileResponse(png_path, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=3600"})


@router.get("/{profile_id}/range-map-legend")
def get_range_map_legend(profile_id: str, source: str = "wikipedia", db: Session = Depends(get_db)):
    """
    Return the legend for a bird's range map, scoped to the requested
    source ("birdlife" | "aab" | "wikipedia"/anything else).

    "birdlife" and "aab" return the real per-species legend captured at
    enrichment/fetch time (BirdLife: read from that species' live DOM;
    AAB: read from that species' page legend text, colors assigned from
    AAB's documented fixed 4-color convention) — see fetch_birdlife_range_map_full
    and _extract_aab_legend in bird_enricher.py. This is what makes the
    legend correct per-bird instead of one fixed global swatch list: a
    species whose map only shows e.g. "Year-round" won't have "Breeding"
    or "Migration" entries invented for it.

    Anything else falls back to the original behavior: parsing the saved
    Wikipedia SVG to extract legend colors with labels, using embedded SVG
    text labels first, falling back to color-matching against known
    Wikipedia range map color conventions. This path is unchanged from
    before and only applies when range_map_source is "wikipedia"/"gbif"/etc.
    """
    profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not profile:
        return {"legend": [], "source": "none", "aspect_ratio": None}

    if source == "birdlife":
        legend = getattr(profile, "birdlife_legend", None)
        return {"legend": legend or [], "source": "birdlife_dom" if legend else "no_legend_cached",
                "aspect_ratio": None}

    if source == "macaulay":
        # Macaulay/Cornell CDN range maps are a single published PNG with
        # no embedded color-coded legend at all (unlike AAB's illustrated
        # maps or BirdLife's DOM-extracted legend) — return empty directly
        # rather than falling through to Wikipedia SVG parsing below,
        # which would be wrong for a real Macaulay image specifically.
        return {"legend": [], "source": "no_legend_for_source", "aspect_ratio": None}

    if source == "aab":
        legend = getattr(profile, "aab_legend", None)
        if legend:
            return {"legend": legend, "source": "aab_dom", "aspect_ratio": None}
        # Only fall through to the SVG-parsing path below if range_map_url
        # is ACTUALLY a Wikipedia-sourced file — the "aab" tab shows
        # whatever profile.range_map_url resolved to (AAB, Macaulay, or
        # Wikipedia, depending on which source succeeded during
        # enrichment; see _resolve_range_map's priority chain), and a
        # Wikipedia SVG's legend has no relationship whatsoever to an AAB
        # or Macaulay illustration's colors. The previous version fell
        # through unconditionally here regardless of the actual source,
        # which is exactly why species enriched via AAB but with no
        # aab_legend ever extracted (e.g. profiles enriched before this
        # extraction logic existed, or where extraction found nothing that
        # time) would display a Wikipedia legend on top of an AAB map —
        # real colors, real categories, just for the wrong map entirely.
        if profile.range_map_source not in ("wikipedia", "gbif"):
            return {"legend": [], "source": "no_legend_cached", "aspect_ratio": None}

    return _get_wikipedia_svg_legend(profile)


def _get_wikipedia_svg_legend(profile: "BirdProfile") -> dict:
    """
    Parse saved SVG to extract legend colors with labels.
    Uses embedded SVG text labels first, falls back to color-matching
    against known Wikipedia range map color conventions.
    Unchanged from the original get_range_map_legend body — only extracted
    into its own function so get_range_map_legend can branch to the real
    per-bird BirdLife/AAB legends first.
    """
    import os as _os
    import xml.etree.ElementTree as _ET

    if not profile or not profile.range_map_url:
        return {"legend": [], "source": "none", "aspect_ratio": None}

    url = profile.range_map_url
    if not url.startswith("file://"):
        # Remote Wikimedia URLs: browser loads SVG directly. We cannot parse it
        # server-side (403) and different Wikipedia range maps use different color
        # conventions, so we return empty rather than potentially-wrong static legend.
        return {"legend": [], "source": "remote", "aspect_ratio": None}

    path = url[7:]
    if not _os.path.exists(path) or not path.endswith(".svg"):
        return {"legend": [], "source": "not_svg", "aspect_ratio": None}

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()

        # --- Pass 0: direct regex scan for all fill colors in raw SVG ---
        # This is the most reliable method for old-format Wikipedia maps
        raw_fills_all = re.findall(r'fill=["\'](#[0-9a-fA-F]{3,6})["\']', raw)
        raw_fills_style = re.findall(r'fill\s*:\s*(#[0-9a-fA-F]{3,6})', raw)
        all_raw_colors = [_normalize_color(c) for c in raw_fills_all + raw_fills_style]
        # Filter out background/border colors
        IGNORE = {"#f8fafc","#ffffff","#fff","#f0f0f0","#eeeeee","#cccccc",
                  "#e8e8e8","#d9d9d9","#000000","#000","#0a0f14","#333333",
                  "#aaaaaa","#999999","#888888","#777777","#666666","#555555",
                  "#c8c8c8","#b0b0b0","#d3d3d3","#c0c0c0","#e0e0e0","#f5f5f5",
                  "#808080","#a0a0a0"}
        # Filter by luminance+saturation rather than explicit list.
        # Background/ocean colors are near-white, near-black, or very low saturation.
        import colorsys as _csv2
        def _is_range_color(hex_c):
            if hex_c in IGNORE: return False
            try:
                r = int(hex_c[1:3], 16) / 255
                g = int(hex_c[3:5], 16) / 255
                b = int(hex_c[5:7], 16) / 255
                h, s, v = _csv2.rgb_to_hsv(r, g, b)
                h_deg = h * 360
                lum = 0.2126*r + 0.7152*g + 0.0722*b  # relative luminance
                # High-saturation yellows (hue 45-75°) are legitimate range colors
                # even though they have high luminance (yellow #ffff00 lum=0.93)
                is_vivid_yellow = (45 <= h_deg <= 80) and s >= 0.7 and v >= 0.7
                if is_vivid_yellow:
                    return True
                # Skip: too light (background/land/water) or too dark (outlines/text)
                if lum > 0.78 or lum < 0.04: return False
                # Skip: low saturation colors (grey tones, muted neutrals)
                if s < 0.18: return False
                return True
            except Exception: return False
        raw_unique = list(dict.fromkeys(c for c in all_raw_colors if _is_range_color(c)))

        # --- Pass 1: extract CSS class colors from <style> blocks ---
        css_colors = {}
        for style_block in re.findall(r'<style[^>]*>(.*?)</style>', raw, re.DOTALL | re.IGNORECASE):
            for cls, color in re.findall(r'\.([\w-]+)\s*\{[^}]*fill\s*:\s*(#[0-9a-fA-F]{3,6})', style_block):
                css_colors[cls] = _normalize_color(color)

        tree = _ET.parse(path)
        root = tree.getroot()

        # --- Pass 2: look for <g id="..."> or <g class="..."> with title child ---
        labeled = {}
        for el in root.iter():
            tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if tag != "g":
                continue
            title_el = None
            for child in el:
                ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if ctag == "title":
                    title_el = child
                    break
            if title_el is None:
                continue
            title_text = (title_el.text or "").strip()
            if not title_text:
                continue
            # Get fill from this group or its first path child
            fill = el.get("fill") or ""
            style_attr = el.get("style") or ""
            m = re.search(r"fill\s*:\s*(#[0-9a-fA-F]{3,6})", style_attr)
            if m:
                fill = m.group(1)
            if not fill:
                for child in el:
                    ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if ctag in ("path", "polygon", "rect"):
                        fill = child.get("fill") or ""
                        s = child.get("style") or ""
                        m2 = re.search(r"fill\s*:\s*(#[0-9a-fA-F]{3,6})", s)
                        if m2:
                            fill = m2.group(1)
                        cls = child.get("class") or ""
                        if cls and cls in css_colors:
                            fill = css_colors[cls]
                        if fill:
                            break
            if fill and fill.startswith("#"):
                labeled[_normalize_color(fill)] = title_text

        # --- Pass 3: filter to range-relevant labels only, discard geography ---
        # Wikipedia SVGs title BOTH range layers AND country/ocean/continent outlines.
        # We only want seasonal/behavioral range labels, not place names.
        RANGE_KEYWORDS = {
            "breed", "nonbreed", "non-breed", "winter", "summer", "resident",
            "year-round", "year round", "migrat", "passage", "vagrant", "visit",
            "permanent", "seasonal", "spring", "autumn", "fall", "overwinter",
            "nesting", "range", "distribution",
        }
        range_labeled = {
            c: lbl for c, lbl in labeled.items()
            if any(kw in lbl.lower() for kw in RANGE_KEYWORDS)
        }
        if range_labeled:
            legend = [{"color": c, "label": lbl} for c, lbl in range_labeled.items()]
            logger.info("SVG legend: %d range-labeled entries for %s", len(legend), profile.common_name)
            ar = "auto"
            vb = re.search(r'viewBox=["\'\']\s*([\d.e+-]+)\s+([\d.e+-]+)\s+([\d.e+-]+)\s+([\d.e+-]+)', raw)
            if vb:
                w, h = float(vb.group(3)), float(vb.group(4))
                if h > 0: ar = f"{w:.1f} / {h:.1f}"
            return {"legend": legend[:6], "source": "titled_groups", "aspect_ratio": ar}
        # labeled had only geography names — fall through to color-matching

        # --- Pass 4: use raw_unique colors collected in Pass 0 ---
        # Collect best color per label (prefer new-format hue over old-format).
        # E.g. SVG may have both #ff0000 (old Nonbreeding) and #0080ff (new Nonbreeding);
        # we want to show the blue swatch because that's what the map actually renders.

        # Preferred hue ranges for new-format Wikipedia colors (post-2010)
        # Old format: blue=Breeding, red=Nonbreeding, green=Year-round
        # New format: orange=Breeding, purple=Year-round, blue/cyan=Nonbreeding, yellow=Migration
        _NEW_HUE = {
            "Breeding":    (20,  55),   # orange
            "Year-round":  (260, 325),  # purple/violet
            "Nonbreeding": (175, 250),  # blue/cyan
            "Migration":   (55,  80),   # yellow
        }
        def _prefers_new(hex_c, lbl):
            try:
                r = int(hex_c[1:3],16)/255; g = int(hex_c[3:5],16)/255; b = int(hex_c[5:7],16)/255
                h,s,v = _csv2.rgb_to_hsv(r,g,b)
                lo, hi = _NEW_HUE.get(lbl, (0,360))
                return lo <= h*360 <= hi
            except Exception:
                return False

        best_per_label = {}   # label → best hex color
        for color in raw_unique[:10]:
            label = _closest_wiki_label(color)
            if not label:
                continue
            if label not in best_per_label:
                best_per_label[label] = color
            elif _prefers_new(color, label) and not _prefers_new(best_per_label[label], label):
                best_per_label[label] = color   # upgrade to new-format color

        legend = [{"color": c, "label": lbl} for lbl, c in best_per_label.items()]

        if legend:
            logger.info("SVG legend: %d color-matched entries for %s", len(legend), profile.common_name)
            ar = "auto"
            vb = re.search(r'viewBox=["\']\s*([\d.e+-]+)\s+([\d.e+-]+)\s+([\d.e+-]+)\s+([\d.e+-]+)', raw)
            if vb:
                w, h = float(vb.group(3)), float(vb.group(4))
                if h > 0: ar = f"{w:.1f} / {h:.1f}"
            return {"legend": legend[:6], "source": "color_matched", "aspect_ratio": ar}

        # Still return aspect_ratio so frontend can size container correctly
        ar_fallback = "auto"
        vb_fb = re.search(r'viewBox=["\'\'\']\s*[\d.e+-]+\s+[\d.e+-]+\s+([\d.e+-]+)\s+([\d.e+-]+)', raw)
        if vb_fb:
            w_fb, h_fb = float(vb_fb.group(1)), float(vb_fb.group(2))
            if h_fb > 0: ar_fallback = f"{w_fb:.1f} / {h_fb:.1f}"
        return {"legend": [], "source": "no_colors_found", "aspect_ratio": ar_fallback}

    except Exception as e:
        logger.debug("SVG legend parse error for %s: %s", getattr(profile, "id", "?"), e)
        return {"legend": [], "source": "error", "aspect_ratio": None}

@router.post("/ensure/{common_name:path}", response_model=BirdProfileOut)
def ensure_bird_profile(
    common_name: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Ensure a BirdProfile exists for the given common name.
    Creates one and triggers enrichment if it doesn't exist yet.
    Used by the regional library to enable profile pages for undetected birds.
    """
    from urllib.parse import unquote
    name = unquote(common_name)
    profile = db.query(BirdProfile).filter(BirdProfile.common_name == name).first()
    if not profile:
        from ..services.bird_enricher import BirdEnricher
        enricher = BirdEnricher(db)
        profile = enricher._create_profile(name)
        if profile:
            background_tasks.add_task(_enrich_profile, profile.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Could not create bird profile")
    return profile_to_out(profile, db)


@router.get("/by-label/{label:path}", response_model=BirdProfileOut)
def get_profile_by_label(
    label: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Get bird profile by BirdNET label OR common name.
    Navigation from Likely Near Me / Regional Library passes the common name
    (not the full BirdNET label) so we fall back to common_name match.
    Creates the profile and queues enrichment if it does not exist yet.
    """
    from urllib.parse import unquote
    label = unquote(label)

    # "Bat" is checked FIRST and handled entirely separately from the
    # generic lookup below — this is the actual fix for a real, confirmed
    # bug. A correctly-written, dedicated bat-photo mechanism
    # (BirdEnricher._ensure_bat_profile / _fetch_bat_photo, using a real
    # representative photo from iNaturalist's Little Brown Bat taxon)
    # already existed in this codebase but was never actually called from
    # here, the ONLY real entry point for resolving a profile by label —
    # this endpoint called _create_profile(label) directly instead, which
    # has no bat-specific handling at all and never sets a photo for "Bat".
    #
    # Checked before the generic lookup, not just inside the "doesn't exist
    # yet" branch below: _ensure_bat_profile() does its own internal lookup
    # and correctly retrofits a photo onto an EXISTING "Bat" profile that's
    # missing one (checks `if not profile.photo_path`), not just brand-new
    # ones — important since Josh's system almost certainly already has a
    # long-existing "Bat" profile row from before any of this bat-specific
    # code existed. If the generic lookup ran first and found that existing
    # row, we'd skip straight past the "doesn't exist yet" branch and this
    # retrofit would never get a chance to run at all.
    from ..services.bat_profile_content import BAT_LABEL
    if label == BAT_LABEL:
        from ..services.bird_enricher import BirdEnricher
        enricher = BirdEnricher(db)
        profile = enricher._ensure_bat_profile()
        if not profile:
            raise HTTPException(status_code=404, detail=f"No profile for: {label}")
        return profile_to_out(profile, db)

    # Exact label match (detected birds with full BirdNET label)
    profile = db.query(BirdProfile).filter(BirdProfile.label == label).first()

    # Case-insensitive common_name fallback (regional library / likely-near-me)
    if not profile:
        profile = db.query(BirdProfile).filter(
            BirdProfile.common_name.ilike(label)
        ).first()

    # Create stub profile so the page loads and enrichment can run
    if not profile:
        from ..services.bird_enricher import BirdEnricher
        enricher = BirdEnricher(db)
        profile = enricher._create_profile(label)
        if profile:
            background_tasks.add_task(_enrich_profile, profile.id)

    if not profile:
        raise HTTPException(status_code=404, detail=f"No profile for: {label}")

    # Trigger enrichment if profile exists but has never been enriched
    if not profile.enrichment_complete and not profile.last_enriched:
        background_tasks.add_task(_enrich_profile, profile.id)

    return profile_to_out(profile, db)



# ── Life List ─────────────────────────────────────────────────────────────────

@router.get("/life-list")
def get_life_list(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    All bird species ever detected at this location.
    Returns sorted by first-detected date (chronological).
    """
    from ..cache import life_list_cache
    cached = life_list_cache.get("life_list")
    if cached is not None:
        return cached
    from sqlalchemy import func
    _s_lf = _get_app_settings(db)  # single fetch for all flags
    show_del = bool(_s_lf.show_deleted_detections) if _s_lf else False
    min_conf = float(_s_lf.min_confidence_display or 0.0) if _s_lf else 0.0
    _life_q = (
        db.query(
            Detection.common_name,
            Detection.scientific_name,
            Detection.label,
            func.count(Detection.id).label("total_detections"),
            func.min(Recording.trigger_timestamp).label("first_detected"),
            func.max(Recording.trigger_timestamp).label("last_detected"),
            func.avg(Detection.confidence).label("avg_confidence"),
            func.max(Detection.confidence).label("max_confidence"),
            func.max(Recording.is_bat).label("is_bat"),
        )
        .join(Recording, Detection.recording_id == Recording.id)
    )
    if not show_del:
        from ..models import Recording as _Rec
        _life_q = _life_q.filter(_Rec.deleted_at.is_(None))
    if min_conf > 0:
        _life_q = _life_q.filter(Detection.confidence >= min_conf)

    # Exclude species detected ONLY via Haikubox. A species with at
    # least one real Pi/device detection is unaffected by this — it's
    # only the case of a species whose every single detection came from
    # Haikubox that gets excluded here. This matters specifically because
    # disabling Haikubox (the toggle) does NOT delete the underlying
    # Recording rows — it only hides them from the two recordings-list
    # endpoints (see list_recordings/list_haikubox_recordings) — so
    # without this exclusion, a Haikubox-only species would keep
    # appearing on the life list (and, by extension, the Field Guide)
    # even with the feature turned off entirely, which directly
    # contradicts the explicit requirement that such a species disappear
    # in that case. Implemented as "this common_name has zero rows where
    # haikubox_detection_id IS NULL" — i.e. the species has no detection
    # that isn't from Haikubox.
    from ..services.species_filters import exclude_haikubox_only
    _life_q = exclude_haikubox_only(_life_q, db)

    rows = (
        _life_q
        .group_by(Detection.common_name)
        .order_by(func.min(Recording.trigger_timestamp).asc())
        .all()
    )

    # Batch-load all matching BirdProfiles in ONE query (eliminates N+1)
    #
    # Matches on BOTH common_name and label, not common_name alone — same
    # real bug and fix as the Dashboard summary's profile lookup: a
    # profile's common_name (user-facing, editable) can diverge from its
    # label (stable, never edited) — confirmed exactly this happened to
    # the "Bat" profile in production. Keyed by both fields so a lookup
    # by either succeeds.
    all_names = [row.common_name for row in rows]
    profiles_by_name = {}
    for p in db.query(BirdProfile).filter(
        or_(BirdProfile.common_name.in_(all_names), BirdProfile.label.in_(all_names))
    ).all():
        profiles_by_name[p.common_name] = p
        profiles_by_name[p.label] = p
    # Queue enrichment for profiles without photos (outside the loop).
    # Deduplicated by id first — a profile is now reachable via two keys
    # (common_name and label) pointing at the same object, so iterating
    # .values() directly could visit it twice and queue a redundant task.
    seen_profile_ids = set()
    for p in profiles_by_name.values():
        if p.id in seen_profile_ids:
            continue
        seen_profile_ids.add(p.id)
        if not p.enrichment_complete and not p.photo_url and not p.photo_path:
            background_tasks.add_task(_enrich_profile, p.id)

    # Build per-species detection-month map in one query
    # This tells us which calendar months (0-11) Chirp actually detected each bird,
    # based on the month of the Recording.trigger_timestamp.
    all_names_for_months = [row.common_name for row in rows]
    detection_months_by_name: dict = {}
    if all_names_for_months:
        from sqlalchemy import extract as _extract
        month_rows = (
            db.query(
                Detection.common_name,
                _extract("month", Recording.trigger_timestamp).label("month"),
            )
            .join(Recording, Detection.recording_id == Recording.id)
            .filter(Detection.common_name.in_(all_names_for_months))
            .filter(Recording.deleted_at.is_(None) if not show_del else Recording.id.isnot(None))
            .distinct()
            .all()
        )
        for mrow in month_rows:
            name = mrow.common_name
            # SQLite returns month as float (1.0–12.0), convert to 0-indexed int
            month_idx = int(float(mrow.month)) - 1
            if name not in detection_months_by_name:
                detection_months_by_name[name] = []
            if month_idx not in detection_months_by_name[name]:
                detection_months_by_name[name].append(month_idx)

    result = []
    for row in rows:
        profile = profiles_by_name.get(row.common_name)
        photo_url = None
        profile_id = None
        ebird_code = None
        conservation = None
        if profile:
            profile_id = profile.id
            ebird_code = profile.ebird_species_code
            conservation = profile.conservation_status
            if profile.photo_path and os.path.exists(profile.photo_path):
                photo_url = f"/api/v1/birds/{profile.id}/photo"
            elif profile.photo_url:
                photo_url = profile.photo_url

        result.append({
            "common_name": row.common_name,
            "scientific_name": row.scientific_name,
            "label": row.label,
            "profile_id": profile_id,
            "ebird_species_code": ebird_code,
            "conservation_status": conservation,
            "photo_url": photo_url,
            "monthly_frequency": profile.monthly_frequency if profile else None,
            "detection_months": detection_months_by_name.get(row.common_name, []),
            "total_detections": row.total_detections,
            "first_detected": row.first_detected.isoformat() if row.first_detected else None,
            "last_detected": row.last_detected.isoformat() if row.last_detected else None,
            "max_confidence": float(row.max_confidence) if row.max_confidence else 0,
            "ebird_url": f"https://ebird.org/species/{ebird_code}" if ebird_code else None,
            "is_bat": bool(row.is_bat),
        })
    life_list_cache.set("life_list", result)
    return result
@router.get("/identified-bats")
def get_identified_bats(db: Session = Depends(get_db)):
    """
    Bat species that have been confidently identified (not just generic
    "Bat" activity) at this location, with their BirdProfile data for
    display (photo, description, etc — via the normal enrichment
    pipeline, same as any other species).

    A separate endpoint from /regional-library rather than folding bats
    into that response: /regional-library is fundamentally an eBird
    checklist (bird-only taxonomy) cross-referenced against local
    detections — a bat species genuinely cannot appear there no matter
    what gets detected, since eBird has no bat taxonomy at all. This
    endpoint sources directly from the Detection table instead, the same
    way get_life_list() already does, so real bat species IDs show up
    correctly regardless of eBird's bird-only scope.

    Only returns species that actually got assigned as a real
    identification (Detection.common_name != "Bat" AND the parent
    Recording.is_bat is true) — generic, unidentified "Bat" activity is
    intentionally excluded here; that's the Recordings page's job
    (filter: is_bat=true), not the Field Guide's.
    """
    from sqlalchemy import func
    _s_bats = _get_app_settings(db)
    show_del = bool(_s_bats.show_deleted_detections) if _s_bats else False
    min_conf = float(_s_bats.min_confidence_display or 0.0) if _s_bats else 0.0

    q = (
        db.query(
            Detection.common_name,
            func.max(Detection.scientific_name).label("scientific_name"),
            func.count(Detection.id).label("total_detections"),
            func.min(Recording.trigger_timestamp).label("first_detected"),
            func.max(Recording.trigger_timestamp).label("last_detected"),
            func.max(Detection.confidence).label("max_confidence"),
        )
        .join(Recording, Detection.recording_id == Recording.id)
        .filter(Recording.is_bat.is_(True))
        .filter(Detection.common_name != "Bat")
    )
    if not show_del:
        q = q.filter(Recording.deleted_at.is_(None))
    if min_conf > 0:
        q = q.filter(Detection.confidence >= min_conf)
    q = q.group_by(Detection.common_name)
    q = q.order_by(func.min(Recording.trigger_timestamp).asc())

    rows = q.all()

    # Attach BirdProfile data (photo, description) for display — same
    # enrichment pipeline any other species profile uses, since
    # ensure_profile() already ran for these during upload processing
    # (see _process_bat_recording_bg's Step 3). Batched into one query
    # instead of one per row — bounded by distinct species count so this
    # was never a severe N+1, but the batched pattern is already
    # established elsewhere in this file (list_recordings' profile_map)
    # and costs nothing extra to apply here too.
    common_names = [row.common_name for row in rows]
    profile_map = {
        p.common_name: p
        for p in db.query(BirdProfile).filter(BirdProfile.common_name.in_(common_names)).all()
    } if common_names else {}

    results = []
    for row in rows:
        profile = profile_map.get(row.common_name)
        results.append({
            "common_name": row.common_name,
            "scientific_name": row.scientific_name,
            "total_detections": row.total_detections,
            "first_detected": row.first_detected.isoformat() if row.first_detected else None,
            "last_detected": row.last_detected.isoformat() if row.last_detected else None,
            "max_confidence": row.max_confidence,
            "profile_id": profile.id if profile else None,
            "photo_url": (profile.photo_url if profile else None),
            "photo_path": (f"/api/v1/birds/{profile.id}/photo" if profile and profile.photo_path else None),
            "description": (profile.description[:200] if profile and profile.description else None),
        })
    return results


# ── Regional Bird Library ──────────────────────────────────────────────────────

@router.get("/regional-library")
def get_regional_library(
    limit: int = Query(1000, ge=1, le=2000),   # increased: show ALL regional birds
    search: Optional[str] = Query(None),
    detected_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    """
    Full regional checklist from eBird with 12-month frequency data.
    Returns ALL species ever recorded in the region across the full year,
    not just those currently common. Frontend handles filtering by month.
    """
    from ..models import RegionalSpecies

    is_canonical = not search and not detected_only and limit == 1000
    if is_canonical:
        from ..cache import regional_library_cache
        cached = regional_library_cache.get("canonical")
        if cached is not None:
            return cached

    q = db.query(RegionalSpecies)
    if search:
        q = q.filter(
            RegionalSpecies.common_name.ilike(f"%{search}%") |
            RegionalSpecies.scientific_name.ilike(f"%{search}%")
        )
    # NOTE: Do NOT pre-filter by locally_detected here. That stale flag is only
    # updated at eBird sync time. We recompute it live from the Detection table
    # below, then apply detected_only filtering after.
    raw_species = q.order_by(RegionalSpecies.current_likelihood.desc()).limit(limit).all()

    # Deduplicate by eBird species code (stable canonical ID) — falls back to a
    # normalized common_name only when the code is missing. Keying purely on
    # common_name is fragile: eBird taxonomy can return near-duplicate entries
    # (e.g. species + subspecies/spuh group) with subtly different name text
    # that would otherwise survive dedup and appear as repeated cards in the UI.
    # (Duplicate rows can also accumulate in the table if two refreshes ran
    # concurrently in the past — this collapses those too.)
    seen_keyed: dict = {}
    for s in raw_species:
        code = (s.ebird_species_code or "").strip()
        key = code if code else (s.common_name or "").strip().lower()
        if key not in seen_keyed or s.current_likelihood > seen_keyed[key].current_likelihood:
            seen_keyed[key] = s
    species = list(seen_keyed.values())

    # ── Compute locally_detected FRESH from Detection table ───────────────────
    # Excludes Haikubox-only species — "locally detected" is meant to mean
    # the Chirp device's own sensor heard it, not Haikubox's cloud
    # detections. See get_life_list's matching comment in this same file
    # for the full reasoning (same bug, same fix, three places: this Field
    # Guide flag, the life list, and the species-likelihood score in
    # services/species_likelihood.py).
    from ..models import Detection as _Det, Recording as _RecLD
    _s_rl = _get_app_settings(db)
    _min_conf_rl = float(_s_rl.min_confidence_display or 0.0) if _s_rl else 0.0
    _show_del_rl = bool(getattr(_s_rl, "show_deleted_detections", False)) if _s_rl else False
    _det_q_rl = db.query(_Det.common_name).join(_RecLD, _Det.recording_id == _RecLD.id)
    if not _show_del_rl:
        _det_q_rl = _det_q_rl.filter(_RecLD.deleted_at.is_(None))
    if _min_conf_rl > 0:
        _det_q_rl = _det_q_rl.filter(_Det.confidence >= _min_conf_rl)
    _det_q_rl = _det_q_rl.filter(_RecLD.haikubox_detection_id.is_(None))
    live_detected: set = {r[0] for r in _det_q_rl.distinct().all()}

    # Build photo_url lookup. Use chunked IN or full-table scan to avoid
    # SQLite's 999-variable limit when the regional list has >900 species.
    names = [s.common_name for s in species]
    profile_photos: dict = {}
    try:
        if len(names) <= 900:
            bp_rows = db.query(
                BirdProfile.common_name, BirdProfile.id,
                BirdProfile.photo_path, BirdProfile.photo_url,
            ).filter(BirdProfile.common_name.in_(names)).all()
        else:
            # Full table scan is safer than hitting SQLite variable limit
            bp_rows = db.query(
                BirdProfile.common_name, BirdProfile.id,
                BirdProfile.photo_path, BirdProfile.photo_url,
            ).all()
        names_set = set(names)
        for row in bp_rows:
            if row.common_name not in names_set:
                continue
            # Trust photo_path without a synchronous os.path.exists() check —
            # this was a real per-row filesystem stat call (unbatchable,
            # confirmed as a meaningful contributor to slow Field Guide
            # loads with hundreds of regional species), and unnecessary:
            # photo_path only changes during enrichment, not on every
            # request, and the "missing detected birds" loop just below in
            # this same function already trusts it the same way without
            # checking — this just makes both loops consistent.
            if row.photo_path:
                profile_photos[row.common_name] = f"/api/v1/birds/{row.id}/photo"
            elif row.photo_url:
                profile_photos[row.common_name] = row.photo_url
    except Exception as _e:
        logger.warning("profile_photos lookup error: %s", _e)

    # Real fix: current_likelihood was a value STORED at whatever month the
    # last manual "Refresh All Data" sync happened to run in (this data has
    # no scheduled background job — see regional-library/refresh below,
    # it's manual-only), not recomputed against the actual current month at
    # read time. For a migratory species, a profile last refreshed months
    # ago would show a completely wrong-season likelihood — a bird that
    # migrated away in April could still show as "likely now" in July
    # just because nobody re-synced since spring. The full 12-month
    # monthly_frequency array itself is still valid (a year's climatology
    # doesn't go stale the way "this month's value" does), so recomputing
    # which index is actually "now" against that same array fixes this
    # without needing more frequent full re-syncs.
    _real_current_month = datetime.utcnow().month - 1  # 0-indexed, matches ebird_service.py's convention

    def _live_likelihood(s):
        mf = s.monthly_frequency
        if mf and len(mf) == 12:
            return float(mf[_real_current_month])
        return s.current_likelihood

    result = [
        {
            "ebird_species_code": s.ebird_species_code,
            "common_name": s.common_name,
            "scientific_name": s.scientific_name,
            "family_com_name": s.family_com_name,
            "order_name": s.order_name,
            "monthly_frequency": s.monthly_frequency,
            "current_likelihood": _live_likelihood(s),
            "locally_detected": s.common_name in live_detected,
            "photo_url": profile_photos.get(s.common_name) or s.photo_url,
            "fetched_at": s.fetched_at.isoformat() if s.fetched_at else None,
            "ebird_url": f"https://ebird.org/species/{s.ebird_species_code}",
            "days_seen": s.days_seen or 0,
            "total_days": s.total_days or 30,
        }
        for s in species
        # Apply detected_only filter HERE using the live flag, not the stale DB flag
        if not detected_only or s.common_name in live_detected
    ]

    # ── Always append life-list birds missing from RegionalSpecies ────────────
    # These are birds your system has detected that eBird doesn't list for your
    # region (out-of-range visitors, rare strays like Common Eider, etc.).
    # They must appear in BOTH the "All" and "Detected Here" views so the counts
    # always match the Life List. Previously this block was gated on `not
    # detected_only`, which made them invisible when filtering — now always run it.
    # Compare on a normalized (trimmed, lowercased) name so a BirdNET label that
    # differs from eBird's common_name only in case/whitespace doesn't get
    # falsely treated as "missing" and appended as a visual duplicate.
    #
    # Reported directly: species with no plausible business being anywhere
    # near this location (an Australian endemic showing up for a
    # Massachusetts deployment) were appearing prominently at the top of
    # the "most likely now" view — not buried at the bottom the way a
    # rare vagrant would be if it were ranked honestly. Root cause
    # was HERE, not in the eBird region lookup itself: verified directly
    # against the region-lookup code with the deployment's own
    # coordinates and it correctly resolves to the right state/country
    # every time. The bug is that every species landing in this
    # branch — meaning it isn't on the standard eBird checklist for this
    # region at all — was unconditionally given current_likelihood=1.0,
    # the maximum possible value. eBird's own frequency values are
    # almost never 1.0 even for the most common local species, so this
    # guaranteed every one of these entries outranked every legitimate
    # regional species in the sort below — including a single one-off
    # BirdNET misidentification, which now looks identical to a
    # repeatedly-confirmed rare visitor. A low fixed value instead keeps
    # these entries visible (so a rare vagrant is still discoverable
    # in the full list) without artificially inflating them above species
    # that belong here.
    regional_names_norm = {s.common_name.strip().lower() for s in species if s.common_name}
    missing_detected = {n for n in live_detected if n and n.strip().lower() not in regional_names_norm}
    if missing_detected:
        for bp in db.query(BirdProfile).filter(BirdProfile.common_name.in_(missing_detected)).all():
            photo = None
            if bp.photo_path:
                photo = f"/api/v1/birds/{bp.id}/photo"
            elif bp.photo_url:
                photo = bp.photo_url
            # Apply search filter to appended birds as well
            if search and search.lower() not in bp.common_name.lower() \
                       and search.lower() not in (bp.scientific_name or "").lower():
                continue
            result.append({
                "ebird_species_code": bp.ebird_species_code or "",
                "common_name": bp.common_name,
                "scientific_name": bp.scientific_name or "",
                "family_com_name": bp.family_name or "",
                "order_name": bp.order_name or "",
                "monthly_frequency": bp.monthly_frequency or [0.0] * 12,
                "current_likelihood": 0.05,
                "locally_detected": True,
                "photo_url": photo,
                "fetched_at": None,
                "ebird_url": f"https://ebird.org/species/{bp.ebird_species_code}" if bp.ebird_species_code else "",
                "days_seen": 0,
                "total_days": 30,
            })

    # Re-sort by the now-live current_likelihood — the initial DB query's
    # ORDER BY (above, at raw_species assembly) sorted by the stale stored
    # column, same root cause as the value fix above. Without this, a
    # species that peaked in whatever month the last sync happened to run
    # could still rank near the top of "most likely now" long after it's
    # no longer true, while a species that's actually likely this month
    # could rank low simply because it wasn't likely whenever the data was
    # last refreshed.
    result.sort(key=lambda x: (x["current_likelihood"], max(x["monthly_frequency"] or [0])), reverse=True)

    if is_canonical:
        from ..cache import regional_library_cache
        regional_library_cache.set("canonical", result)

    return result


@router.post("/regional-library/refresh")
def refresh_regional_library(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Trigger a background refresh of the regional bird library from eBird."""
    background_tasks.add_task(_refresh_regional_library_bg)
    return {"status": "refresh_queued"}


def _refresh_regional_library_bg():
    """
    Refresh regional species list from eBird.

    Uses eBird spplist for full year-round coverage (not just the past 30 days),
    then supplements with iNaturalist histogram data for 12-month frequency bars.

    ATOMIC WRITE: all new rows are assembled in memory first, then the old table
    is replaced in a single transaction — reads never see a partial list.
    """
    import time as _time
    from ..database import SessionLocal
    from ..models import RegionalSpecies, AppSettings
    from ..services.ebird_service import fetch_regional_species_with_monthly_frequency
    import httpx as _httpx

    db = SessionLocal()
    try:
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        if not s or not s.latitude or not s.longitude:
            logger.info("Regional library refresh skipped: no location set")
            return
        api_key = (s.ebird_api_key or settings.ebird_api_key or "")
        if not api_key:
            logger.info("Regional library refresh skipped: no eBird API key")
            return

        logger.info("Refreshing regional bird library…")
        species_list = fetch_regional_species_with_monthly_frequency(
            s.latitude, s.longitude, api_key
        )
        if not species_list:
            logger.warning("eBird returned no species for this location — aborting refresh")
            return

        # ── Detect locally-observed species ──────────────────────────────────
        from ..models import Detection
        _det_q = db.query(Detection.common_name)
        _s_ll = _get_app_settings(db)
        _det_mc   = float(_s_ll.min_confidence_display or 0.0) if _s_ll else 0.0
        _show_del = bool(getattr(_s_ll, "show_deleted_detections", False)) if _s_ll else False
        # Always join to Recording now — the Haikubox exclusion below
        # needs it unconditionally, not just when one of the two other
        # flags happens to require it (the previous structure only
        # joined "if not _show_del or _det_mc > 0", which would have
        # silently skipped the Haikubox filter whenever both of those
        # were false). See get_life_list's comment in this same file for
        # why a Haikubox-only species must not count as "detected" here.
        from ..models import Recording as _RecDet
        _det_q = _det_q.join(_RecDet, Detection.recording_id == _RecDet.id)
        if not _show_del:
            _det_q = _det_q.filter(_RecDet.deleted_at.is_(None))
        if _det_mc > 0:
            _det_q = _det_q.filter(Detection.confidence >= _det_mc)
        _det_q = _det_q.filter(_RecDet.haikubox_detection_id.is_(None))
        detected_names = {r[0] for r in _det_q.distinct().all()}
        current_month = datetime.utcnow().month - 1

        # ── BirdProfile lookup (for cached monthly data + taxon IDs) ─────────
        profile_map: dict = {}
        for bp in db.query(BirdProfile).all():
            profile_map[bp.common_name] = bp
            if bp.scientific_name:
                profile_map[bp.scientific_name] = bp

        def _inat_histogram(taxon_id: int) -> Optional[list]:
            """Fetch 12-month frequency from iNaturalist histogram (cached in profile)."""
            try:
                r = _httpx.get(
                    "https://api.inaturalist.org/v1/observations/histogram",
                    params={
                        "taxon_id": taxon_id,
                        "quality_grade": "research",
                        "verifiable": "true",
                        "date_field": "observed",
                        "interval": "month_of_year",
                    },
                    headers={"User-Agent": "Chirp-BirdDetection/1.0"},
                    timeout=10,
                )
                if r.status_code != 200:
                    return None
                data = r.json().get("results", {})
                monthly_data = data.get("month_of_year", data)
                raw = [float(monthly_data.get(str(m), 0)) for m in range(1, 13)]
                peak = max(raw) or 1.0
                return [round(v / peak, 3) for v in raw]
            except Exception:
                return None
            finally:
                _time.sleep(0.3)

        # ── Build ALL new rows in memory (no DB writes yet) ───────────────────
        # Assembling everything first means we never write a partial list to the DB.
        new_rows: list = []
        inserted_keys: set = set()
        total = len(species_list)

        for idx, sp in enumerate(species_list, 1):
            name = sp["common_name"]
            if not name:
                continue
            # Dedup key: prefer the stable eBird species code (canonical ID).
            # common_name alone is fragile — eBird taxonomy occasionally returns
            # near-duplicate entries (e.g. a species + its subspecies/spuh group)
            # with slightly different name formatting that would otherwise slip
            # past a name-only dedup and show up as repeated cards in the UI.
            code = (sp.get("ebird_species_code") or "").strip()
            dedup_key = code if code else name.strip().lower()
            if dedup_key in inserted_keys:
                continue
            inserted_keys.add(dedup_key)
            sci = sp.get("scientific_name", "")

            # Frequency priority:
            #   1. BirdProfile cached monthly_frequency (already enriched)
            #   2. iNaturalist histogram via known taxon_id (one API call)
            #   3. Frequency already in species_list entry (from bar chart/estimate)
            monthly = None
            bp = profile_map.get(name) or profile_map.get(sci)
            if bp and bp.monthly_frequency and any(v > 0 for v in bp.monthly_frequency):
                monthly = bp.monthly_frequency
            elif bp and bp.inaturalist_id:
                monthly = _inat_histogram(bp.inaturalist_id)

            if not monthly or not any(v > 0 for v in monthly):
                monthly = sp.get("monthly_frequency") or [0.0] * 12

            current_freq = float(monthly[current_month]) if monthly else 0.0

            new_rows.append(RegionalSpecies(
                id=str(uuid.uuid4()),
                ebird_species_code=sp["ebird_species_code"],
                common_name=name,
                scientific_name=sci,
                family_com_name=sp.get("family_com_name", ""),
                order_name=sp.get("order_name", ""),
                monthly_frequency=monthly,
                current_likelihood=current_freq,
                locally_detected=name in detected_names,
                days_seen=sp.get("days_seen", 0),
                total_days=sp.get("total_days", 30),
                region_code=None,
                fetched_at=datetime.utcnow(),
            ))

            if idx % 50 == 0:
                logger.info("Regional library: built %d/%d rows…", idx, total)

        if not new_rows:
            logger.warning("Regional library refresh: 0 rows assembled — not replacing existing data")
            return

        # ── Atomic swap: delete old, insert all new, single commit ────────────
        # The table goes from full→full with no partial-state window.
        logger.info("Regional library: writing %d species atomically…", len(new_rows))
        db.query(RegionalSpecies).delete()
        for row in new_rows:
            db.add(row)
        db.commit()
        # Confirmed directly: without this, the very next read after a
        # successful refresh could still serve the stale response
        # cached from before it ran (up to this cache's own 60s TTL) —
        # including, worst case, an EMPTY list cached from before the
        # very first refresh a fresh location ever runs, making a
        # genuinely successful refresh look like it silently did
        # nothing. The write above is correct; only the read-side cache
        # was never told anything changed.
        from ..cache import regional_library_cache
        regional_library_cache.clear()
        logger.info("Regional library refresh complete: %d species", len(new_rows))

    except Exception as e:
        logger.error("Regional library refresh error: %s", e, exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()



@router.get("/comments/recent")
def get_recent_comments(limit: int = 10, db: Session = Depends(get_db), user=Depends(_current_user)):
    """Get the most recent comments across all bird profiles and recordings.
    Excludes comments attached to a recording that's gone — either
    soft-deleted OR hard-deleted (row no longer exists at all). The
    previous version of this filter only checked
    `Recording.deleted_at.is_(None)`, which is true both for "recording
    exists and isn't soft-deleted" AND for "no matching Recording row at
    all" — an outer join produces NULL for every Recording column in the
    second case, and `NULL IS NULL` is true in SQL, so a comment pointing
    at a genuinely hard-deleted recording slipped straight through a
    filter that was specifically written to catch exactly this. Now also
    requires `Recording.id.isnot(None)` — real proof a matching row was
    actually found — so only that case is excluded, not confused with
    comments on a bird_profile_id (recording_id IS NULL), which are
    unaffected since profiles don't have the same soft-delete concept."""
    from ..models import Comment as _Comment
    comments = (
        db.query(_Comment)
        .outerjoin(Recording, _Comment.recording_id == Recording.id)
        .filter(_Comment.deleted_at.is_(None))
        .filter(or_(
            _Comment.recording_id.is_(None),
            and_(Recording.id.isnot(None), Recording.deleted_at.is_(None)),
        ))
        .order_by(_Comment.created_at.desc())
        .limit(min(limit, 500))
        .all()
    )
    # Batch-load all referenced bird profiles in a single query (eliminates N+1)
    bird_ids = {c.bird_profile_id for c in comments if c.bird_profile_id}
    bp_map: dict = {}
    if bird_ids:
        bp_map = {
            bp.id: bp
            for bp in db.query(BirdProfile).filter(BirdProfile.id.in_(bird_ids)).all()
        }
    result = []
    hidden = _mod.blocked_authors(db, user)
    for c in comments:
        if c.author in hidden:
            continue
        item = _comment_out(c)
        if c.bird_profile_id:
            bp = bp_map.get(c.bird_profile_id)
            item["context_type"] = "bird"
            item["context_id"]   = c.bird_profile_id
            item["context_name"] = bp.common_name if bp else "Unknown"
            item["context_url"]  = f"/library/{c.bird_profile_id}"
        elif c.recording_id:
            item["context_type"] = "recording"
            item["context_id"]   = c.recording_id
            item["context_name"] = "Recording"
            item["context_url"]  = f"/recordings/{c.recording_id}"
        result.append(item)
    return result


@router.get("/{profile_id}", response_model=BirdProfileOut)
def get_bird_profile(
    profile_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Get a bird profile. Enrichment is triggered separately via POST /enrich."""
    profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Bird profile not found")

    # Lazy-generate the AI presence summary on first view — only if the
    # feature is enabled, nothing has been generated yet, no prior
    # attempt already failed (that condition matters: without it, a
    # species with a persistently-failing generation would retry on
    # every single page view, which is both wasteful and, for a paid
    # API, a real recurring cost for something that's already known not
    # to work), AND no generation is already in flight for this exact
    # profile — this last check is the real fix for a confirmed bug:
    # without it, repeated GETs to this same endpoint while the first
    # background task is still running (which the frontend's own
    # polling loop does, precisely while waiting for that first task to
    # finish) each independently see summary=None/error=None and queue
    # ANOTHER duplicate generation, multiplying real LLM calls per page
    # view and, with a slow local provider, potentially slowing every
    # copy down enough that none finish before the frontend gives up
    # polling. A manual regenerate button is the way to retry after a
    # genuine fix (a corrected API key, etc.).
    from ..services.ai_providers import get_feature_config
    if (
        profile.ai_presence_summary is None
        and profile.ai_presence_summary_error is None
        and profile_id not in _summary_generating_now
        and get_feature_config("profile_summary", db) is not None
    ):
        background_tasks.add_task(_generate_profile_summary_bg, profile_id)

    return profile_to_out(profile, db)


def _generate_profile_summary_bg(profile_id: str) -> None:
    """
    Background-task wrapper: opens its OWN fresh DB session rather than
    reusing the request's — Depends(get_db)'s session gets closed in a
    finally block right after the endpoint function returns, which can
    happen before or race with a background task actually running (background
    tasks execute after the response is sent, not necessarily after the
    request's own session cleanup completes). Reusing that session here
    would risk operating on an already-closed connection.

    Also the actual in-flight guard, not just the scheduling-time check
    above — a defensive second layer in case two requests' scheduling
    checks both pass in the same instant before either has added to
    _summary_generating_now (a real, if narrow, race the scheduling
    check alone can't fully close).
    """
    if profile_id in _summary_generating_now:
        return
    _summary_generating_now.add(profile_id)
    try:
        from ..database import SessionLocal
        from ..models import BirdProfile
        with SessionLocal() as db:
            profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
            if profile is None:
                return
            from ..services.profile_summary import generate_profile_summary
            generate_profile_summary(db, profile)
    finally:
        _summary_generating_now.discard(profile_id)


@router.post("/{profile_id}/presence-summary/regenerate")
def regenerate_profile_summary(profile_id: str, db: Session = Depends(get_db)):
    """
    Manual regenerate — the escape hatch alongside the lazy first-view
    generation. Same in-flight guard as that lazy path: if a background
    generation is already running for this profile (e.g. the page just
    loaded and the lazy trigger already kicked one off), don't start a
    second, redundant one — just return the current state.
    """
    profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Bird profile not found")
    if profile_id in _summary_generating_now:
        return profile_to_out(profile, db)
    _summary_generating_now.add(profile_id)
    try:
        from ..services.profile_summary import generate_profile_summary
        generate_profile_summary(db, profile)
    finally:
        _summary_generating_now.discard(profile_id)
    return profile_to_out(profile, db)



# In-process progress tracking for the bulk "Refresh All Data" run, polled by
# the Settings UI for a real progress bar. Same pattern as the existing
# _enriching_now set in bird_enricher.py: a plain module-level dict, safe for
# this single-process deployment (NullPool/SQLite already assumes one
# process). Holds at most one run's state at a time — a second click while
# a run is active is rejected by enrich_all_bird_profiles() below rather
# than starting a second overlapping thread against the same rows.
_bulk_enrich_status: Dict[str, object] = {
    "running": False,
    "total": 0,
    "done": 0,
    "current_name": None,
    "started_at": None,
    "finished_at": None,
    "errors": 0,
}


# In-process progress tracking for the bulk "Refresh All Data" / "Refresh
# Range Maps Only" runs, polled by the Settings UI for a real progress bar.
# Same pattern as the existing _enriching_now set in bird_enricher.py: a
# plain module-level dict, safe for this single-process deployment
# (NullPool/SQLite already assumes one process). Holds at most one run's
# state at a time, regardless of which mode — a second click of EITHER
# button while either kind of run is active is rejected below rather than
# starting a second overlapping thread against the same rows.
_bulk_enrich_status: Dict[str, object] = {
    "running": False,
    "mode": None,          # "full" | "maps_only"
    "total": 0,
    "done": 0,
    "current_name": None,
    "started_at": None,
    "finished_at": None,
    "errors": 0,
}


@router.get("/enrich-all/status")
def enrich_all_status():
    """Poll target for the Settings bulk-refresh progress bar (both modes)."""
    return dict(_bulk_enrich_status)


def _run_bulk_enrich(db: Session, mode: str) -> int:
    """
    Shared implementation for both POST /enrich-all and
    POST /enrich-all/maps-only — same iteration and progress-tracking
    machinery, only the enrich_profile() call differs by mode.
    Raises HTTPException(409) if a run of either mode is already active.
    """
    import threading as _threading
    from ..services.bird_enricher import BirdEnricher
    from ..models import RegionalSpecies

    if _bulk_enrich_status["running"]:
        raise HTTPException(
            status_code=409,
            detail="A bulk refresh is already running — poll /enrich-all/status for progress.",
        )

    regional_names = {r.common_name for r in db.query(RegionalSpecies).all()}
    profile_names  = {p.common_name for p in db.query(BirdProfile).all()}
    all_names = regional_names | profile_names
    total = len(all_names)
    logger.info("enrich-all (%s): %d unique birds to process (%d regional, %d existing profiles)",
                mode, total, len(regional_names), len(profile_names))

    _bulk_enrich_status.update({
        "running": True,
        "mode": mode,
        "total": total,
        "done": 0,
        "current_name": None,
        "started_at": datetime.utcnow().isoformat(),
        "finished_at": None,
        "errors": 0,
    })

    def run_all():
        from ..database import SessionLocal as _SL
        sub_db = _SL()
        try:
            enricher = BirdEnricher(sub_db)
            for name in sorted(all_names):
                _bulk_enrich_status["current_name"] = name
                try:
                    profile = sub_db.query(BirdProfile).filter(
                        BirdProfile.common_name == name).first()
                    if not profile:
                        # _create_profile expects a BirdNET label (common_name format)
                        profile = enricher._create_profile(name)
                    if profile:
                        if mode == "maps_only":
                            enricher.enrich_profile(profile, maps_only=True)
                        else:
                            enricher.enrich_profile(profile, force=True)
                except Exception as e:
                    logger.warning("Bulk enrich error (%s) for %s: %s", mode, name, e)
                    _bulk_enrich_status["errors"] += 1
                finally:
                    _bulk_enrich_status["done"] += 1
        finally:
            sub_db.close()
            _bulk_enrich_status["running"] = False
            _bulk_enrich_status["current_name"] = None
            _bulk_enrich_status["finished_at"] = datetime.utcnow().isoformat()

    t = _threading.Thread(target=run_all, daemon=True)
    t.start()
    return total


@router.post("/enrich-all")
def enrich_all_bird_profiles(db: Session = Depends(get_db)):
    """
    Ensure profiles exist for ALL RegionalSpecies, then enrich every profile.
    This covers both detected birds (BirdProfile) and undetected library birds.
    """
    total = _run_bulk_enrich(db, mode="full")
    return {"status": "started", "count": total}


@router.post("/enrich-all/maps-only")
def enrich_all_range_maps_only(db: Session = Depends(get_db)):
    """
    Like /enrich-all, but only refreshes range maps (every enabled source:
    AAB, Macaulay, Wikipedia SVG, BirdLife, iNat Geomodel, eBird S&T, GBIF)
    instead of re-fetching Wikipedia descriptions, iNat photos/sounds, and
    seasonal frequency data too. Much faster per bird since it skips most
    of the slow network calls — intended for "I just want fresher maps."
    """
    total = _run_bulk_enrich(db, mode="maps_only")
    return {"status": "started", "count": total}




@router.get("/{profile_id}/range-map/status")
def range_map_status(profile_id: str, db: Session = Depends(get_db)):
    """Return current range_map_url and range_map_source for polling."""
    profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {
        "id":               profile_id,
        "range_map_url":    profile.range_map_url,
        "range_map_source": getattr(profile, "range_map_source", None),
    }


@router.post("/{profile_id}/range-map/reset")
def reset_range_map_to_wikipedia(
    profile_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Clear any cached GBIF/eBird S&T range map and re-enrich from Wikipedia/enrichment pipeline.
    This restores the default Wikipedia SVG (or best available auto-detected source).

    Requires range_maps_enabled = True in Settings.
    """
    if not _range_maps_enabled(db):
        raise HTTPException(
            status_code=403,
            detail="Range maps are disabled. Enable them in Settings → Experimental Features.",
        )
    profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    # Remove the custom PNG, clear source flag, reset enrichment so the
    # auto-enrichment pipeline will find and restore the Wikipedia SVG URL.
    import os as _os
    for suffix in ("_gbif.png", "_ebird_st.png"):
        if profile.range_map_url and suffix in (profile.range_map_url or ""):
            old_path = profile.range_map_url.replace("file://", "")
            try:
                if _os.path.exists(old_path):
                    _os.remove(old_path)
            except OSError:
                pass
    profile.range_map_url    = None
    profile.range_map_source = None
    profile.enrichment_complete = False
    db.commit()
    # Run enrichment in background to immediately restore the Wikipedia map
    background_tasks.add_task(_enrich_profile, profile_id, force=True)
    return {"status": "reset", "id": profile_id}


@router.post("/{profile_id}/range-map/fetch")
def fetch_range_map_from_source(
    profile_id: str,
    source: str,   # "ebird_st" | "gbif"
    background_tasks: BackgroundTasks,
    force: bool = False,
    db: Session = Depends(get_db),
):
    """
    Fetch and render a range map from a specific data source, saving it
    to the local media directory and updating the profile.
    The download runs in the background; poll GET /api/v1/birds/{id}
    until range_map_source matches the requested source.

    Pass ?force=true to actually re-fetch/re-render even if a cached file
    for this source already exists (used by the explicit refresh button).
    Without force, if a cached file already exists for this exact source,
    this returns immediately without queuing any background work — this
    endpoint previously never checked for an existing file at all, so
    every tab click or page reload triggered a full from-scratch
    Playwright/GeoTIFF re-render even when the file had just been fetched.

    Requires range_maps_enabled = True in Settings.
    """
    if not _range_maps_enabled(db):
        raise HTTPException(
            status_code=403,
            detail="Range maps are disabled. Enable them in Settings → Range Maps (experimental)."
        )
    if source not in ("ebird_st", "gbif"):
        raise HTTPException(status_code=400, detail=f"Unknown source: {source}")
    profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    if not force:
        import os as _os
        from ..config import settings as _cfg
        import re as _re
        safe = _re.sub(r"[^a-zA-Z0-9_-]", "_", profile.common_name.lower())
        cached_path = _os.path.join(_cfg.media_dir, safe, f"range_map_{source}.png")
        if _os.path.exists(cached_path) and _os.path.getsize(cached_path) > 1_000:
            logger.info("Range map fetch for %s (%s) skipped — cached file already exists "
                        "and force=false: %s", profile.common_name, source, cached_path)
            # If this source isn't the currently-displayed one, point the
            # profile at the cache that's already on disk instead of
            # silently doing nothing — this is the actual "switch tabs and
            # get the cached version instantly" behavior being asked for.
            if profile.range_map_source != source:
                profile.range_map_url = f"file://{cached_path}"
                profile.range_map_source = source
                db.commit()
            return {"status": "cached", "source": source, "id": profile_id}

    background_tasks.add_task(_fetch_range_map_bg, profile_id, source)
    return {"status": "queued", "source": source, "id": profile_id}



@router.get("/{profile_id}/comments")
def get_bird_comments(profile_id: str, db: Session = Depends(get_db), user=Depends(_current_user)):
    """Get all comments for a bird profile, newest first."""
    comments = (
        db.query(Comment)
        .filter(Comment.bird_profile_id == profile_id, Comment.deleted_at.is_(None))
        .order_by(Comment.created_at.desc())
        .all()
    )
    hidden = _mod.blocked_authors(db, user)
    return [_comment_out(c) for c in comments if c.author not in hidden]


@router.post("/{profile_id}/comments")
def post_bird_comment(profile_id: str, body: dict, db: Session = Depends(get_db), user=Depends(_current_user)):
    """Post a comment on a bird profile."""
    text = (body.get("body") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Comment body required")
    profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    c = Comment(
        bird_profile_id=profile_id,
        author=_mod.author_for(user, body),
        body=text,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _comment_out(c)


@router.delete("/{profile_id}/comments/{comment_id}")
def delete_bird_comment(profile_id: str, comment_id: str, db: Session = Depends(get_db), user=Depends(_current_user)):
    """Soft-delete a comment."""
    from datetime import datetime as _dt
    c = db.query(Comment).filter(
        Comment.id == comment_id, Comment.bird_profile_id == profile_id
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Comment not found")
    if not _mod.may_change(c, user):
        raise HTTPException(status_code=403, detail="Only the author or an admin can change this note")
    c.deleted_at = _dt.utcnow()
    db.commit()
    return {"ok": True}


@router.put("/{profile_id}/comments/{comment_id}")
def update_bird_comment(profile_id: str, comment_id: str, body: dict, db: Session = Depends(get_db), user=Depends(_current_user)):
    """Edit a comment body."""
    from datetime import datetime as _dt
    c = db.query(Comment).filter(
        Comment.id == comment_id, Comment.bird_profile_id == profile_id,
        Comment.deleted_at.is_(None)
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Comment not found")
    if not _mod.may_change(c, user):
        raise HTTPException(status_code=403, detail="Only the author or an admin can change this note")
    new_body = (body.get("body") or "").strip()
    if not new_body:
        raise HTTPException(status_code=400, detail="Body cannot be empty")
    c.body = new_body
    c.updated_at = _dt.utcnow()
    db.commit()
    return _comment_out(c)


def _comment_out(c: Comment) -> dict:
    return {
        "id": c.id,
        "author": c.author,
        "body": c.body,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@router.post("/{profile_id}/enrich")
def trigger_enrichment(profile_id: str, background_tasks: BackgroundTasks,
                        db: Session = Depends(get_db)):
    """Manually trigger re-enrichment of a bird profile."""
    profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Bird profile not found")
    # Reset flag immediately so the frontend can poll for completion:
    # enrichment_complete=False → "in progress", True → "done"
    profile.enrichment_complete = False
    profile.last_enriched = None
    db.add(profile)
    db.commit()
    background_tasks.add_task(_enrich_profile, profile_id, force=True)
    return {"status": "enrichment_queued", "id": profile_id}



@router.get("/{profile_id}/range-map-debug")
def debug_range_map(profile_id: str, db: Session = Depends(get_db)):
    """Debug: shows color extraction for a bird SVG range map."""
    import os as _os, colorsys as _cs
    profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    result = {
        "bird": profile.common_name,
        "range_map_url": profile.range_map_url,
        "enrichment_complete": profile.enrichment_complete,
    }

    if not profile.range_map_url or not profile.range_map_url.startswith("file://"):
        result["status"] = "no_local_svg"
        return result

    path = profile.range_map_url[7:]
    if not _os.path.exists(path):
        result["status"] = "file_missing"
        return result

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()

    # Parse viewBox safely using double-quote pattern then single-quote fallback
    vb_dq = re.search(r'viewBox="([^"]+)"', raw)
    vb_sq = re.search(r"viewBox='([^']+)'", raw)
    vb_val = (vb_dq or vb_sq)
    if vb_val:
        result["viewbox_raw"] = vb_val.group(1)
        parts = vb_val.group(1).split()
        if len(parts) == 4:
            result["viewbox"] = {"x0": parts[0], "y0": parts[1], "w": parts[2], "h": parts[3]}
            try:
                result["aspect_ratio"] = f"{float(parts[2]):.1f} / {float(parts[3]):.1f}"
            except ValueError:
                pass

    tag_m = re.search(r"<svg[^>]*>", raw, re.DOTALL)
    if tag_m:
        tag = tag_m.group(0)
        result["svg_tag_has_width"] = "width=" in tag
        result["svg_tag_has_height"] = "height=" in tag

    all_fills = [_normalize_color(c) for c in re.findall(r'fill="#([0-9a-fA-F]{3,6})"', raw)]
    all_fills += [_normalize_color("#" + c) for c in re.findall(r"fill='#([0-9a-fA-F]{3,6})'", raw)]
    IGNORE = {"#f8fafc","#ffffff","#fff","#f0f0f0","#eeeeee","#cccccc","#e8e8e8","#d9d9d9",
              "#000000","#000","#0a0f14","#333333","#aaaaaa","#999999","#888888","#777777",
              "#666666","#555555","#c8c8c8","#b0b0b0","#d3d3d3","#c0c0c0","#e0e0e0","#f5f5f5",
              "#808080","#a0a0a0"}

    color_analysis = []
    for c in sorted(set(all_fills)):
        info = {"hex": c, "in_ignore": c in IGNORE}
        try:
            r = int(c[1:3], 16) / 255
            g = int(c[3:5], 16) / 255
            b = int(c[5:7], 16) / 255
            h, s, v = _cs.rgb_to_hsv(r, g, b)
            lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
            info.update({"lum": round(lum, 3), "sat": round(s, 3), "hue_deg": round(h * 360, 1)})
            kept = (c not in IGNORE) and (lum <= 0.78) and (lum >= 0.04) and (s >= 0.18)
            info["kept"] = kept
            if kept:
                info["matched_label"] = _closest_wiki_label(c)
        except Exception as e:
            info["error"] = str(e)
        color_analysis.append(info)

    result["colors"] = color_analysis
    result["kept_count"] = sum(1 for i in color_analysis if i.get("kept"))
    result["status"] = "ok"
    return result


@router.get("/{profile_id}/photo")
def get_bird_photo(profile_id: str, db: Session = Depends(get_db)):
    """Serve the downloaded bird photo."""
    profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not profile or not profile.photo_path or not os.path.exists(profile.photo_path):
        raise HTTPException(status_code=404, detail="Photo not available")
    ext = os.path.splitext(profile.photo_path)[1].lower()
    media_type = {"jpg": "image/jpeg", ".jpg": "image/jpeg",
                  ".jpeg": "image/jpeg", ".png": "image/png",
                  ".webp": "image/webp"}.get(ext, "image/jpeg")
    # Reported directly: pages accessed through a Cloudflare tunnel were
    # noticeably slower than on the LAN — every hop through a tunnel adds
    # round-trip latency that a fast local network hides, so the
    # NUMBER of round trips matters far more remotely than it does at
    # home. This endpoint is the single most-requested one in the whole
    # app (every bird photo on Dashboard, Life List, Field Guide, and
    # every profile page all come through here, often dozens per page)
    # and had NO Cache-Control at all — every other photo/image endpoint
    # in this file already sets one (86400s is this file's own established
    # convention for a downloaded photo that could occasionally be
    # re-enriched, e.g. the range map / heatmap endpoints just above).
    # Missing it here meant browsers fell back to weak heuristic caching,
    # and Cloudflare itself has nothing to key an edge cache on for an
    # /api/ path without an explicit header — so this was round-tripping
    # to the origin on every single load, for every bird shown.
    return FileResponse(profile.photo_path, media_type=media_type,
                         headers={"Cache-Control": "public, max-age=86400"})


# ── User-submitted photos (with optional AI species confirmation) ────────────

ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_PHOTO_BYTES = 8 * 1024 * 1024  # 8MB


def _photo_out(p: BirdPhoto) -> dict:
    return {
        "id": p.id,
        "bird_profile_id": p.bird_profile_id,
        "url": f"/api/v1/birds/photos/{p.id}/file",
        "uploaded_by": p.uploaded_by,
        "uploaded_at": p.uploaded_at.isoformat() if p.uploaded_at else None,
        "ai_checked": p.ai_checked,
        "ai_match": p.ai_match,
        "ai_guess": p.ai_guess,
        "ai_note": p.ai_note,
    }


@router.get("/{profile_id}/photos")
def list_bird_photos(profile_id: str, db: Session = Depends(get_db)):
    """List user-submitted photos for a bird profile (newest first)."""
    profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Bird profile not found")
    photos = (
        db.query(BirdPhoto)
        .filter(BirdPhoto.bird_profile_id == profile_id)
        .order_by(BirdPhoto.uploaded_at.desc())
        .all()
    )
    return [_photo_out(p) for p in photos]


@router.post("/{profile_id}/photos")
async def upload_bird_photo(
    profile_id: str,
    file: UploadFile = File(...),
    uploaded_by: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Upload a user-submitted photo to a bird profile. If an Anthropic API key
    is configured in Settings, the photo is also checked against the
    profile's species as a sanity-check confirmation — this is optional and
    upload succeeds either way; ai_checked=false just means no key was set
    or the check itself failed (network error, bad key, etc.), not that the
    photo was rejected.
    """
    profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Bird profile not found")

    content_type = file.content_type or ""
    if content_type not in ALLOWED_PHOTO_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type '{content_type}'. Use JPEG, PNG, WebP, or GIF.",
        )

    data = await file.read()
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=400, detail="Photo exceeds 8MB limit")
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    photos_dir = os.path.join(settings.media_dir, "birds",
                               profile.common_name.replace(" ", "_"), "user_photos")
    os.makedirs(photos_dir, exist_ok=True)

    photo_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename or "")[1].lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        ext = ".jpg"
    file_path = os.path.join(photos_dir, f"{photo_id}{ext}")
    with open(file_path, "wb") as f:
        f.write(data)

    photo = BirdPhoto(
        id=photo_id,
        bird_profile_id=profile_id,
        file_path=file_path,
        uploaded_by=uploaded_by,
    )

    # Optional AI species confirmation — never blocks the upload on failure
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    api_key = (s.anthropic_api_key if s else None) or ""
    if api_key:
        try:
            from ..services.photo_id import identify_species_from_photo
            checked, match, guess, note = identify_species_from_photo(
                data, file.filename or "photo.jpg", profile.common_name, api_key, db=db,
            )
            photo.ai_checked = checked
            photo.ai_match = match
            photo.ai_guess = guess
            photo.ai_note = note
        except Exception as e:
            logger.warning("Photo AI confirmation error for %s: %s", profile.common_name, e)

    db.add(photo)
    db.commit()
    return _photo_out(photo)


@router.get("/photos/{photo_id}/file")
def get_bird_photo_file(photo_id: str, db: Session = Depends(get_db)):
    """Serve a user-uploaded photo file."""
    photo = db.query(BirdPhoto).filter(BirdPhoto.id == photo_id).first()
    if not photo or not os.path.exists(photo.file_path):
        raise HTTPException(status_code=404, detail="Photo not found")
    ext = os.path.splitext(photo.file_path)[1].lower()
    media_type = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                  ".png": "image/png", ".webp": "image/webp",
                  ".gif": "image/gif"}.get(ext, "image/jpeg")
    # Also had no Cache-Control at all (see get_bird_photo's own comment
    # above for the full reasoning). This one can be cached even more
    # aggressively than a profile's photo — photo_id is a stable,
    # never-reused key pointing at one specific uploaded file that never
    # changes in place, the same "immutable content at a stable URL"
    # shape recordings.py's own clip/spectrogram endpoints already use
    # their 30-day immutable header for.
    return FileResponse(photo.file_path, media_type=media_type,
                         headers={"Cache-Control": "public, max-age=2592000, immutable"})


@router.delete("/photos/{photo_id}")
def delete_bird_photo(photo_id: str, db: Session = Depends(get_db)):
    """Delete a user-submitted photo."""
    photo = db.query(BirdPhoto).filter(BirdPhoto.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    try:
        if os.path.exists(photo.file_path):
            os.remove(photo.file_path)
    except OSError as e:
        logger.warning("Could not delete photo file %s: %s", photo.file_path, e)
    db.delete(photo)
    db.commit()
    return {"status": "deleted"}


@router.get("/{profile_id}/range-map")
def get_range_map(profile_id: str, refresh: bool = False, source: Optional[str] = None,
                   db: Session = Depends(get_db)):
    """
    Serve a locally-cached range map image.
    Sources (in priority order):
    1. Cached Wikipedia Commons range map (already fetched by enricher)
    2. eBird Status & Trends abundance map (seasonal, Merlin-style)
    3. iNaturalist taxon range map

    Pass ?refresh=true to force a fresh AAB re-capture (URL + legend)
    before serving, rather than serving whatever's cached from the last
    enrichment pass. Previously only the BirdLife tab had a refresh
    control — AAB had no on-demand way to re-capture without re-running
    full enrichment for the whole profile.

    Pass ?source=aab to assert that the caller specifically wants an AAB/
    Macaulay/Wikipedia-sourced image, NOT eBird S&T or GBIF — this is the
    AAB tab's own dedicated endpoint, served via this same generic handler
    (the "aab" tab in the frontend shows whatever range_map_url resolved
    to, which may be AAB, Macaulay, or Wikipedia depending on which source
    succeeded during enrichment). Without this check, once the separate
    eBird S&T tab successfully populated range_map_url/range_map_source
    (which it does independently of this endpoint, via its own background
    fetch), switching back to the AAB tab would keep serving that same
    S&T-sourced image — the endpoint had no way to know a different tab's
    request expected a structurally different source. When the cached
    source doesn't match, this re-resolves exactly as if refresh=true had
    been passed, rather than silently serving the wrong source's image.
    """
    from fastapi.responses import Response, RedirectResponse
    import httpx as _httpx
    import os

    profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # If the AAB or Macaulay tab is asking but the cache is actually
    # eBird S&T or GBIF sourced (populated independently by the S&T tab's
    # own fetch flow), force the same re-resolution path refresh=true
    # already uses — this is the actual fix for the AAB tab showing the
    # S&T map after visiting that tab first, now also covering the
    # Macaulay tab for the same reason (both want the AAB/Macaulay/
    # Wikipedia family of sources specifically, not S&T/GBIF).
    if source in ("aab", "macaulay") and profile.range_map_source in ("ebird_st", "gbif"):
        logger.info("%s tab requested but cache is %s-sourced for %s — forcing re-resolution",
                    source, profile.range_map_source, profile.common_name)
        refresh = True

    if refresh and source == "macaulay":
        # Macaulay refresh is a simple Cornell CDN lookup keyed by eBird
        # species code — no Playwright session involved, unlike AAB.
        if profile.ebird_species_code:
            from ..services.bird_enricher import BirdEnricher
            enricher = BirdEnricher.__new__(BirdEnricher)
            try:
                ml_url = enricher._fetch_ml_range_map(profile.ebird_species_code)
            except Exception as e:
                ml_url = None
                logger.warning("Macaulay refresh failed for %s: %s", profile.common_name, e)
            if ml_url:
                local = enricher._download_range_map(ml_url, profile.common_name)
                if local:
                    profile.range_map_url = f"file://{local}"
                    profile.range_map_source = "macaulay"
                    profile.range_maps_prefetched_at = datetime.utcnow()
                    db.commit()
                    db.refresh(profile)
                    logger.info("Macaulay range map manually refreshed for %s", profile.common_name)
                else:
                    logger.warning("Macaulay refresh for %s got a URL but download failed", profile.common_name)
            else:
                logger.info("Macaulay refresh for %s found nothing — serving existing cache", profile.common_name)
        else:
            logger.info("Macaulay refresh for %s skipped — no eBird species code on file", profile.common_name)

        if profile.range_map_source in ("ebird_st", "gbif"):
            # Same dead-end handling as the AAB branch below: don't serve
            # the wrong source under this tab, try Wikipedia, then a
            # clean 404 if even that fails.
            try:
                wiki_url = enricher._fetch_wikipedia_range_map(profile.common_name, profile.scientific_name or "")
            except Exception:
                wiki_url = None
            if wiki_url:
                profile.range_map_url = wiki_url
                profile.range_map_source = "wikipedia"
                db.commit()
                logger.info("Macaulay tab fallback (Wikimedia): %s → %s", profile.common_name, wiki_url[:80])
                return RedirectResponse(url=wiki_url, status_code=302)
            raise HTTPException(status_code=404,
                                detail=f"No Macaulay or Wikipedia range map available for {profile.common_name}.")

    if refresh and source != "macaulay":
        from ..services.bird_enricher import refetch_aab_range_map_standalone
        try:
            result = refetch_aab_range_map_standalone(profile.common_name)
        except Exception as e:
            logger.warning("AAB refresh failed for %s: %s", profile.common_name, e)
            result = {"ok": False, "url": None, "legend": None}

        if result.get("ok") and result.get("url"):
            from ..services.bird_enricher import BirdEnricher
            enricher = BirdEnricher.__new__(BirdEnricher)
            local = enricher._download_range_map(result["url"], profile.common_name)
            if local:
                profile.range_map_url = f"file://{local}"
                profile.range_map_source = "aab"
                if result.get("legend"):
                    profile.aab_legend = result["legend"]
                profile.range_maps_prefetched_at = datetime.utcnow()
                db.commit()
                db.refresh(profile)
                logger.info("AAB range map manually refreshed for %s", profile.common_name)
            else:
                logger.warning("AAB refresh for %s got a URL but download failed", profile.common_name)
        else:
            logger.info("AAB refresh for %s found nothing new — serving existing cache", profile.common_name)

        # If the cache is STILL ebird_st/gbif sourced after the refresh
        # attempt above (the AAB re-fetch genuinely failed to find
        # anything), do not serve that stale, wrong-source file under the
        # AAB tab. The original version of this fix set range_map_url to
        # None here, which was a real regression: it prevented execution
        # from ever reaching the dead-URL-fallback logic further down in
        # this function (which tries a fresh Wikipedia lookup) — that
        # logic is only reached via the non-empty-url proxy path, so an
        # emptied url hit an early 404 instead, even in cases where a
        # fresh Wikipedia map was findable and would have worked, exactly
        # as it had on a PRIOR request for the same species before the
        # S&T tab was visited and overwrote range_map_source again.
        # Go straight to the same fresh-Wikipedia-lookup fallback the dead-
        # URL case already uses, rather than re-deriving a separate path.
        if source == "aab" and profile.range_map_source in ("ebird_st", "gbif"):
            logger.warning("AAB refresh for %s did not produce an AAB-sourced result "
                           "(cache is %s-sourced) — trying a fresh Wikipedia map instead "
                           "of serving the wrong source under the AAB tab",
                           profile.common_name, profile.range_map_source)
            try:
                from ..services.bird_enricher import BirdEnricher
                enricher = BirdEnricher.__new__(BirdEnricher)
                wiki_url = enricher._fetch_wikipedia_range_map(profile.common_name, profile.scientific_name or "")
            except Exception as e:
                wiki_url = None
                logger.debug("Wikipedia fallback lookup failed for %s: %s", profile.common_name, e)

            if wiki_url:
                profile.range_map_url = wiki_url
                profile.range_map_source = "wikipedia"
                db.commit()
                logger.info("AAB tab fallback (Wikimedia): %s → %s", profile.common_name, wiki_url[:80])
                return RedirectResponse(url=wiki_url, status_code=302)

            # No Wikipedia fallback found either — this is a genuine dead
            # end for the AAB tab specifically, but say so plainly rather
            # than silently showing the wrong source.
            raise HTTPException(status_code=404,
                                detail=f"No AAB or Wikipedia range map available for "
                                       f"{profile.common_name}. The cached map is from a "
                                       f"different source (eBird S&T) and can't be shown "
                                       f"under the AAB tab.")

    # Handle locally-saved range map files (file:// protocol)
    if profile.range_map_url and profile.range_map_url.startswith("file://"):
        local_path = profile.range_map_url[7:]
        if os.path.exists(local_path) and os.path.getsize(local_path) > 500:
            ext = os.path.splitext(local_path)[1].lower()
            if ext == ".svg":
                # .svg is itself a reliable signal this is Wikipedia-sourced —
                # AAB and Macaulay only ever produce raster PNG/JPG in this
                # codebase. Defensively sync range_map_source here too, in
                # case it's stale from an enrichment pass that predates this
                # field being tracked correctly (see the redirect path below
                # for the full explanation of why staleness here breaks the
                # legend endpoint).
                if profile.range_map_source != "wikipedia":
                    profile.range_map_source = "wikipedia"
                    db.commit()
                # Serve SVG with injected dark background so it renders well in dark UI
                try:
                    svg_content = open(local_path, "r", encoding="utf-8").read()

                    # Get original viewBox for aspect ratio (no cropping — path
                    # coordinates are relative so bbox math is unreliable)
                    # Strip any fixed px dimensions so CSS can control sizing.
                    # Do NOT inject width="100%" height="100%" — browsers treat that as
                    # a 300×150 intrinsic SVG, producing wrong aspect ratios in <img> tags.
                    # Instead use explicit pixel dimensions derived from the viewBox so the
                    # browser always has a reliable intrinsic size.
                    svg_content = re.sub(r'(<svg[^>]*?)\s+width="[0-9][^"]*"', r'\1', svg_content, count=1)
                    svg_content = re.sub(r'(<svg[^>]*?)\s+height="[0-9][^"]*"', r'\1', svg_content, count=1)
                    svg_content = re.sub(r'(<svg[^>]*?)\s+style="[^"]*"', r'\1', svg_content, count=1)

                    # Adjust viewBox to crop blank space at the top of world maps.
                    # Wikipedia range SVGs span the full globe; most North American bird
                    # ranges are in the lower 78%. Cropping the top 22% removes empty
                    # Arctic/ocean and keeps the visible area focused on the range.
                    vb_raw = re.search(r'viewBox="([^"]+)"', svg_content)
                    if vb_raw:
                        vb_parts = vb_raw.group(1).split()
                        if len(vb_parts) == 4:
                            try:
                                vx, vy, vw, vh = (float(p) for p in vb_parts)
                                ar = vw / vh if vh > 0 else 1
                                if ar > 1.15:  # wide world / continental map
                                    crop_frac = 0.22 if ar < 2.0 else 0.12
                                    crop_px = vh * crop_frac
                                    new_vb = f'{vx:.1f} {vy + crop_px:.1f} {vw:.1f} {vh - crop_px:.1f}'
                                    svg_content = svg_content.replace(
                                        vb_raw.group(0), f'viewBox="{new_vb}"'
                                    )
                            except ValueError:
                                pass

                    # Don't set explicit dimensions. With viewBox present and no
                    # width/height, browsers correctly derive intrinsic dimensions from
                    # viewBox in <img> tags. Set preserveAspectRatio so content is
                    # centered and fully visible (meet = scale to fit, never crop).
                    svg_content = re.sub(
                        r'(<svg)\b',
                        r'\1 preserveAspectRatio="xMidYMid meet"',
                        svg_content, count=1
                    )

                    from fastapi.responses import Response as _Resp
                    return _Resp(
                        content=svg_content.encode("utf-8"),
                        media_type="image/svg+xml",
                        headers={
                            # no-cache: always re-validate; fixes stale browsers after code changes
                            "Cache-Control": "no-cache",
                            "X-Content-Type-Options": "nosniff",
                        }
                    )
                except Exception as _e:
                    logger.debug("SVG serve error: %s", _e)
                    pass
            return FileResponse(local_path, media_type="image/png",
                                headers={"Cache-Control": "public, max-age=86400"})

    # Try to get a URL to fetch: prefer Wikipedia Commons, then eBird S&T
    url = profile.range_map_url

    # No fallback URLs that work reliably from server-side:
    # - iNat range.png → 403 Forbidden from Docker
    # - eBird v1/asset/{code} → needs numeric ID not species code
    # Wikipedia Commons SVGs are set during enrichment and served correctly

    if not url:
        logger.warning("No range map URL for profile %s (%s)", profile_id, profile.common_name)
        raise HTTPException(status_code=404, detail="No range map available")

    # Check for locally cached copy
    from ..config import settings as cfg
    cache_dir = os.path.join(cfg.media_dir, "range_maps")
    os.makedirs(cache_dir, exist_ok=True)
    ext = ".png" if ".png" in url else ".jpg" if ".jpg" in url else ".svg"
    cache_path = os.path.join(cache_dir, f"{profile_id}{ext}")

    logger.info("Range map fetch: %s → %s (cached: %s)",
                profile.common_name, url[:80], os.path.exists(cache_path))

    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            data = f.read()
        # Only serve cache if it has actual content (>500 bytes)
        if len(data) > 500:
            ct = "image/svg+xml" if ext == ".svg" else f"image/{ext[1:]}"
            return Response(content=data, media_type=ct,
                            headers={"Cache-Control": "public, max-age=86400"})
        else:
            logger.warning("Cached range map too small (%d bytes), re-fetching", len(data))

    # For Wikipedia/Wikimedia URLs: redirect directly to the browser
    # (Wikimedia blocks server-side fetches but browsers can access freely)
    # For other URLs: try to proxy and cache
    is_wiki = any(d in url for d in ['wikimedia.org', 'wikipedia.org', 'upload.wikimedia'])

    # Keep range_map_source in sync with what's actually being served here.
    # This redirect/proxy path is a separate, older code path from
    # _resolve_range_map() in bird_enricher.py — it never touched
    # range_map_source at all, so a profile could end up with
    # range_map_url pointing at Wikipedia (e.g. after an AAB refresh's
    # download failed and this function fell through to the existing
    # Wikipedia URL) while range_map_source was still stale from an
    # earlier, now-broken AAB capture. The legend endpoint trusts
    # range_map_source to decide whether to serve the Wikipedia SVG
    # legend or the AAB one — a stale "aab" value there meant it kept
    # serving (empty) AAB legend data for a map that was actually
    # Wikipedia, producing the all-grey legend dots.
    if is_wiki and profile.range_map_source != "wikipedia":
        profile.range_map_source = "wikipedia"
        db.commit()

    if is_wiki:
        logger.info("Range map redirect (Wikimedia): %s → %s", profile.common_name, url[:80])
        return RedirectResponse(url=url, status_code=302)
    
    # Non-Wikimedia: try to proxy and cache
    try:
        r = _httpx.get(url, timeout=20, follow_redirects=True,
                       headers={"User-Agent": "Chirp-BirdDetection/1.0",
                                "Accept": "image/png,image/jpeg,image/svg+xml,image/*"})
        if r.status_code == 200 and len(r.content) > 500:
            ct = r.headers.get("content-type", "image/png").split(";")[0].strip()
            actual_ext = ".svg" if "svg" in ct else ".png" if "png" in ct else ".jpg"
            actual_cache = os.path.join(cache_dir, f"{profile_id}{actual_ext}")
            with open(actual_cache, "wb") as f:
                f.write(r.content)
            logger.info("Range map cached for %s (%d bytes)", profile.common_name, len(r.content))
            return Response(content=r.content, media_type=ct,
                            headers={"Cache-Control": "public, max-age=86400"})
        logger.debug("Range map fetch failed for %s: status=%s", profile.common_name, r.status_code)
    except _httpx.RequestError as e:
        logger.debug("Range map request error for %s: %s", profile.common_name, e)

    # The stored URL is confirmed dead (proxy fetch above failed) — redirecting
    # the browser to it would just hit the same block (Cloudflare/hotlink
    # protection generally isn't bypassed by the browser making the request
    # instead of the server; a real production log confirmed this exact AAB
    # CDN URL 403ing repeatedly across multiple refresh attempts, with no
    # recovery since this function previously had no fallback for "the
    # already-cached URL itself stopped working"). Try a fresh Wikipedia
    # map instead of dead-ending — same fallback _resolve_range_map() uses
    # during normal enrichment — and persist it so future requests don't
    # keep hitting this same broken URL.
    logger.warning("Range map URL for %s is dead (non-Wikipedia, proxy fetch failed) — "
                    "falling back to Wikipedia", profile.common_name)
    try:
        from ..services.bird_enricher import BirdEnricher
        enricher = BirdEnricher.__new__(BirdEnricher)
        wiki_url = enricher._fetch_wikipedia_range_map(profile.common_name, profile.scientific_name or "")
    except Exception as e:
        wiki_url = None
        logger.debug("Wikipedia fallback lookup failed for %s: %s", profile.common_name, e)

    if wiki_url:
        profile.range_map_url = wiki_url
        profile.range_map_source = "wikipedia"
        db.commit()
        logger.info("Range map fallback (Wikimedia): %s → %s", profile.common_name, wiki_url[:80])
        return RedirectResponse(url=wiki_url, status_code=302)

    # No Wikipedia fallback available either — this is a genuine dead end,
    # but still better to say so plainly than redirect to a URL already
    # confirmed broken.
    raise HTTPException(status_code=503,
                        detail=f"Range map source for {profile.common_name} is currently unavailable "
                               "and no Wikipedia fallback was found. Try the refresh button again later.")


@router.get("/{profile_id}/calls")
def get_bird_calls(profile_id: str, db: Session = Depends(get_db)):
    """List available bird call files (local or URL-only)."""
    profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Bird profile not found")
    calls = []
    for i, call in enumerate(profile.call_media or []):
        path = call.get("path")
        if path and os.path.exists(path):
            # Serve from local disk
            calls.append({**call, "stream_url": f"/api/v1/birds/{profile_id}/calls/{i}"})
        elif call.get("url"):
            # Stream directly from source URL (iNaturalist CDN)
            calls.append({**call, "stream_url": call["url"]})
    return calls


@router.get("/{profile_id}/presence-history")
def get_presence_history(profile_id: str, db: Session = Depends(get_db)):
    """
    This profile's OWN detection history at THIS location, bucketed by
    week-of-year and summed across however many years of data exist —
    different from `monthly_frequency` (BirdProfile's other
    presence field), which is eBird's regional checklist-frequency
    estimate for the species in general, not anything this deployment
    has detected. Requested directly: the existing Seasonal
    Presence card only ever showed that generic eBird curve, with no way
    to see this species' own local pattern.

    Same detection-matching definition profile_to_out() already uses for
    this profile's total_detections/last_detected stats (label OR
    common_name match, respecting show_deleted_detections and
    min_confidence_display) — so this chart's totals stay consistent
    with the numbers already shown elsewhere on the same page, rather
    than quietly using a different definition of "this profile's
    detections" in a second place.

    Weekly (52 buckets), not monthly (12) or daily (365) — monthly is
    what the existing eBird-sourced chart already uses, so matching it
    wouldn't add anything a line graph needs to look meaningfully
    different from a bar chart; daily is too sparse for a typical single-
    deployment dataset (most days for most species would be zero,
    producing a noisy line rather than a readable pattern). Weekly is
    close to the resolution eBird's own bar charts use (48 periods/year)
    and is dense enough for a smooth line while each bucket still
    usually has enough data to mean something.
    """
    profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Bird profile not found")

    from datetime import date, timedelta
    from zoneinfo import ZoneInfo
    from ..models import AppSettings as _AS

    _s = db.query(_AS).filter(_AS.id == 1).first()
    _show_deleted = bool(getattr(_s, "show_deleted_detections", False)) if _s else False
    _min_conf = float(getattr(_s, "min_confidence_display", 0.0) or 0.0) if _s else 0.0
    _tz_name = (_s.timezone if _s else None) or "UTC"
    try:
        _tz = ZoneInfo(_tz_name)
    except Exception:
        _tz = ZoneInfo("UTC")

    q = (
        db.query(Recording.trigger_timestamp)
        .join(Detection, Detection.recording_id == Recording.id)
        .filter((Detection.label == profile.label) | (Detection.common_name == profile.common_name))
    )
    if not _show_deleted:
        q = q.filter(Recording.deleted_at.is_(None))
    if _min_conf > 0:
        q = q.filter(Detection.confidence >= _min_conf)

    weekly_counts = [0] * 52
    years = set()
    for (ts,) in q.all():
        if ts is None:
            continue
        # Recording.trigger_timestamp is stored as naive UTC (no tzinfo
        # attached) — convert to the configured local timezone before
        # bucketing, same reasoning as yard_pulse's own local-day
        # boundaries: a detection at 11pm local on Dec 31 shouldn't land
        # in week 1 just because it's already Jan 1 in UTC.
        local_dt = ts.replace(tzinfo=ZoneInfo("UTC")).astimezone(_tz) if ts.tzinfo is None else ts.astimezone(_tz)
        years.add(local_dt.year)
        day_of_year = local_dt.timetuple().tm_yday  # 1-366
        week_idx = min(51, (day_of_year - 1) // 7)  # 52 buckets regardless of leap year — the last one just gets 1-2 extra days
        weekly_counts[week_idx] += 1

    # Human-readable week-start labels and a month number per week, built
    # from a fixed non-leap reference year — purely for display, so
    # stable regardless of which years the underlying data spans.
    # The month number lets the frontend map each week onto the same
    # Winter/Spring/Summer/Fall bands already used elsewhere in the app
    # (Dashboard, Life List, Field Guide all define that mapping
    # independently already; sending it here too would just be a
    # fourth copy of the same 4 month-ranges to keep in sync).
    ref_year = 2023
    week_starts = [date(ref_year, 1, 1) + timedelta(days=7 * i) for i in range(52)]

    weekly = [
        {
            "week": i + 1,
            # 0-indexed (0=Jan...11=Dec), NOT Python's own 1-indexed
            # date.month — matching the SAME convention the frontend's
            # existing SEASONS constant already uses (built around
            # 0-indexed array positions from the eBird monthly_frequency
            # chart, e.g. Winter: [11,0,1]). Sending Python's native
            # 1-indexed month here silently shifted every month by one
            # and left December matching no season at all — caught by a
            # direct test before this ever reached a user, not
            # discovered after.
            "month": week_starts[i].month - 1,
            "label": week_starts[i].strftime("%b %d"),
            "count": weekly_counts[i],
        }
        for i in range(52)
    ]

    total = sum(weekly_counts)
    peak_idx = max(range(52), key=lambda i: weekly_counts[i]) if total > 0 else None

    return {
        "weekly": weekly,
        "total_detections": total,
        "years_covered": sorted(years),
        "peak_week": weekly[peak_idx] if peak_idx is not None and weekly_counts[peak_idx] > 0 else None,
    }


@router.get("/{profile_id}/calls/{call_index}")
def stream_bird_call(profile_id: str, call_index: int, db: Session = Depends(get_db)):
    """Stream a specific bird call audio file."""
    profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Bird profile not found")
    calls = profile.call_media or []
    if call_index >= len(calls):
        raise HTTPException(status_code=404, detail="Call not found")
    path = calls[call_index].get("path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Call file not on disk")
    ext = os.path.splitext(path)[1].lower()
    mime = {".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".wav": "audio/wav",
            ".m4a": "audio/mp4", ".flac": "audio/flac"}.get(ext, "audio/mpeg")
    # Same missing-Cache-Control gap as the photo endpoints above, and an
    # even bigger win here — audio files are larger than photos, so the
    # repeated-download cost over a Cloudflare tunnel is worse per file,
    # not just more frequent.
    return FileResponse(path, media_type=mime,
                         headers={"Cache-Control": "public, max-age=86400"})



# ── eBird Life List Export ─────────────────────────────────────────────────────

def _life_list_records(db: Session, exclude_bats: bool = False):
    """
    Shared query backing both life-list export endpoints (CSV/eBird and
    JSON): one row per detected species with first/last detection
    timestamps and total detection count. Factored out so the two export
    formats can't silently drift apart on what counts as "the life list."

    Excludes a species whose every detection came from Haikubox (none
    from the actual Pi/device) — see get_life_list's matching comment
    for the full reasoning; kept in sync with that endpoint deliberately,
    for the exact reason stated in this docstring's first line.

    exclude_bats: off by default, since bats genuinely belong on Chirp's
    own Life List — this only exists for export_life_list_ebird to opt
    into, since eBird's taxonomy is birds-only and has no concept of a
    bat species at all. A bat submission there either gets silently
    dropped or, worse, mismatched against some unrelated bird name by
    eBird's own import-time matching — neither is something the eBird
    export should ever risk, so it's excluded at the source rather than
    filtered client-side after the fact.
    """
    q = (
        db.query(
            Detection.common_name,
            Detection.scientific_name,
            func.min(Recording.trigger_timestamp).label("first_dt"),
            func.max(Recording.trigger_timestamp).label("last_dt"),
            func.count(Detection.id).label("n"),
        )
        .join(Recording, Detection.recording_id == Recording.id)
        .filter(Recording.deleted_at.is_(None))
    )
    from ..services.species_filters import exclude_haikubox_only
    q = exclude_haikubox_only(q, db)
    if exclude_bats:
        q = q.filter(Recording.is_bat.is_(False))
    return (
        q.group_by(Detection.common_name)
        .order_by(func.max(Recording.trigger_timestamp).desc())
        .all()
    )


@router.get("/life-list/ebird-export")
def export_life_list_ebird(db: Session = Depends(get_db)):
    """
    Export the life list in eBird Record Format v3.
    Import at https://ebird.org/import — select "eBird Record Format" (not Checklist).

    Column order below is confirmed against a REAL, SUCCESSFUL eBird
    import — not reverse-engineered from an error message this time. Two
    earlier versions of this function each got the schema wrong in a
    different way (v1 put Location Name at column 5, entirely missing
    the field; v2 moved it to column 6 based on eBird's error message
    alone, closer but still wrong — it inserted a genuinely blank filler
    column rather than splitting Scientific Name into its real two
    separate fields). This version matches a file that was hand-diffed
    against the original broken export, row for row, after it actually
    imported cleanly:
      1  Common Name
      2  Genus                (Scientific Name split in two — NOT one
      3  Species                combined field, the actual bug in both
                                 earlier versions)
      4  Count                 (X = presence-only)
      5  Species Comments
      6  Location Name
      7  Latitude              (decimal degrees)
      8  Longitude             (decimal degrees)
      9  Date                  (M/D/YYYY)
      10 Start Time            (H:MM AM/PM)
      11 State/Province        (bare code, e.g. "MA" — NOT "US-MA";
                                 confirmed from the working file, no
                                 country prefix)
      12 Country Code          (e.g. US)
      13 Protocol              ("Incidental", capitalized — confirmed
                                 from the working file, lowercase
                                 "incidental" was never actually tested)
      14 Number of Observers   ("1")
      15 Duration (minutes)    ("0")
      16 All Obs Reported      ("N" — confirmed from the working file;
                                 NOT "0", that was never actually right)
      17 Distance (km)         (blank)
      18 Area (ha)             (blank)
      19 Checklist Comments

    Bats are excluded entirely (exclude_bats=True below) — eBird's
    taxonomy is birds-only, so a bat submission here either gets
    silently dropped by eBird's own import or, worse, mismatched against
    some unrelated bird name by its name-matching logic. Neither is
    something this export should ever risk; Chirp's own Life List still
    shows bats normally, this exclusion is specific to the eBird format.
    """
    import csv, io
    from datetime import datetime as _dt

    records = _life_list_records(db, exclude_bats=True)
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    lat  = s.latitude    if s else None
    lon  = s.longitude   if s else None
    loc  = s.location_name if s else "Chirp Detection System"

    # Real reverse-geocoding via the same functions bar-chart likelihood data
    # already uses — replaces a previous version of this code that hardcoded
    # country_code = "US" and matched location_name text against a fixed
    # dictionary of US state names only, silently producing an incorrect
    # export for any deployment outside the United States (this software
    # supports non-US range-map sources elsewhere, so assuming US-only here
    # was a real, if narrow-impact, correctness gap — not just theoretical).
    # get_country_code_from_latlon/get_region_code_from_latlon already
    # existed, already worked, and were simply never called from here.
    state_code   = ""
    country_code = "US"  # only as a last-resort fallback if lat/lon aren't set at all
    if lat is not None and lon is not None:
        try:
            from ..services.ebird_service import get_region_code_from_latlon
            from ..services.bird_enricher import _get_ebird_api_key
            api_key = _get_ebird_api_key(db)
            region = get_region_code_from_latlon(lat, lon, api_key or "")
            if region:
                parts = region.split("-")
                country_code = parts[0]
                if len(parts) >= 2:
                    # Bare state code only (e.g. "MA"), NOT the full
                    # "US-MA" region code — confirmed from the working
                    # import; eBird's own subnational1_code field
                    # convention is region-prefixed, but this CSV column
                    # apparently isn't, and the earlier version that used
                    # the prefixed form was never actually verified to work.
                    state_code = parts[1]
        except Exception as e:
            logger.warning("Region lookup failed for eBird export, falling back to US: %s", e)

    buf = io.StringIO()
    writer = csv.writer(buf)
    # NO header row — eBird Record Format is headerless

    for rec in records:
        dt = rec.last_dt or rec.first_dt or _dt.utcnow()
        date_str = dt.strftime("%-m/%-d/%Y")   # M/D/YYYY no leading zeros
        time_str = dt.strftime("%-I:%M %p")    # H:MM AM/PM no leading zeros
        lat_str  = f"{lat:.5f}" if lat else ""
        lon_str  = f"{lon:.5f}" if lon else ""

        # Scientific Name genuinely needs to be two separate fields, not
        # one combined string with a space in it — the actual root cause
        # both earlier versions of this export got wrong. Splits on the
        # first space only, so a species epithet that's itself
        # multi-word (rare, but exists) doesn't get truncated.
        sci = (rec.scientific_name or "").strip()
        if " " in sci:
            genus, species_epithet = sci.split(" ", 1)
        else:
            genus, species_epithet = sci, ""

        writer.writerow([
            rec.common_name,        # 1  Common Name
            genus,                  # 2  Genus
            species_epithet,        # 3  Species
            "X",                    # 4  Count (X = presence-only)
            "Detected by Chirp automated acoustic monitor",  # 5 Species Comments
            loc or "My Location",   # 6  Location Name
            lat_str,                # 7  Latitude
            lon_str,                # 8  Longitude
            date_str,               # 9  Date (M/D/YYYY)
            time_str,               # 10 Start Time
            state_code,             # 11 State/Province (bare code)
            country_code,           # 12 Country Code
            "Incidental",           # 13 Protocol
            "1",                    # 14 Number of Observers
            "0",                    # 15 Duration (minutes)
            "N",                    # 16 All Obs Reported
            "",                     # 17 Distance (blank)
            "",                     # 18 Area (blank)
            f"Auto-exported from Chirp on {_dt.utcnow().strftime('%Y-%m-%d')}",  # 19 Checklist Comments
        ])

    # No BOM — eBird explicitly warns against it in their import docs
    csv_bytes = buf.getvalue().encode("utf-8")
    from fastapi.responses import Response
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=chirp_ebird_export_{_dt.utcnow().strftime('%Y%m%d')}.csv"},
    )

@router.get("/life-list/json-export")
def export_life_list_json(db: Session = Depends(get_db)):
    """
    Export the life list as plain JSON — one object per detected species
    with common/scientific name, first/last detection timestamps (ISO
    8601), and total detection count. General-purpose export for anyone
    who wants their Chirp life list in a structured format for their own
    use (spreadsheets, other birding apps, personal records, etc).

    NOT an eBird import format — eBird's bulk import tool only accepts CSV
    (see export_life_list_ebird above for that). This endpoint exists
    alongside it as a second download option, not a substitute.
    """
    import json
    from datetime import datetime as _dt
    from fastapi.responses import Response

    records = _life_list_records(db)

    payload = {
        "exported_at": _dt.utcnow().isoformat() + "Z",
        "source": "Chirp",
        "species_count": len(records),
        "species": [
            {
                "common_name": rec.common_name,
                "scientific_name": rec.scientific_name or None,
                "first_detected": rec.first_dt.isoformat() if rec.first_dt else None,
                "last_detected": rec.last_dt.isoformat() if rec.last_dt else None,
                "detection_count": rec.n,
            }
            for rec in records
        ],
    }

    json_bytes = json.dumps(payload, indent=2).encode("utf-8")
    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=chirp_life_list_{_dt.utcnow().strftime('%Y%m%d')}.json"},
    )

@router.get("/{profile_id}/ebird")
def get_ebird_data(profile_id: str, db: Session = Depends(get_db)):
    """Return raw eBird taxonomy/data for a species."""
    profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ebird_data": profile.ebird_data, "ebird_species_code": profile.ebird_species_code}


# ── Background Helpers ────────────────────────────────────────────────────────

def _enrich_profile(profile_id: str, force: bool = False):
    from ..database import SessionLocal
    from ..services.bird_enricher import BirdEnricher
    from ..services.bat_profile_content import BAT_LABEL
    db = SessionLocal()
    try:
        profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
        if not profile:
            return
        enricher = BirdEnricher(db)
        if profile.label == BAT_LABEL:
            enricher._ensure_bat_profile(force=force)
        else:
            enricher.enrich_profile(profile, force=force)
    except Exception as e:
        logger.error("Enrichment error for %s: %s", profile_id, e)
    finally:
        db.close()


def _fetch_range_map_bg(profile_id: str, source: str) -> None:
    """Background task: fetch and store a range map from the specified source."""
    from ..database import SessionLocal
    from ..services.range_map_service import fetch_ebird_st_map, fetch_gbif_map
    from ..config import settings as _cfg
    import re as _re
    import os as _os

    db = SessionLocal()
    try:
        profile = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
        if not profile:
            return

        common_name  = profile.common_name
        sci_name     = profile.scientific_name or common_name
        species_code = profile.ebird_species_code

        safe = _re.sub(r"[^a-zA-Z0-9_-]", "_", common_name.lower())
        media_dir = _os.path.join(_cfg.media_dir, safe)
        _os.makedirs(media_dir, exist_ok=True)

        success = False

        if source == "ebird_st":
            # Get S&T key from DB settings (preferred) or env config
            from ..models import AppSettings
            s = db.query(AppSettings).filter(AppSettings.id == 1).first()
            api_key = (s.ebird_st_api_key if s else None) or getattr(_cfg, "ebird_st_api_key", None)
            if not api_key:
                logger.error(
                    "eBird S&T: no API key configured for %s — "                    "go to Settings and add your eBird S&T key (get one at https://ebird.org/st/request)",
                    common_name
                )
                return
            if not species_code:
                logger.error(
                    "eBird S&T: no eBird species code for %s — "                    "run Refresh All Data first to populate the species code",
                    common_name
                )
                return
            logger.info(
                "eBird S&T: fetching range map for %s (code=%s) using key %s***",
                common_name, species_code, api_key[:4]
            )
            out_path = _os.path.join(media_dir, "range_map_ebird_st.png")
            success = fetch_ebird_st_map(species_code, api_key, out_path)

        elif source == "gbif":
            out_path = _os.path.join(media_dir, "range_map_gbif.png")
            success = fetch_gbif_map(sci_name, common_name, out_path)

        if success:
            profile.range_map_url    = f"file://{out_path}"
            profile.range_map_source = source
            db.commit()
            logger.info("Range map updated for %s from %s: %s", common_name, source, out_path)
        else:
            logger.warning("Range map fetch FAILED for %s from %s", common_name, source)

    except Exception as e:
        logger.error("_fetch_range_map_bg error for %s/%s: %s", profile_id, source, e, exc_info=True)
    finally:
        db.close()
