"""
Generates the Weekly Journal entry — a week-in-review counterpart to
Daily Journal (daily_summary.py), covering the trailing 7 days rather
than "so far today." Same personality-slider and educational framing,
plus real arrival/departure data from wildlife_patterns.py that a
single day's window is too noisy to support reliably (see that
module's docstring for why "regular presence" is gated on distinct-day
counts, not raw detection counts).

Optional and best-effort, same convention as daily_summary.py: no
provider assigned means this never runs; a failed call stores the
error on AppSettings.weekly_summary_error and the card just shows that
error rather than stale content. Scheduled by main.py's background loop
on a configurable day-of-week + hour, not daily.
"""
import logging
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .ai_providers import call_chat_completion, get_feature_config
from .wildlife_patterns import get_arrivals_and_departures
from .journal_enrichment import get_trend_context, get_species_facts, get_other_likely_species, get_time_of_day_pattern, get_taxonomic_diversity

logger = logging.getLogger("chirp.weekly_summary")

# Weekly-appropriate focus angles — deliberately different from daily's
# own list (daily_summary.py's _FOCUS_ANGLES), since "so far today"
# framing doesn't fit a week-in-review, and a week supports angles a
# single day doesn't (a real week-over-week comparison, an arrival/
# departure story, a broader seasonal arc).
_FOCUS_ANGLES = [
    "If there were any real arrivals or departures this week (species newly present, or a "
    "previously-regular species that's gone quiet), lead with that — it's the closest thing "
    "to real news this yard has to offer, and it's worth treating as such rather than burying "
    "it in a list.",
    "Pick the single most interesting educational thread from this week's mix of species — a "
    "migration pattern, a foraging strategy, a vocalization quirk — and give it real room to "
    "breathe rather than skimming past it for the sake of covering everything.",
    "Take stock of the week as a whole: what dominated, what was rare, what the overall "
    "diversity suggests about the health and character of this particular patch of habitat "
    "right now.",
    "Frame the week against the time of year — what's typically happening in bird life "
    "generally around now (migration, breeding, wintering, molting), and how this week's "
    "actual data does or doesn't fit that expected pattern.",
    "If a real trend comparison against a typical week is given, make that the centerpiece — a "
    "genuinely busier or quieter week than usual, or a real week-over-week species-count shift, is "
    "worth real attention: what plausible reason (weather, migration timing, season) might explain "
    "it, framed as a real possibility, not a certainty you can't verify from the data given.",
]

_OPENING_STYLES = [
    "Open by naming the week's actual date range plainly, then move quickly into something "
    "specific and alive — not a generic 'this week in the yard' throat-clear.",
    "Open with the single most notable thing from the whole week — an arrival, a departure, "
    "an unusual number, a genuinely interesting fact — before backing out to the fuller picture.",
]


def _gather_week_data(db, tz: ZoneInfo, s=None) -> dict:
    """Same real-data-grounding principle as daily_summary.py's
    _gather_today_data — pulls the actual trailing 7 days rather than
    letting the model estimate or invent a week's worth of activity.

    s: the caller's already-fetched AppSettings row, if it has one —
    see the matching parameter on daily_summary.py's _gather_today_data
    for why (avoids a second identical query on every generation run)."""
    from ..models import Recording, Detection, AppSettings

    if s is None:
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    min_conf = float(s.min_confidence_display or 0.0) if s else 0.0
    show_deleted = bool(getattr(s, "show_deleted_detections", False)) if s else False

    now_local = datetime.now(ZoneInfo("UTC")).astimezone(tz)
    today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    period_end_local = today_start_local + timedelta(days=1)  # through end of today
    period_start_local = period_end_local - timedelta(days=7)

    period_start_utc = period_start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    period_end_utc = period_end_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    base_filters = [Recording.trigger_timestamp >= period_start_utc,
                    Recording.trigger_timestamp < period_end_utc,
                    Recording.is_bat.is_(False)]
    if not show_deleted:
        base_filters.append(Recording.deleted_at.is_(None))
    base_filters.append(Recording.haikubox_detection_id.is_(None))

    q = (
        db.query(Detection.common_name, Detection.confidence)
        .join(Recording, Detection.recording_id == Recording.id)
        .filter(*base_filters)
    )
    if min_conf > 0:
        q = q.filter(Detection.confidence >= min_conf)
    rows = q.all()

    species_counts: dict = {}
    for name, conf in rows:
        species_counts[name] = species_counts.get(name, 0) + 1

    total_detections = len(rows)
    species_this_week = sorted(species_counts.items(), key=lambda x: -x[1])

    patterns = get_arrivals_and_departures(db, period_start_utc, period_end_utc)

    # Real historical comparison — explicit 7-day period_length (not
    # inferred from period_end - period_start), matching the same real
    # bug fix daily_summary.py's own version of this needed: the
    # CURRENT period is always a genuine full 7 days here (unlike
    # Daily Journal's "today so far"), but passing an explicit length
    # keeps both callers using the identical, already-tested code path
    # rather than one relying on inference and one not.
    try:
        trend = get_trend_context(
            db, tz, period_start_utc, timedelta(days=7),
            current_species_count=len(species_counts), current_detection_count=total_detections,
            min_conf=min_conf, show_deleted=show_deleted,
        )
    except Exception as e:
        logger.info("Weekly summary: trend computation failed (non-fatal): %s", e)
        trend = {"has_baseline": False}

    try:
        top_names = [name for name, _ in species_this_week[:5]]
        species_facts = get_species_facts(db, top_names, max_species=3)
        other_likely = get_other_likely_species(db, set(species_counts.keys()), max_species=5)
        time_pattern = get_time_of_day_pattern(db, period_start_utc, period_end_utc, min_conf=min_conf, show_deleted=show_deleted)
        taxonomic = get_taxonomic_diversity(db, set(species_counts.keys()))
    except Exception as e:
        logger.info("Weekly summary: species facts/likely-species/time-pattern/taxonomic lookup failed (non-fatal): %s", e)
        species_facts, other_likely, time_pattern, taxonomic = [], [], {}, {}

    return {
        "period_start_local": period_start_local,
        "period_end_local": period_end_local - timedelta(days=1),  # display as an inclusive end date, not the exclusive boundary
        "period_start_utc": period_start_utc,
        "period_end_utc": period_end_utc,
        "date_range_str": f"{period_start_local.strftime('%b %-d')}–{(period_end_local - timedelta(days=1)).strftime('%b %-d')}",
        "total_detections": total_detections,
        "species_count": len(species_counts),
        "top_species": species_this_week[:10],
        "first_ever_arrivals": patterns["first_ever_arrivals"],
        "returning_arrivals": patterns["returning_arrivals"],
        "departures": patterns["departures"],
        "location_name": s.location_name if s else None,
        "latitude": s.latitude if s else None,
        "longitude": s.longitude if s else None,
        "trend": trend,
        "species_facts": species_facts,
        "other_likely_species": other_likely,
        "time_pattern": time_pattern,
        "taxonomic": taxonomic,
    }


def generate_weekly_summary(db) -> None:
    """
    Generates this week's summary and stores it on AppSettings, or
    stores an error and leaves any previous summary in place — same
    "don't blank out a still-valid entry on a failed retry" rule as
    generate_daily_summary.
    """
    from ..models import AppSettings

    config = get_feature_config("weekly_summary", db)
    if config is None:
        return  # feature disabled or unconfigured — nothing to do, silently
    provider, api_key = config

    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if s is None:
        return
    try:
        tz = ZoneInfo(s.timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")

    try:
        week = _gather_week_data(db, tz, s)

        species_lines = "\n".join(
            f"- {name}: {count} detection{'s' if count != 1 else ''}"
            for name, count in week["top_species"]
        ) or "- (nothing detected this week)"

        def _species_list_line(label, species):
            if not species:
                return ""
            return f"{label}: {', '.join(species)}\n"

        patterns_block = (
            _species_list_line("Brand new species this week (never detected here before)", week["first_ever_arrivals"])
            + _species_list_line("Returning species (seen before, absent recently, back this week)", week["returning_arrivals"])
            + _species_list_line("Species that had been regular recently but were absent this week", week["departures"])
        ) or "No notable arrivals or departures detected this week — a fairly stable week, species-wise.\n"

        trend = week.get("trend", {})
        if trend.get("has_baseline"):
            trend_line = (
                f"Trend vs. a typical week (average of the last {trend['baseline_periods']} weeks before this one): "
                f"{week['species_count']} species this week vs. a typical {trend['avg_species']} "
                f"({'+' if trend['species_delta'] >= 0 else ''}{trend['species_delta']}); "
                f"{week['total_detections']} detections this week vs. a typical {trend['avg_detections']} "
                f"({'+' if trend['detections_delta'] >= 0 else ''}{trend['detections_delta']})."
            )
        else:
            trend_line = "Not enough history yet to compare this week against a typical week — don't invent a trend claim."

        facts = week.get("species_facts", [])
        facts_block = (
            "\n\nReal reference facts (from Wikipedia, via this species' own profile — put these "
            "IN YOUR OWN WORDS if you use them, never quote or closely paraphrase the wording "
            "below):\n" + "\n".join(f"- {f['common_name']}: {f['excerpt']}" for f in facts)
            if facts else ""
        )

        other_likely = week.get("other_likely_species", [])
        other_likely_line = (
            f"Other species commonly present in this region this time of year that haven't shown "
            f"up this week: {', '.join(other_likely)}. (Real regional data — only mention this if "
            f"it fits naturally, and never claim one of these WAS detected.)"
            if other_likely else ""
        )

        time_pattern = week.get("time_pattern", {})
        time_pattern_line = (
            f"Time-of-day pattern across the week: {', '.join(time_pattern['dawn_concentrated_species'])} "
            f"showed up mostly in the early morning (5-9am), real data across the week's actual "
            f"detections — worth a genuine mention if it fits, not just a list of names."
            if time_pattern.get("dawn_concentrated_species") else ""
        )

        taxonomic = week.get("taxonomic", {})
        taxonomic_line = (
            f"Taxonomic diversity this week: {taxonomic['family_count']} different bird families "
            f"represented ({', '.join(taxonomic['families'].keys())}) — real data, worth "
            f"mentioning if it genuinely adds something."
            if taxonomic.get("family_count") else ""
        )

        focus_angle = random.choice(_FOCUS_ANGLES)
        opening_style = random.choice(_OPENING_STYLES)
        recent_openings = getattr(s, "weekly_summary_recent_openings", None) or []
        recent_openings_block = (
            "Recent weekly entries opened like this — do NOT open the same way, structurally or "
            "in wording, as any of these:\n" + "\n".join(f'- "{o}"' for o in recent_openings)
            if recent_openings else ""
        )

        from .personality import personality_instructions, length_instruction
        depth_value = s.ai_personality_depth if s.ai_personality_depth is not None else 50
        curiosity_value = s.ai_personality_curiosity if s.ai_personality_curiosity is not None else 50
        tone_instructions = personality_instructions(
            friendliness=s.ai_personality_friendliness if s.ai_personality_friendliness is not None else 60,
            informational=s.ai_personality_informational if s.ai_personality_informational is not None else 50,
            irreverence=s.ai_personality_irreverence if s.ai_personality_irreverence is not None else 35,
            depth=depth_value,
            curiosity=curiosity_value,
        )

        # Same locally-run search as daily_summary.py — see that file's
        # matching comment for why this isn't any AI provider's own
        # search tool. A week has a more natural "lead" to search for
        # than a single day does: whichever species is actually
        # newsworthy this week (a real arrival or departure) takes
        # priority over just the top-detected species, since that's
        # genuinely more likely to be worth a real search result.
        web_search_block = ""
        lead_species_candidates = (
            week["first_ever_arrivals"] + week["returning_arrivals"] + week["departures"]
        )
        lead_species = lead_species_candidates[0] if lead_species_candidates else (
            week["top_species"][0][0] if week["top_species"] else None
        )
        if bool(getattr(s, "ai_web_search_enabled", False)) and lead_species:
            try:
                from .web_search import search_web
                results = search_web(f"{lead_species} bird migration seasonal pattern", max_results=2)
                if results:
                    web_search_block = (
                        f"\n\nWeb search results for '{lead_species}' (from a local search, not "
                        "the AI provider's own knowledge — use these if genuinely relevant, ignore "
                        "them if not, and never present a result as something you already knew):\n"
                        + "\n".join(f"- {r['title']}: {r['snippet']}" for r in results)
                    )
            except Exception as e:
                logger.warning("Web search lookup failed (non-fatal, continuing without it): %s", e)

        system_prompt = (
            "You are writing a week-in-review journal entry for a home bird-monitoring system "
            "called Chirp, covering the past 7 days — a real week-in-retrospect a birder might "
            "write closing out their field journal, not a stats digest. Weave in the actual "
            "detection data given to you, real ornithology context, and any genuine arrivals or "
            "departures noted below (only state facts you're actually confident are true — do "
            "not invent statistics or specific numbers beyond what's given).\n\n"
            f"{tone_instructions}\n\n"
            "Lean into real educational substance more than a single day's entry would: this is "
            "a good place to actually explain a term in passing when one comes up naturally "
            "(migration terms like 'passage migrant' or 'nocturnal flight calls', foraging-guild "
            "terms like 'bark-gleaner' or 'aerial insectivore', or similar) — a brief, "
            "plain-language aside, not a glossary entry, and only when it fits, not forced into "
            "every paragraph. A genuine, specific, verifiable fun fact about one of the week's "
            "species is welcome too. All of this sits on top of real, accurate content, never "
            "replaces it, and should never come at a species' expense.\n\n"
            "Arrivals and departures — if the data below shows any, treat them as the real "
            "news they are (see focus instruction below for how much to lead with this). If the "
            "data shows none, don't invent any — a stable week where the same species held "
            "steady is a legitimate, fine thing to report honestly, not a gap to paper over.\n\n"
            "Real data below may also include: a trend comparison against a typical week (use it "
            "plainly if present — a real, computed number; if it says there isn't enough history "
            "yet, don't invent one anyway), real reference facts sourced from Wikipedia (rewrite "
            "these in your own words if you use them — never quote or closely paraphrase the "
            "given wording), other species genuinely common in this region right now that "
            "haven't been detected this week (a real, computed regional likelihood list — fine "
            "to mention as 'birds that could show up' when it fits, never as something that WAS "
            "detected), a real time-of-day pattern across the week (which species were "
            "genuinely concentrated in the early morning across their own actual detections, "
            "computed from real timestamps), and real taxonomic diversity (how many distinct bird "
            "families this week's species actually represent, from real eBird taxonomy data).\n\n"
            f"For THIS entry specifically: {focus_angle}\n\n"
            f"{opening_style}\n\n"
            f"{recent_openings_block}\n\n"
            "Important context: Chirp is a passive acoustic microphone system only — it "
            "listens and identifies birds by sound. It is NOT a bird feeder, birdhouse, or "
            "camera, and you have no information about what feeders, houses, plantings, or "
            "other yard features the person actually has. Never assume or refer to a feeder, "
            "nest box, bath, or specific plants as something they already own or maintain — "
            "phrase anything like that as general advice, not an observation about their yard.\n\n"
            f"{length_instruction(depth_value, short='2 focused paragraphs', normal='3-4 short paragraphs', long='5-6 paragraphs, with real room to teach a concept properly, unpack a trend in depth, or work through more of the real material from this week instead of skimming past it')} "
            "A week has more real material than a single day, so even the normal length can run "
            "a little longer than Daily Journal, but it's still a journal entry to enjoy reading, "
            "not an exhaustive report. Write directly to the reader, second person. Past tense is "
            "appropriate throughout — the week is over. No markdown headers, just prose."
        )
        user_prompt = (
            f"Week covered: {week['date_range_str']}\n"
            f"Location: {week['location_name'] or 'Not set'}\n\n"
            f"Detections this week: {week['total_detections']} total, {week['species_count']} species.\n"
            f"Top species this week:\n{species_lines}\n\n"
            f"Arrivals/departures this week:\n{patterns_block}\n"
            f"{trend_line}\n\n"
            f"{other_likely_line}\n"
            f"{time_pattern_line}\n"
            f"{taxonomic_line}\n"
            f"{facts_block}"
            f"{web_search_block}\n\n"
            "Write the week-in-review entry, matching the focus/opening instructions given."
        )

        from .personality import DEPTH_HIGH, DEPTH_LOW
        max_tokens = 1200 if depth_value > DEPTH_HIGH else (500 if depth_value < DEPTH_LOW else 800)
        text = call_chat_completion(provider, api_key, system_prompt, user_prompt, max_tokens=max_tokens, db=db, feature="weekly_summary")

        s.weekly_summary_text = text
        s.weekly_summary_generated_at = datetime.utcnow()
        s.weekly_summary_period_start = week["period_start_utc"]
        s.weekly_summary_period_end = week["period_end_utc"]
        s.weekly_summary_error = None

        opening_snippet = " ".join(text.split()[:12])
        history = list(getattr(s, "weekly_summary_recent_openings", None) or [])
        history.append(opening_snippet)
        s.weekly_summary_recent_openings = history[-5:]

        db.commit()
        logger.info("Weekly summary generated successfully via %s", provider)

    except Exception as e:
        logger.warning("Weekly summary generation failed: %s", e)
        s.weekly_summary_error = str(e)[:500]
        db.commit()
