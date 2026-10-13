"""
Real, grounded enrichment for Daily/Weekly Journal — shared by both
daily_summary.py and weekly_summary.py. Three real, computed data
sources fed INTO the prompt as grounding material, matching the same
principle as everything else in both callers: give the model real
numbers/facts to describe, don't ask it to invent trends, facts, or
predictions on its own.

- get_trend_context: a real historical baseline (average detections/
  species per day over a trailing window BEFORE the current period),
  so "today's 12 species vs a typical 8" is an actual computed
  comparison.
- get_species_facts: real, Wikipedia-sourced descriptions
  (BirdProfile.description, populated by bird_enricher.py from actual
  Wikipedia/iNaturalist fetches, not invented) for the period's top
  species — short excerpts only, and the caller's own system prompt
  must instruct the model to paraphrase these into its own words,
  never quote them directly (this project's own copyright discipline
  applies the same way here as anywhere else real source text flows
  into a prompt).
- get_other_likely_species: species genuinely likely for this region
  and month (the exact same monthly_frequency data birds.py's own
  regional-library/Field Guide feature uses, including the same
  "recompute the live current-month value from the stored 12-month
  array, don't trust a possibly-stale cached current_likelihood
  column" fix already proven correct there) that weren't actually
  detected in the current period.
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger("chirp.journal_enrichment")


def get_trend_context(db, tz: ZoneInfo, period_start_utc: datetime, period_length,
                       current_species_count: int, current_detection_count: int,
                       min_conf: float = 0.0, show_deleted: bool = False,
                       baseline_periods: int = 4) -> dict:
    """
    Real historical baseline - the average species count and detection
    count per period over the baseline_periods FULL periods immediately
    BEFORE the current one.

    period_length is an explicit timedelta (always exactly 1 day for
    Daily Journal, always exactly 7 days for Weekly Journal) - NOT
    inferred from the current period's own start/end boundaries. A real
    bug caught by testing with actual, checkable numbers rather than
    just "does this run without crashing": the current period is often
    genuinely PARTIAL (Daily Journal's "today so far" is less than 24
    hours for anyone running this before midnight), so deriving the
    baseline bucket size from period_end - period_start would silently
    shrink the whole comparison window to a few hours instead of real
    trailing days - this test's own baseline data (placed 1-4 real days
    in the past) fell completely outside that mis-sized window, and
    has_baseline came back False even with real, present data to
    compare against.

    Returns has_baseline=False (never raises) if there's not enough
    real history yet - a brand-new install with only a few days of
    data has nothing honest to compare against, and the caller should
    treat that as "not enough history yet" rather than a real
    "no change" finding.
    """
    from ..models import Recording, Detection

    baseline_start_utc = period_start_utc - (period_length * baseline_periods)

    base_filters = [
        Recording.trigger_timestamp >= baseline_start_utc,
        Recording.trigger_timestamp < period_start_utc,
        Recording.is_bat.is_(False),
    ]
    if not show_deleted:
        base_filters.append(Recording.deleted_at.is_(None))
    base_filters.append(Recording.haikubox_detection_id.is_(None))

    q = (
        db.query(Detection.common_name, Detection.confidence, Recording.trigger_timestamp)
        .join(Recording, Detection.recording_id == Recording.id)
        .filter(*base_filters)
    )
    if min_conf > 0:
        q = q.filter(Detection.confidence >= min_conf)
    rows = q.all()

    if not rows:
        return {"has_baseline": False}

    per_period_species: dict = {}
    per_period_detections: dict = {}
    for name, conf, ts in rows:
        bucket_index = int((ts - baseline_start_utc) / period_length)
        if bucket_index < 0 or bucket_index >= baseline_periods:
            continue
        per_period_species.setdefault(bucket_index, set()).add(name)
        per_period_detections[bucket_index] = per_period_detections.get(bucket_index, 0) + 1

    species_counts_per_bucket = [len(per_period_species.get(i, set())) for i in range(baseline_periods)]
    detection_counts_per_bucket = [per_period_detections.get(i, 0) for i in range(baseline_periods)]

    avg_species = sum(species_counts_per_bucket) / baseline_periods
    avg_detections = sum(detection_counts_per_bucket) / baseline_periods

    return {
        "has_baseline": True,
        "baseline_periods": baseline_periods,
        "avg_species": round(avg_species, 1),
        "avg_detections": round(avg_detections, 1),
        "species_delta": round(current_species_count - avg_species, 1),
        "detections_delta": round(current_detection_count - avg_detections, 1),
    }


def get_species_facts(db, species_names: list, max_species: int = 3) -> list:
    """
    Real, sourced facts for up to max_species of the given names, in the
    caller's own given order (typically already sorted by detection
    count / notability) rather than DB row order, since the caller's
    priority is what actually matters when only max_species can fit.

    Prefers a real Cornell Lab "Cool Fact" (BirdProfile.aab_cool_facts)
    over the general description excerpt when available — genuinely
    more specific and citable ("robins eat more earthworms in the
    morning, more fruit later in the day" vs. a general opening
    paragraph), and a real, distinct additional source from the
    description itself (which may now ALSO be Cornell Lab-sourced, but
    is a different piece of text — see bird_enricher.py's own comment
    on preferring AAB's description over Wikipedia's). When a species
    has multiple cool facts, picks one at random rather than always the
    first — real variety across different days' journal entries for a
    species that comes up often, rather than the same fact every time.

    Returns a list of {common_name, excerpt, source} - excerpt capped
    short deliberately (a grounding fact for the model to paraphrase,
    not the whole stored text dumped in verbatim). source is "cool_fact"
    or "description", so callers/tests can tell which path was used.
    """
    import random
    from ..models import BirdProfile

    if not species_names:
        return []

    profiles = (
        db.query(BirdProfile.common_name, BirdProfile.description, BirdProfile.aab_cool_facts)
        .filter(BirdProfile.common_name.in_(species_names))
        .all()
    )
    by_name = {name: (desc, facts) for name, desc, facts in profiles if desc or facts}

    def _cap(text: str) -> str:
        text = text.strip()
        if len(text) > 280:
            cut = text[:280]
            last_period = cut.rfind(". ")
            return cut[:last_period + 1] if last_period > 100 else cut + "..."
        return text

    results = []
    for name in species_names:
        if name not in by_name:
            continue
        desc, cool_facts = by_name[name]
        if cool_facts:
            excerpt = _cap(random.choice(cool_facts))
            results.append({"common_name": name, "excerpt": excerpt, "source": "cool_fact"})
        elif desc:
            results.append({"common_name": name, "excerpt": _cap(desc), "source": "description"})
        else:
            continue
        if len(results) >= max_species:
            break
    return results


def get_other_likely_species(db, detected_species_names: set, max_species: int = 5) -> list:
    """
    Species genuinely likely for this region right now (the same real
    monthly_frequency data birds.py's regional-library endpoint uses,
    including recomputing the live current-month value from the stored
    12-month array rather than trusting a possibly-stale cached
    current_likelihood column - the identical fix already proven
    correct there, ported here rather than reintroducing the staleness
    bug it fixed) that were NOT among the species actually detected in
    the current period. Returns [] gracefully if RegionalSpecies hasn't
    been populated yet (regional-library sync is a manual, one-time
    action) rather than erroring.
    """
    from ..models import RegionalSpecies

    current_month_index = datetime.utcnow().month - 1  # 0-indexed, matches ebird_service.py's own convention

    try:
        candidates = (
            db.query(RegionalSpecies.common_name, RegionalSpecies.monthly_frequency, RegionalSpecies.current_likelihood)
            .all()
        )
    except Exception as e:
        logger.info("get_other_likely_species: RegionalSpecies query failed (non-fatal, likely not synced yet): %s", e)
        return []

    scored = []
    for name, monthly, stale_likelihood in candidates:
        if name in detected_species_names:
            continue
        live_likelihood = monthly[current_month_index] if monthly and len(monthly) == 12 else (stale_likelihood or 0.0)
        if live_likelihood > 0:
            scored.append((name, live_likelihood))

    scored.sort(key=lambda x: -x[1])
    return [name for name, _ in scored[:max_species]]


def get_time_of_day_pattern(db, period_start_utc: datetime, period_end_utc: datetime,
                             min_conf: float = 0.0, show_deleted: bool = False) -> dict:
    """
    Real composition commentary distinct from per-species facts: which
    species were genuinely concentrated in the dawn/morning window vs.
    spread through the rest of the day, computed from actual detection
    timestamps rather than general knowledge about which species are
    "usually" dawn choristers (a real species can and does behave
    differently on a given real day than its textbook pattern - this
    reports what actually happened, not what's typical).

    "Dawn/morning" is a fixed local-clock window (5am-9am) rather than
    computed relative to actual sunrise/sunset for this date/location
    - a real simplification: a true civil-dawn calculation needs the
    tenant's precise lat/lon and date, which callers of this function
    don't uniformly have on hand, and a fixed clock window is a
    reasonable, honest approximation for "the early part of the day"
    without overstating precision Chirp doesn't actually have here.

    Returns {} if there's not enough real data to say anything
    meaningful (fewer than 3 total detections) rather than reporting a
    pattern from too little data to mean anything.
    """
    from ..models import Recording, Detection

    base_filters = [
        Recording.trigger_timestamp >= period_start_utc,
        Recording.trigger_timestamp < period_end_utc,
        Recording.is_bat.is_(False),
    ]
    if not show_deleted:
        base_filters.append(Recording.deleted_at.is_(None))
    base_filters.append(Recording.haikubox_detection_id.is_(None))

    q = (
        db.query(Detection.common_name, Detection.confidence, Recording.trigger_timestamp)
        .join(Recording, Detection.recording_id == Recording.id)
        .filter(*base_filters)
    )
    if min_conf > 0:
        q = q.filter(Detection.confidence >= min_conf)
    rows = q.all()

    if len(rows) < 3:
        return {}

    dawn_species: dict = {}
    rest_of_day_species: dict = {}
    for name, conf, ts in rows:
        bucket = dawn_species if 5 <= ts.hour < 9 else rest_of_day_species
        bucket[name] = bucket.get(name, 0) + 1

    # A species genuinely "dawn-concentrated" today: most of its own
    # actual detections fell in that window, not just present there at
    # all (a species heard once at dawn and 5 times all afternoon isn't
    # a real dawn-concentration story).
    dawn_concentrated = [
        name for name, dawn_count in dawn_species.items()
        if dawn_count > rest_of_day_species.get(name, 0)
    ]

    return {
        "dawn_species_count": len(dawn_species),
        "rest_of_day_species_count": len(rest_of_day_species),
        "dawn_concentrated_species": sorted(dawn_concentrated)[:5],
    }


def get_taxonomic_diversity(db, detected_species_names: set) -> dict:
    """
    Real "landscape" commentary distinct from any of the other three
    functions: how taxonomically diverse today's/this week's actual
    detections are, using real family/order data
    (RegionalSpecies.family_com_name/order_name — the same real eBird
    taxonomy data the regional-library feature already populates, not
    invented). A day with 8 species from 2 families (say, all
    corvids and thrushes) is a genuinely different ecological story
    than 8 species from 6 different families, and that's a real,
    computable fact this project had access to but never surfaced
    anywhere before now.

    Returns {} gracefully if RegionalSpecies hasn't been populated yet
    (same reasoning as get_other_likely_species) or if none of the
    detected species have a taxonomy match (e.g. bat detections, which
    don't appear in RegionalSpecies at all since that table is
    eBird-sourced and eBird only covers birds).
    """
    from ..models import RegionalSpecies

    if not detected_species_names:
        return {}

    try:
        rows = (
            db.query(RegionalSpecies.common_name, RegionalSpecies.family_com_name, RegionalSpecies.order_name)
            .filter(RegionalSpecies.common_name.in_(detected_species_names))
            .all()
        )
    except Exception as e:
        logger.info("get_taxonomic_diversity: RegionalSpecies query failed (non-fatal, likely not synced yet): %s", e)
        return {}

    if not rows:
        return {}

    families: dict = {}
    for name, family, order in rows:
        if family:
            families.setdefault(family, []).append(name)

    if len(families) < 2:
        # Not a meaningful diversity story if there's only one family
        # represented (or none matched) — nothing false to report, but
        # nothing genuinely notable either.
        return {}

    return {
        "family_count": len(families),
        "matched_species_count": len(rows),
        "families": {fam: sorted(species) for fam, species in sorted(families.items(), key=lambda kv: -len(kv[1]))[:6]},
    }
