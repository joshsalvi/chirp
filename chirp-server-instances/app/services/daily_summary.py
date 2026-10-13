"""
Generates the Dashboard's AI-written daily journal entry — real detection
data, current weather (Open-Meteo), and general ornithology context, in a
short personality-driven summary rather than a stats recap.

Optional and best-effort: no provider assigned means this never runs; a
failed call stores the error on AppSettings.daily_summary_error and the
card just doesn't render. Scheduled by main.py's background loop.
"""

import logging
import random
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

# Picked randomly per generation for real structural variety, rather than
# relying on a "be creative" instruction alone.
_FOCUS_ANGLES = [
    "Lead with a genuine, specific, surprising fun fact about one of today's species — something "
    "most people wouldn't already know — and build the rest of the entry around it.",
    "Focus on how today's weather likely shaped activity — bird behavior really does respond to "
    "conditions like wind, temperature, and pressure, so make a real connection if the data supports it.",
    "Highlight whichever species today was rarest or most unusual for this yard, and spend real "
    "attention on it rather than giving equal weight to everything.",
    "Take a broader view — reflect on what today's overall mix of species suggests about diversity "
    "or the health of the local environment, grounded only in the real data given.",
    "Compare today loosely to what's typical for this time of year, if the data supports a real "
    "seasonal observation — migration timing, breeding season behavior, winter survival strategies.",
    "Give a more conversational, scene-setting account of the day — as if genuinely describing what "
    "it felt like to have these particular birds around today, less list-like, more narrative.",
    "Pick one species from today and give it a bit of character — a nickname, a personality read on "
    "its behavior, a little affectionate ribbing if it's a repeat visitor — grounded in something "
    "real about that species, not just invented whimsy for its own sake.",
    "Imagine the day as a soundscape rather than a list of names — what the yard actually sounded "
    "like, layered and specific, using the real species and timing given rather than generic "
    "'birds chirped' filler.",
    "Notice a genuine contrast or odd juxtaposition in today's mix — the shyest and boldest species "
    "both showing up, an early riser next to a late arrival, a common visitor next to a rare one — "
    "and have a little fun with it without forcing a connection the data doesn't support.",
    "If a real trend comparison against a typical day is given, make that the centerpiece — a "
    "genuinely busier or quieter day than usual is worth digging into: what real, plausible reason "
    "(weather, season, time of year) might explain it, stated as a reasonable possibility, not a "
    "certainty you can't actually verify from the data given.",
    "If real 'other species likely in the region right now' data is given, use it for a genuine "
    "'who else might be around' moment — what a few of today's actual species have in common with "
    "ones that haven't shown up yet (similar habitat, similar season, similar diet), grounded in "
    "the real list given, not invented possibilities.",
]

_OPENING_STYLES = [
    "Open with a specific, concrete observation about one bird or moment — not a general statement "
    "about the day as a whole.",
    "Open with a genuine question a curious birder might actually wonder, then work toward an answer.",
    "Open with a brief, vivid sense of place or weather before getting to the birds.",
    "Open directly with the most interesting fact or observation from today — no throat-clearing.",
    "Open the way you'd start telling a friend about your day, conversationally, mid-thought.",
    "Open with a small, genuine surprise or double-take — something that made you look twice or "
    "smile, before settling into the rest of the entry.",
    "Open with a bit of dry humor or a wry, affectionate aside about a species' behavior — never "
    "mean-spirited, always grounded in something a real birder would actually notice and chuckle at.",
]

import httpx

from .ai_providers import get_feature_config, call_chat_completion

logger = logging.getLogger("chirp.daily_summary")

# Open-Meteo's WMO weather codes, condensed to plain language for the prompt
# — the model doesn't need the numeric code, just a description it can work
# with naturally in a sentence.
_WEATHER_CODE_DESC = {
    0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy with frost", 51: "light drizzle", 53: "drizzle",
    55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 80: "rain showers",
    81: "rain showers", 82: "violent rain showers", 95: "thunderstorms",
}


def _fetch_weather(lat: float, lon: float) -> Optional[dict]:
    """Best-effort current-conditions fetch. Returns None on any failure —
    weather is a nice-to-have in the summary, never a blocker."""
    try:
        resp = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,weather_code,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "timezone": "auto",
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        cur = data.get("current", {})
        daily = data.get("daily", {})
        code = cur.get("weather_code")
        return {
            "temp_f": cur.get("temperature_2m"),
            "wind_mph": cur.get("wind_speed_10m"),
            "condition": _WEATHER_CODE_DESC.get(code, "unclear conditions"),
            "high_f": (daily.get("temperature_2m_max") or [None])[0],
            "low_f": (daily.get("temperature_2m_min") or [None])[0],
        }
    except Exception as e:
        logger.info("Daily summary: weather fetch failed (non-fatal): %s", e)
        return None


def _day_phase(hour: int) -> str:
    """
    Buckets the current local hour into a phase the prompt uses for
    framing, so a morning entry doesn't talk about the day in the past
    tense. Boundaries assume a schedule like 09:00/12:00/15:00/17:00/20:00.
    """
    if hour < 11:
        return "early_morning"
    elif hour < 15:
        return "midday"
    elif hour < 18:
        return "afternoon"
    else:
        return "evening"


_PHASE_INSTRUCTIONS = {
    "early_morning": (
        "It is currently early morning. Write this as the day just getting underway — talk "
        "about what's been heard SO FAR this morning, not the day as a whole (it isn't over). "
        "It's fine to note what you might hope to hear as the day continues, but don't describe "
        "the day in the past tense or as a finished whole."
    ),
    "midday": (
        "It is currently midday. Briefly recap what the morning brought, but frame it as the "
        "morning specifically, not the whole day — there's still an afternoon and evening ahead. "
        "You can note what might still be active later (e.g. some species are more vocal at dusk)."
    ),
    "afternoon": (
        "It is currently mid-to-late afternoon. Most of the day's activity is likely behind you "
        "by now, so this can lean more retrospective than a midday entry — but the day isn't "
        "fully over yet, so avoid language that implies it's completely wrapped up (e.g. 'today "
        "was' rather than 'today has been' or 'so far today')."
    ),
    "evening": (
        "It is evening — write this as a genuine day-in-retrospect, the way a birder would close "
        "out their field journal at the end of the day. Past tense, a full day's arc, is "
        "appropriate here in a way it wouldn't be earlier."
    ),
}


def _gather_today_data(db, tz: ZoneInfo, s=None) -> dict:
    """Pulls today's real detection data — species seen, counts, streaks,
    anything notable — to ground the summary in what actually happened
    rather than the model inventing plausible-sounding specifics.

    s: the caller's already-fetched AppSettings row, if it has one —
    generate_daily_summary always does by the time it calls this, so
    passing it through avoids a second identical query for the same
    single row on every single generation run. Still queries it itself
    if not given, so this stays callable standalone (e.g. from a test)
    without forcing every caller to fetch it first."""
    from ..models import Recording, Detection, AppSettings
    from .wildlife_patterns import get_arrivals_and_departures
    from .journal_enrichment import get_trend_context

    if s is None:
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    min_conf = float(s.min_confidence_display or 0.0) if s else 0.0
    show_deleted = bool(getattr(s, "show_deleted_detections", False)) if s else False

    now_local = datetime.now(ZoneInfo("UTC")).astimezone(tz)
    today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    today_end_utc = now_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    base_filters = [Recording.trigger_timestamp >= today_start_utc, Recording.is_bat.is_(False)]
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
    species_today = sorted(species_counts.items(), key=lambda x: -x[1])

    # Only first-ever arrivals, deliberately not departures — a single
    # day is too noisy a window to call a species "gone" (missing it by
    # chance for one day is completely normal and not a real pattern;
    # see wildlife_patterns.py's own docstring on why departures need a
    # multi-day "regular presence" baseline that a single day can't
    # establish). A genuinely first-ever species today, though, is real
    # regardless of window size — it either has prior history or it doesn't.
    try:
        patterns = get_arrivals_and_departures(db, today_start_utc, today_end_utc)
        first_ever_today = patterns["first_ever_arrivals"]
    except Exception:
        first_ever_today = []

    # Real historical comparison — see journal_enrichment.py's own
    # docstring for why this needs an EXPLICIT period_length (a real
    # bug otherwise: "today so far" is a partial day for anyone running
    # this before midnight, and deriving the baseline window from that
    # partial span instead of a real trailing-4-days window silently
    # broke the whole comparison — caught by testing with actual,
    # checkable expected numbers, not just confirming it runs).
    try:
        trend = get_trend_context(
            db, tz, today_start_utc, timedelta(days=1),
            current_species_count=len(species_counts), current_detection_count=total_detections,
            min_conf=min_conf, show_deleted=show_deleted,
        )
    except Exception as e:
        logger.info("Daily summary: trend computation failed (non-fatal): %s", e)
        trend = {"has_baseline": False}

    # Real, sourced facts for today's top species, and real other-likely
    # species from the same regional data Field Guide uses — both
    # wrapped defensively, same "never let an enrichment nice-to-have
    # block the whole summary" principle as the weather fetch above.
    try:
        from .journal_enrichment import get_species_facts, get_other_likely_species, get_time_of_day_pattern, get_taxonomic_diversity
        top_names = [name for name, _ in species_today[:5]]
        species_facts = get_species_facts(db, top_names, max_species=2)
        other_likely = get_other_likely_species(db, set(species_counts.keys()), max_species=5)
        time_pattern = get_time_of_day_pattern(db, today_start_utc, today_end_utc, min_conf=min_conf, show_deleted=show_deleted)
        taxonomic = get_taxonomic_diversity(db, set(species_counts.keys()))
    except Exception as e:
        logger.info("Daily summary: species facts/likely-species/time-pattern/taxonomic lookup failed (non-fatal): %s", e)
        species_facts, other_likely, time_pattern, taxonomic = [], [], {}, {}

    return {
        "date_local": now_local.strftime("%A, %B %d"),
        "time_local": now_local.strftime("%-I:%M %p"),
        "phase": _day_phase(now_local.hour),
        "total_detections": total_detections,
        "species_count": len(species_counts),
        "top_species": species_today[:8],   # cap what goes in the prompt — a long tail doesn't add value
        "first_ever_today": first_ever_today,
        "location_name": s.location_name if s else None,
        "latitude": s.latitude if s else None,
        "longitude": s.longitude if s else None,
        "trend": trend,
        "species_facts": species_facts,
        "other_likely_species": other_likely,
        "time_pattern": time_pattern,
        "taxonomic": taxonomic,
    }


def generate_daily_summary(db) -> None:
    """
    Generates today's summary and stores it on AppSettings, or stores an
    error and leaves any previous summary in place — a failed regeneration
    attempt shouldn't blank out a still-valid entry from earlier today.
    """
    from ..models import AppSettings

    config = get_feature_config("daily_summary", db)
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
        today = _gather_today_data(db, tz, s)
        weather = _fetch_weather(today["latitude"], today["longitude"]) if today["latitude"] and today["longitude"] else None

        species_lines = "\n".join(f"- {name}: {count} detection{'s' if count != 1 else ''}" for name, count in today["top_species"]) or "- (nothing detected yet today)"
        weather_line = (
            f"Current conditions: {weather['condition']}, {weather['temp_f']}°F (today's range {weather['low_f']}–{weather['high_f']}°F), wind {weather['wind_mph']} mph."
            if weather else "Weather data unavailable today."
        )

        # Real historical comparison — only included when there's
        # actually enough history to compare against (a brand-new
        # install has nothing honest to compare to yet, and the prompt
        # instructs the model accordingly rather than silently omitting
        # this and letting it guess at "typical").
        trend = today.get("trend", {})
        if trend.get("has_baseline"):
            trend_line = (
                f"Trend vs. the typical day (average of the last {trend['baseline_periods']} days before today): "
                f"{today['species_count']} species today vs. a typical {trend['avg_species']} "
                f"({'+' if trend['species_delta'] >= 0 else ''}{trend['species_delta']}); "
                f"{today['total_detections']} detections today vs. a typical {trend['avg_detections']} "
                f"({'+' if trend['detections_delta'] >= 0 else ''}{trend['detections_delta']})."
            )
        else:
            trend_line = "Not enough history yet to compare today against a typical day — don't invent a trend claim."

        # Real, sourced facts (Wikipedia via BirdProfile.description) —
        # explicitly marked for paraphrasing, never verbatim reproduction,
        # matching this project's own copyright discipline elsewhere.
        facts = today.get("species_facts", [])
        facts_block = (
            "\n\nReal reference facts (from Wikipedia, via this species' own profile — put these "
            "IN YOUR OWN WORDS if you use them, never quote or closely paraphrase the wording "
            "below):\n" + "\n".join(f"- {f['common_name']}: {f['excerpt']}" for f in facts)
            if facts else ""
        )

        # Real Field Guide-style "other likely species" — genuinely
        # computed from the same regional monthly-likelihood data the
        # Field Guide/regional-library feature uses, not invented.
        other_likely = today.get("other_likely_species", [])
        other_likely_line = (
            f"Other species commonly present in this region this time of year that haven't shown "
            f"up yet: {', '.join(other_likely)}. (Real regional data — only mention this if it "
            f"fits naturally, and never claim one of these WAS detected today.)"
            if other_likely else ""
        )

        # Real composition/"landscape" commentary, distinct from
        # per-species facts — which species' own actual detections were
        # concentrated in the early-morning window today, computed from
        # real timestamps, not textbook dawn-chorus assumptions.
        time_pattern = today.get("time_pattern", {})
        time_pattern_line = (
            f"Time-of-day pattern: {', '.join(time_pattern['dawn_concentrated_species'])} showed up mostly in the "
            f"early morning (5-9am) today, real data — worth a genuine mention if it fits, not "
            f"just a list of names."
            if time_pattern.get("dawn_concentrated_species") else ""
        )

        # Real taxonomic diversity — a genuinely different "landscape"
        # fact from species-count: how many distinct bird families
        # today's species actually represent, real data from eBird
        # taxonomy, not invented.
        taxonomic = today.get("taxonomic", {})
        taxonomic_line = (
            f"Taxonomic diversity today: {taxonomic['family_count']} different bird families "
            f"represented ({', '.join(taxonomic['families'].keys())}) — real data, worth "
            f"mentioning if it genuinely adds something (a notably diverse or notably narrow mix "
            f"is worth a comment; a middling number usually isn't worth dwelling on)."
            if taxonomic.get("family_count") else ""
        )

        # Pick a distinct focus/opening each time, and show recent
        # openings so the model has something concrete to not repeat.
        focus_angle = random.choice(_FOCUS_ANGLES)
        opening_style = random.choice(_OPENING_STYLES)
        recent_openings = getattr(s, "daily_summary_recent_openings", None) or []
        recent_openings_block = (
            "Recent entries opened like this — do NOT open the same way, structurally or "
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

        # Locally-run web search (services/web_search.py) — not any AI
        # provider's own built-in search tool, so this works the same
        # way regardless of which provider is assigned, and doesn't
        # depend on any AI vendor's infrastructure. Chirp's own code
        # decides what to search for (today's single most notable
        # species, see below) rather than leaving that choice to the
        # model — same grounding principle as everything else fed into
        # this prompt: real data in, not an open-ended request to go
        # look something up.
        web_search_block = ""
        if bool(getattr(s, "ai_web_search_enabled", False)) and today["top_species"]:
            try:
                from .web_search import search_web
                lead_species = today["first_ever_today"][0] if today["first_ever_today"] else today["top_species"][0][0]
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
            "You are writing a short, warm daily journal entry for a home bird-monitoring "
            "system called Chirp, written in the voice of an enthusiastic, knowledgeable birder "
            "keeping a personal field journal — not a dry stats report. Weave in the actual "
            "detection data given to you, the weather, and genuine, accurate ornithology facts "
            "or seasonal context relevant to the species mentioned (only state facts you're "
            "actually confident are true — do not invent statistics or specific numbers about "
            "a species that weren't given to you).\n\n"
            f"{tone_instructions} Vivid and specific sensory language over generic phrasing "
            "('a Carolina Wren hollering from the hedge' beats 'birds were singing') is always "
            "welcome regardless of the settings above. Personality should sit on top of real, "
            "accurate content, never replace it, and should never come at a species' expense.\n\n"
            "Bring real educational substance, not just mood — when a natural moment arises, "
            "briefly explain a term in plain language (e.g. what a 'nocturnal flight call' is, "
            "what an 'irruption' means, why a species might be called a 'short-distance "
            "migrant') or share one genuine, specific, verifiable fact about a species "
            "mentioned. A brief aside, not a glossary entry — and only when it actually fits, "
            "not forced into every single line.\n\n"
            "Real data below may include: a trend comparison against a typical day (use it "
            "plainly if present — a real, computed number, not your own estimate of what's "
            "'usual'; if it says there isn't enough history yet, don't invent a trend anyway), "
            "real reference facts sourced from Wikipedia (rewrite these in your own words if "
            "you use them — never quote or closely paraphrase the given wording), other "
            "species genuinely common in this region right now that haven't been detected yet "
            "(a real, computed regional likelihood list — fine to mention as 'birds that could "
            "show up' when it fits naturally, never as something that WAS detected), a "
            "real time-of-day pattern (which of today's actual species were genuinely "
            "concentrated in the early morning, computed from real timestamps — a real "
            "observation about today specifically, not a general claim about what that species "
            "usually does), and real taxonomic diversity (how many distinct bird families today's "
            "species actually represent, from real eBird taxonomy data — a genuinely diverse or "
            "genuinely narrow mix is worth noting, a middling number usually isn't).\n\n"
            f"{_PHASE_INSTRUCTIONS[today['phase']]}\n\n"
            f"For THIS entry specifically: {focus_angle}\n\n"
            f"{opening_style}\n\n"
            f"{recent_openings_block}\n\n"
            "Important context: Chirp is a passive acoustic microphone system only — it "
            "listens and identifies birds by sound. It is NOT a bird feeder, birdhouse, or "
            "camera, and you have no information about what feeders, houses, plantings, or "
            "other yard features the person actually has. Never assume or refer to a feeder, "
            "nest box, bath, or specific plants as something they already own or maintain — "
            "phrase anything like that as general advice ('if you'd like to attract more "
            "orioles, they're drawn to...'), not an observation about their yard.\n\n"
            "When it fits naturally (not necessarily every entry), you can:\n"
            "- Offer a genuine, specific tip related to today's species for attracting or "
            "supporting birds — food preferences, plantings, water, nesting habits — framed "
            "as suggestions, not assumptions about what's already there.\n"
            "- Reflect on what today's mix of species suggests about diversity or the health "
            "of the local environment (e.g. a good range of species/foraging guilds is a "
            "healthy sign; an unusual gap or an invasive species showing up heavily is worth "
            "a gentle, non-alarmist mention) — grounded only in the actual detections given, "
            "not invented trend claims.\n"
            "- If a species below is flagged as a first-ever detection, that's real news — "
            "worth genuine attention, not a passing mention buried in a list.\n\n"
            f"{length_instruction(depth_value, short='1-2 short paragraphs', normal='2-3 short paragraphs', long='4-5 paragraphs, with real room to teach a concept properly or unpack a trend instead of just naming it')} "
            "Write directly to the reader, second person, present tense. No markdown headers, just prose."
        )
        first_ever_line = (
            f"First-ever species detected here, today: {', '.join(today['first_ever_today'])}\n"
            if today.get("first_ever_today") else ""
        )
        user_prompt = (
            f"Date: {today['date_local']}\n"
            f"Current local time: {today['time_local']}\n"
            f"Location: {today['location_name'] or 'Not set'}\n"
            f"{weather_line}\n\n"
            f"Detections so far today: {today['total_detections']} total, {today['species_count']} species.\n"
            f"Top species so far today:\n{species_lines}\n\n"
            f"{trend_line}\n\n"
            f"{other_likely_line}\n\n"
            f"{time_pattern_line}\n\n"
            f"{taxonomic_line}\n\n"
            f"{first_ever_line}"
            f"{facts_block}"
            f"{web_search_block}\n\n"
            "Write the journal entry for right now, matching the time-of-day framing and "
            "the specific focus/opening instructions given."
        )

        # A longer requested entry genuinely needs more token budget —
        # without this, a "high" depth setting could get the model
        # cut off mid-sentence by the OLD fixed 600-token cap, silently
        # producing a truncated entry instead of the fuller one asked for.
        from .personality import DEPTH_HIGH, DEPTH_LOW
        max_tokens = 900 if depth_value > DEPTH_HIGH else (400 if depth_value < DEPTH_LOW else 600)
        text = call_chat_completion(provider, api_key, system_prompt, user_prompt, max_tokens=max_tokens, db=db, feature="daily_summary")

        s.daily_summary_text = text
        s.daily_summary_generated_at = datetime.utcnow()
        s.daily_summary_error = None

        # Update the rolling anti-repetition history — first ~12 words as
        # a lightweight fingerprint of how this entry opened, keeping the
        # last 5 so this doesn't grow unbounded.
        opening_snippet = " ".join(text.split()[:12])
        history = list(getattr(s, "daily_summary_recent_openings", None) or [])
        history.append(opening_snippet)
        s.daily_summary_recent_openings = history[-5:]

        db.commit()
        logger.info("Daily summary generated successfully via %s", provider)

    except Exception as e:
        logger.warning("Daily summary generation failed: %s", e)
        s.daily_summary_error = str(e)[:500]
        db.commit()
