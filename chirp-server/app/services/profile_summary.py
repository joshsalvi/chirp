"""
Generates the AI-written presence-pattern note at the top of a Bird
Profile — when a species shows up, how often, recent activity in this
specific yard. Distinct from BirdProfile.description, which is Wikipedia's
generic species text.

Same posture as daily_summary.py: optional, best-effort, and cached
rather than regenerated on every view — generates once on first request,
then sits cached until a manual regenerate.
"""

import logging
from datetime import datetime

from .ai_providers import get_feature_config, call_chat_completion

logger = logging.getLogger("chirp.profile_summary")


def _gather_species_data(db, profile) -> dict:
    """Real detection history for this one species — first/last seen,
    total count, monthly pattern if available — so the model is grounded
    in what's actually in this yard's data rather than inventing specifics."""
    from ..models import Recording, Detection
    from sqlalchemy import func

    non_hb_filter = Recording.haikubox_detection_id.is_(None)
    row = (
        db.query(
            func.min(Recording.trigger_timestamp).label("first_dt"),
            func.max(Recording.trigger_timestamp).label("last_dt"),
            func.count(Detection.id).label("n"),
        )
        .join(Recording, Detection.recording_id == Recording.id)
        .filter(Detection.common_name == profile.common_name)
        .filter(Recording.deleted_at.is_(None))
        .filter(non_hb_filter)
        .first()
    )

    return {
        "common_name": profile.common_name,
        "scientific_name": profile.scientific_name,
        "first_detected": row.first_dt.strftime("%B %Y") if row and row.first_dt else None,
        "last_detected": row.last_dt.strftime("%B %d, %Y") if row and row.last_dt else None,
        "total_detections": row.n if row else 0,
        "monthly_frequency": profile.monthly_frequency,  # 12 floats Jan-Dec, or None
    }


def generate_profile_summary(db, profile) -> None:
    """
    Generates the presence summary for one BirdProfile and stores it on
    that row, or stores an error and leaves any previous summary in
    place. `profile` is an already-loaded BirdProfile ORM object —
    caller is responsible for fetching it and committing the session
    afterward isn't needed here, this function commits itself.
    """
    config = get_feature_config("profile_summary", db)
    if config is None:
        return  # feature disabled or unconfigured — nothing to do, silently
    provider, api_key = config

    from .personality import personality_instructions
    from ..models import AppSettings
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    tone_instructions = personality_instructions(
        friendliness=s.ai_personality_friendliness if s and s.ai_personality_friendliness is not None else 60,
        informational=s.ai_personality_informational if s and s.ai_personality_informational is not None else 50,
        irreverence=s.ai_personality_irreverence if s and s.ai_personality_irreverence is not None else 35,
        depth=s.ai_personality_depth if s and s.ai_personality_depth is not None else 50,
        curiosity=s.ai_personality_curiosity if s and s.ai_personality_curiosity is not None else 50,
        brief=True,
    )

    try:
        data = _gather_species_data(db, profile)

        if data["total_detections"] == 0:
            # Nothing to say yet — not an error, just genuinely no basis
            # for a presence summary. Leave the card hidden rather than
            # generate a paragraph about having no data.
            profile.ai_presence_summary = None
            profile.ai_presence_summary_error = None
            profile.ai_presence_summary_generated_at = datetime.utcnow()
            db.commit()
            return

        monthly_line = ""
        if data["monthly_frequency"] and len(data["monthly_frequency"]) == 12:
            months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
            ranked = sorted(zip(months, data["monthly_frequency"]), key=lambda x: -x[1])[:3]
            monthly_line = f"Historically most frequent (regional data, not just this yard): {', '.join(m for m, _ in ranked)}.\n"

        system_prompt = (
            "You are writing a very short (2-3 sentences, one short paragraph) note for the top "
            "of a bird species' profile page in a home acoustic-monitoring app called Chirp. The "
            "note is about THIS species' presence pattern in THIS SPECIFIC yard, based on the "
            "real detection data given to you — not a general species description (that's shown "
            "elsewhere on the page already). Only state facts you're actually confident are true; "
            "do not invent specific numbers, dates, or statistics beyond what's given. "
            "Regardless of tone settings below: don't flatter the reader about their own data — "
            "no 'impressive!', no calling an ordinary detection count for a common species "
            "remarkable, no exclamation points used just to manufacture excitement. State what "
            "happened; let it be interesting on its own if it is, and unremarkable if it isn't. "
            f"{tone_instructions} No markdown, just plain prose, second person "
            "('you've heard...', 'your yard...')."
        )
        user_prompt = (
            f"Species: {data['common_name']} ({data['scientific_name'] or 'unknown scientific name'})\n"
            f"First detected in this yard: {data['first_detected']}\n"
            f"Most recently detected: {data['last_detected']}\n"
            f"Total detections logged: {data['total_detections']}\n"
            f"{monthly_line}"
            "\nWrite the presence-pattern note."
        )

        text = call_chat_completion(provider, api_key, system_prompt, user_prompt, max_tokens=300, db=db, feature="profile_summary")

        profile.ai_presence_summary = text
        profile.ai_presence_summary_generated_at = datetime.utcnow()
        profile.ai_presence_summary_error = None
        db.commit()
        logger.info("Profile summary generated for %s via %s", profile.common_name, provider)

    except Exception as e:
        logger.warning("Profile summary generation failed for %s: %s", profile.common_name, e)
        profile.ai_presence_summary_error = str(e)[:500]
        db.commit()


def refresh_stale_profile_summaries(db, max_age_days: int, max_per_run: int = 100) -> dict:
    """
    Regenerates presence summaries that have gone stale — a species'
    first-view-only summary can otherwise sit unchanged for months while
    real detection counts and "most recently detected" keep moving,
    slowly drifting from what the yard's actual data now shows. Called
    from a scheduled background loop (see main.py's
    _profile_summary_refresh_loop), not on every request.

    Selects BirdProfile rows where the feature is enabled AND either:
      - never generated at all (ai_presence_summary_generated_at IS NULL),
        covering a species added/enriched after the lazy first-view path
        was skipped for some reason, or
      - generated longer ago than max_age_days.
    Deliberately excludes any profile with ai_presence_summary_error set —
    same rule as the lazy first-view trigger: a species whose generation
    is already known to be failing should not silently retry on every
    scheduled run, for the same reason it doesn't retry on every page
    view (wasted local compute, or a real recurring cost against a paid
    hosted API for something already known not to work). Use the manual
    "Regenerate" button on a profile to retry after an actual fix.

    max_per_run caps how many summaries get regenerated in a single
    scheduled pass — a fresh install or one with hundreds of species
    could otherwise try to regenerate everything at once the first time
    this runs, which is a lot of back-to-back AI calls in one go
    (expensive against a hosted API, and slow/CPU-heavy against a local
    Ollama instance already serving other requests). Remaining stale
    profiles beyond the cap simply get picked up on the next scheduled
    run instead — the staleness condition doesn't go away, so nothing
    is permanently skipped, just spread out over more than one run.

    Returns a small dict of counts for the caller to log, rather than
    just logging internally — keeps this function's return value
    inspectable/testable independent of logging side effects.
    """
    from ..models import BirdProfile
    from datetime import timedelta

    config = get_feature_config("profile_summary", db)
    if config is None:
        return {"skipped": "feature_disabled", "regenerated": 0, "failed": 0}

    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    candidates = (
        db.query(BirdProfile)
        .filter(BirdProfile.ai_presence_summary_error.is_(None))
        .filter(
            (BirdProfile.ai_presence_summary_generated_at.is_(None))
            | (BirdProfile.ai_presence_summary_generated_at < cutoff)
        )
        .order_by(BirdProfile.ai_presence_summary_generated_at.asc().nullsfirst())
        .limit(max_per_run)
        .all()
    )

    regenerated, failed = 0, 0
    for profile in candidates:
        try:
            generate_profile_summary(db, profile)
            # generate_profile_summary itself sets ai_presence_summary_error
            # on failure rather than raising — check it directly rather than
            # relying on an exception here, since none will be raised for a
            # normal AI-call failure (only for something wildly unexpected).
            if profile.ai_presence_summary_error:
                failed += 1
            else:
                regenerated += 1
        except Exception as e:
            logger.warning("Unexpected error refreshing profile summary for %s: %s", profile.common_name, e)
            failed += 1

    logger.info(
        "Profile summary refresh: %d candidates, %d regenerated, %d failed",
        len(candidates), regenerated, failed,
    )
    return {"candidates": len(candidates), "regenerated": regenerated, "failed": failed}
