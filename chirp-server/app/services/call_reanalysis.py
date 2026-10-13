"""
On-demand AI second opinion on a bird call — shows the model the
recording's spectrogram and asks whether it's consistent with the
current identification, the same vision-based approach photo_id.py uses
for bird photos. A sanity check against the BirdNET detection, not a
replacement for it.

Not scheduled — only runs when a user clicks "Re-check this call" on a
specific recording.

Substantially rebuilt from the original version, which gave the model
almost nothing to work with (species name + confidence number) and
asked for a vague, hedgy 2-3 sentence paragraph with no real structure
— genuinely hard to act on, and easy to skim past without a clear
takeaway. Two real, concrete improvements:

1. Real regional/seasonal plausibility grounding — the same
   RegionalSpecies monthly-likelihood data Field Guide and the AI
   journal already use, given to the model as an actual computed fact
   ("this species has X% likelihood for this region this month") rather
   than left for the model to guess at from its own general knowledge of
   range maps.
2. A real, structured response instead of free-form prose: the model is
   asked to lead with one of three exact words (CONSISTENT /
   INCONSISTENT / UNCERTAIN), which gets parsed into
   Recording.ai_reanalysis_verdict so the frontend can show a clear
   badge — the actual conclusion visible at a glance, not buried in a
   paragraph — followed by specific reasoning that has to reference
   real acoustic/visual features (frequency range, harmonic structure,
   call rhythm/duration), not just a restated confidence-adjacent
   hedge.
"""

import logging
import re
from datetime import datetime

from .ai_providers import get_feature_config, call_vision_completion

logger = logging.getLogger("chirp.call_reanalysis")

# BIRDS / NONE: the survey of a recording with no shown detections.
_VALID_VERDICTS = {"CONSISTENT", "INCONSISTENT", "UNCERTAIN", "BIRDS", "NONE"}


def _parse_verdict(text: str) -> tuple:
    """
    Extracts the leading verdict word and returns (verdict, remaining_text).
    verdict is lowercased ("consistent"/"inconsistent"/"uncertain") for
    storage, or None if the model didn't actually lead with one of the
    three exact words asked for — a real, deliberately-permissive
    fallback rather than raising, since a model occasionally not
    following the exact format shouldn't turn into a hard failure for
    what's still a genuinely useful note; it just won't get a badge.
    """
    stripped = text.strip()
    first_word = stripped.split(None, 1)[0].rstrip(":.,").upper() if stripped else ""
    if first_word in _VALID_VERDICTS:
        remainder = stripped[len(first_word):].lstrip(":.,- \n")
        return first_word.lower(), remainder
    return None, stripped


def _get_regional_plausibility(db, common_name: str) -> str:
    """
    Real, computed regional/seasonal plausibility for this species right
    now — the same live monthly-likelihood data (with the same
    recompute-from-the-stored-12-month-array fix already proven correct
    in birds.py's own regional-library endpoint, not a possibly-stale
    cached current_likelihood column) used elsewhere in this project.
    Returns an empty string if RegionalSpecies hasn't been synced yet or
    this species has no match — a real, honest "nothing to say here"
    rather than a fabricated claim either way.
    """
    from ..models import RegionalSpecies

    try:
        row = db.query(RegionalSpecies).filter(RegionalSpecies.common_name == common_name).first()
    except Exception:
        return ""
    if not row:
        return ""

    current_month_index = datetime.utcnow().month - 1
    likelihood = (
        row.monthly_frequency[current_month_index]
        if row.monthly_frequency and len(row.monthly_frequency) == 12
        else (row.current_likelihood or 0.0)
    )

    if likelihood >= 0.3:
        band = "commonly reported"
    elif likelihood >= 0.05:
        band = "occasionally reported"
    elif likelihood > 0:
        band = "rarely reported"
    else:
        band = "essentially never reported"

    month = datetime.utcnow().strftime("%B")
    line = (
        f"Regional context (eBird, this area, {month}): {common_name} is {band} "
        f"(about {likelihood * 100:.0f}% relative frequency)."
    )
    if likelihood < 0.05:
        line += (" Rare here this month: answer CONSISTENT only if a clearly "
                 "species-typical call shape is visible; otherwise UNCERTAIN.")
    return line


def _get_bat_grounding_context(recording) -> str:
    """
    Real, computed pulse-train statistics from bat_detector.py's own
    on-device analysis (pulse_count, peak_freq_hz, mean_pulse_duration_ms,
    swept_fraction — see Recording.bat_metadata's own column comment in
    models.py for the full field list) formatted as grounding facts for
    the model, the same "give it real computed numbers, don't make it
    guess" approach _get_regional_plausibility() above uses for birds.
    Returns an empty string if bat_metadata is missing entirely (an
    older recording from before this field existed, or the device-side
    computation itself failed) — an honest gap, not a fabricated one.
    """
    meta = recording.bat_metadata or {}
    if not meta:
        return ""

    parts = []
    if meta.get("peak_freq_hz"):
        parts.append(f"peak frequency {meta['peak_freq_hz'] / 1000:.1f} kHz")
    if meta.get("mean_pulse_duration_ms"):
        parts.append(f"mean pulse duration {meta['mean_pulse_duration_ms']:.1f} ms")
    if meta.get("pulse_count"):
        parts.append(f"{meta['pulse_count']} pulses detected")
    if meta.get("swept_fraction") is not None:
        parts.append(f"frequency-swept fraction {meta['swept_fraction']:.0%} "
                      f"(higher = more FM sweep character, lower = more flat/CF character)")
    if not parts:
        return ""

    lines = ["On-device pulse-detection measurements (real computed values, not a guess): " + ", ".join(parts) + "."]

    # species_guess, when present, is the SEPARATE BattyBirdNET-based
    # classifier's own output (see bat_species_classifier.py) — surfaced
    # here as additional real context, not as something to just defer
    # to uncritically; its own known accuracy caveats (confusable Myotis
    # species, occasional silence misclassified with high confidence)
    # are exactly why a second, independent vision-based opinion on the
    # spectrogram itself has real value here, same as for birds.
    guess = meta.get("species_guess") or {}
    top_sp = guess.get("top_species")
    if top_sp and top_sp.get("common_name"):
        lines.append(
            f"A separate automated classifier (BattyBirdNET, trained on NABat data) "
            f"suggests {top_sp['common_name']} at {round(top_sp.get('confidence', 0) * 100)}% "
            f"confidence — known to sometimes confuse acoustically similar Myotis species "
            f"and occasionally misclassify silence/noise, so treat this as one more data "
            f"point, not a settled answer."
        )
    return "\n".join(lines)


def _reanalyze_bat_call(db, recording, top, proc, provider, api_key) -> str:
    """
    Bat-echolocation branch of reanalyze_call() below. Genuinely
    different framing from the bird path, not just a different prompt
    with the same shape: a bat Recording's Detection.common_name is
    "Bat" (generic) unless the separate BattyBirdNET classifier
    confidently asserted a real species (see _process_bat_recording_bg
    in api/recordings.py) — so "is this call consistent with the
    claimed species" doesn't apply the same way it does for a BirdNET
    call, which always names a specific species. The more fundamental
    and more often useful question for a bat recording is whether the
    spectrogram shows genuine echolocation at all, versus a false
    positive from wind, insects, or electrical noise — bat_detector.py's
    on-device pulse-rate/FM-sweep filters already reject most of that,
    but they're heuristics, not certainty. When a species WAS
    confidently asserted, the model is additionally asked to weigh in
    on that specific claim.

    Returns the generated PNG path's directory is NOT returned — like
    the bird path, this function has no return value; kept as a
    function (not inlined into reanalyze_call) purely for readability,
    matching the same reasoning as _process_bat_recording_bg's own
    "two pipelines diverge almost entirely" split.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        png_path = proc.generate_bat_spectrogram(recording.wav_path, tmpdir, recording.id)
        with open(png_path, "rb") as f:
            image_bytes = f.read()

    has_species = bool(top.common_name) and top.common_name != "Bat"
    grounding = _get_bat_grounding_context(recording)

    system_prompt = (
        "You are giving a useful second opinion on an ultrasonic bat-echolocation "
        "spectrogram from a home acoustic-monitoring system. This is NOT a bird call — the "
        "y-axis is linear frequency in kHz (not the mel scale used for bird spectrograms), "
        "typically spanning 0-96 kHz, since bat calls run from roughly 9 kHz to over 150 kHz, "
        "well above human hearing. An on-device pulse detector already flagged this as a "
        "likely echolocation call using real-time heuristics (pulse rate, FM-sweep fraction, "
        "time-of-day gating) — you're a sanity check on that flag using the full "
        "spectrogram image, not a replacement for it.\n\n"
        + ("A separate classifier has additionally suggested a specific species for this call "
           "(see below) — weigh in on whether the spectrogram's pulse shape is plausible for "
           "that claim specifically, in addition to the general genuine-echolocation question.\n\n"
           if has_species else
           "No species has been confidently identified for this call — don't guess at one "
           "yourself; focus on whether this is genuine bat echolocation at all.\n\n")
        + "Respond in this exact structure:\n"
        "Line 1: exactly one word — CONSISTENT (the spectrogram looks like bat "
        "echolocation" + (", plausibly consistent with the suggested species" if has_species else "")
        + "), INCONSISTENT (it doesn't — likely a false positive from wind, insects, "
        "electrical/mechanical noise, or a bird/other animal instead — state which, if you can "
        "tell), or UNCERTAIN (ambiguous from the spectrogram alone, which is a "
        "legitimate answer, not a cop-out).\n"
        "Then 2-4 sentences of reasoning, referencing SPECIFIC visual features you can "
        "see: whether pulses show a clear frequency sweep (FM, sloping down through "
        "time) or a flat constant-frequency (CF) component, the pulse repetition rate and "
        "regularity, pulse duration, and how many pulses are visible in the clip. Ground your "
        "reasoning in what's visible in THIS image, not in the on-device measurements "
        "alone — those are given as context, not as something to just restate.\n"
        + ("Bold the species name (**Species Name**) the first time you mention it.\n" if has_species else "")
        + "Finish with one short final sentence or two, starting with **Overall:**, that "
        "restates your bottom-line take in plain terms — someone skimming only that "
        "last line should still get the gist.\n"
        "No bullet points, no headers, no other markdown beyond the bold species name "
        "(if any) and the Overall line — plain prose otherwise."
    )
    species_line = f"Automated species suggestion: {top.common_name}.\n\n" if has_species else ""
    user_prompt = (
        f"{species_line}"
        f"{grounding}\n\n"
        "Give your second opinion on this ultrasonic spectrogram, following the exact structure above."
    )

    return call_vision_completion(
        provider, api_key, system_prompt, user_prompt, image_bytes, _image_type(image_bytes),
        max_tokens=400, db=db, feature="call_reanalysis",
    )


# A species heading the model sometimes garbles: the name repeated inside
# its own likelihood ("**Blue Jay** (likelihood **Blue Jay** (likelihood
# 85%)") or the likelihood inside the bold ("**Blue Jay (likelihood 85%)**").
_LIKELIHOOD_REPEAT_RE = re.compile(
    r"\(\s*likelihood\s+(?:\*\*)?[A-Z][^()\n*]{0,60}?(?:\*\*)?\s*(?=\(\s*likelihood\s*\d)", re.I)
_LIKELIHOOD_INSIDE_BOLD_RE = re.compile(
    r"\*\*([^*\n]{2,60}?)\s*\(\s*likelihood\s*(\d{1,3})\s*%\s*\)\s*\*\*", re.I)
_LIKELIHOOD_RE = re.compile(r"\(\s*likelihood\s*(\d{1,3})\s*%\s*\)", re.I)
_SECTION_RE = re.compile(r"^\s*\*\*\s*(Overall|Other species detected|Also visible|Audio check|Measured check)\b", re.I)


def _tidy_note(text: str, multi_species: bool = False) -> str:
    """Clean up the model's species headings and, for a multi-species
    note, drop the opening summary paragraph that only repeats the
    per-species paragraphs and Overall."""
    if not text:
        return text
    text = _LIKELIHOOD_INSIDE_BOLD_RE.sub(lambda m: f"**{m.group(1).strip()}** (likelihood {m.group(2)}%)", text)
    text = _LIKELIHOOD_REPEAT_RE.sub("", text)
    text = _LIKELIHOOD_RE.sub(lambda m: f"(likelihood {m.group(1)}%)", text)
    if not multi_species:
        return text
    verdict, rest = _parse_verdict(text)
    head = text[:len(text) - len(rest)] if verdict else ""
    paras = re.split(r"\n\s*\n", rest.strip())
    first_species = next((i for i, para in enumerate(paras)
                          if para.lstrip().startswith("**") and not _SECTION_RE.match(para)), None)
    if first_species:
        paras = paras[first_species:]
    body = "\n\n".join(paras)
    if not head:
        return body
    return head.rstrip(" :.,-\n") + "\n\n" + body



def tidy_stored_note(text):
    """_tidy_note for a note already saved (verdict word removed): fixes
    headings, and drops an opening summary when two or more species
    paragraphs follow it. Applied when serving every note, so ones saved earlier read the same."""
    if not text:
        return text
    text = _rewrite_legacy_measured(text)
    heads = sum(1 for para in re.split(r"\n\s*\n", text)
                if para.lstrip().startswith("**") and not _SECTION_RE.match(para))
    return _tidy_note(text, multi_species=heads >= 2)

def _strip_truncated_trailing_section(text: str) -> str:
    """
    Reported directly, twice now, with screenshots each time. First
    report: a response ending in a bare, empty "**Other species
    detected:**Also visible:" — both headers present, no content after
    either, from Ollama's local thinking models occasionally still
    exhausting their token budget (see ai_providers.py's own comments)
    partway through the LAST section of an already-long multi-species
    response. That version of this function only ever checked the
    single LAST marker in the text, which fixed that exact case but
    missed a second, different one: three headers stacked up —
    "**Other species detected:****Also visible:**Other species
    detected:" — where the first two are empty (nothing between
    consecutive markers) but the THIRD one goes on to have real content
    after it. Checking only the last marker's own trailing content
    finds that real content and leaves the whole mangled stack alone,
    including the two empty ones earlier in it. This version checks
    every marker's own gap to the NEXT marker (or end of string) and
    drops just the empty ones, wherever they fall, not only a trailing
    one — which also fixes the visible symptom on screen: adjacent
    "**heading:****heading:**" with no space between a closing and
    reopening ** pair renders as literal asterisks in this app's
    lightweight markdown, not two separate bold spans, so removing the
    empty ones removes that visual glitch as a side effect, not just
    the empty-looking header itself.
    """
    import re
    markers = list(re.finditer(r"\*\*(Other species detected|Also visible):\*\*", text))
    if not markers:
        return text
    # Walk right-to-left so removing one marker's span never shifts the
    # character offsets of markers still to be checked.
    for i in range(len(markers) - 1, -1, -1):
        marker = markers[i]
        gap_end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        gap_content = text[marker.end():gap_end].strip()
        if len(gap_content) < 20:
            text = text[:marker.start()] + text[gap_end:]
    return text.rstrip()


def _measure_pulses(wav_path: str) -> list:
    """Best-effort call to audio_processor.detect_periodic_tonal_pulses."""
    try:
        from .audio_processor import detect_periodic_tonal_pulses
        return detect_periodic_tonal_pulses(wav_path)
    except Exception as e:
        logger.warning("Periodic pulse measurement failed for %s: %s", wav_path, e)
        return []


# A pulse at least this tall on the spectrogram, and this short, is a chip
# (Eastern Chipmunk, a bird's chip note, tapping), not an insect or beep.
# Measured: chipmunk chips 2.3 kHz tall and 32 ms long; Snowy Tree Cricket
# 47-258 Hz and 117-144 ms; Gray Treefrog trill 656 Hz.
CHIP_MIN_SPAN_HZ = 1500
CHIP_MAX_MS = 80


def _is_chip(p: dict) -> bool:
    return (p.get("span_hz") or 0) >= CHIP_MIN_SPAN_HZ and 0 < (p.get("pulse_ms") or 999) <= CHIP_MAX_MS


def _describe_pulse(p: dict) -> str:
    rate = 1.0 / p["period_s"] if p["period_s"] else 0
    timing = (f"repeating every {p['period_s']:.2f} s (about {rate:.1f} per second) across "
              f"{round(p['coverage'] * 100)}% of the recording")
    if _is_chip(p):
        return (f"short chips about {p['pulse_ms']} ms long spanning "
                f"{p['low_hz'] / 1000:.1f}\u2013{p['high_hz'] / 1000:.1f} kHz, {timing}")
    span = f" (about {p['span_hz']} Hz wide)" if p.get("span_hz") is not None else ""
    return f"a narrowband sound at about {p['freq_hz'] / 1000:.1f} kHz{span} {timing}"


def _pulse_source(p: dict) -> str:
    if _is_chip(p):
        return ("most likely an Eastern Chipmunk's chip call (a steady series of short chips "
                "several kHz tall, often for minutes), or a bird repeating a chip note")
    return "likely an insect such as a cricket or katydid, or a mechanical beep"


def _pulse_hint(pulses: list) -> str:
    """Measured signal-analysis note appended to the user prompt."""
    if not pulses:
        return ""
    parts = []
    for p in pulses[:3]:
        if _is_chip(p):
            parts.append(_describe_pulse(p) + ". These are tall, thin vertical streaks, "
                         "not a narrow band: insects and beeps make a narrow, constant-pitch "
                         "band; a series like this is " + _pulse_source(p))
        else:
            parts.append(_describe_pulse(p) + ", a row of short, evenly spaced marks at one "
                         "height, " + _pulse_source(p))
    return (
        "\n\nSignal analysis (an automatic measurement of the audio, separate "
        "from BirdNET) found: " + "; ".join(parts) + ". Check the image for it and "
        "describe it under **Also visible:** (or, if a bird, under **Other species "
        "detected:**), naming the most likely source with a likelihood. If it isn't "
        "visible, say so there."
    )


_PULSE_WORDS = ("insect", "cricket", "katydid", "cicada", "chirp", "pulse", "dash",
                "rhythm", "repeat", "periodic", "evenly spaced", "beep", "chipmunk", "chip")
_NEGATIONS = ("no ", "not ", "none", "without", "absent", "n't", "nothing")


def _mentions_pulses(paragraph: str) -> bool:
    """True if some sentence positively describes the pulse. A sentence like
    'no insect buzzing or mechanical rhythms are visible' names the right
    words but denies them, so negated sentences don't count."""
    import re
    for sentence in re.split(r"(?<=[.!?])\s+", paragraph.lower()):
        if any(w in sentence for w in _PULSE_WORDS) and not any(n in sentence for n in _NEGATIONS):
            return True
    return False


def _ensure_pulses_reported(text: str, pulses: list) -> str:
    """
    A measured periodic pulse is surfaced even when the vision model
    overlooks it or says nothing like it is visible — that exact miss
    prompted the measurement. Leaves the text alone if Also visible
    already describes it; otherwise adds the measured description there.
    """
    if not pulses:
        return text
    desc = _describe_pulse(pulses[0]) + ", " + _pulse_source(pulses[0]) + "."
    if _is_chip(pulses[0]) and "chipmunk" in text.lower():
        return text
    marker = "**Also visible:**"
    idx = text.find(marker)
    if idx == -1:
        return text.rstrip() + "\n\n" + marker + " Measured in the audio: " + desc
    body = text[idx + len(marker):]
    nxt = body.find("\n\n**")
    para = body if nxt == -1 else body[:nxt]
    if _mentions_pulses(para):
        return text
    lead = "Measured in the audio, though: " if any(n in para.lower() for n in _NEGATIONS) \
        else "Also measured in the audio: "
    end = idx + len(marker) + len(para)
    return text[:end].rstrip() + " " + lead + desc + text[end:]


def _measure_background(wav_path: str, detections) -> dict:
    """Best-effort call to audio_processor.measure_background_sounds."""
    try:
        from .audio_processor import measure_background_sounds
        return measure_background_sounds(
            wav_path, [(d.start_time, d.end_time, d.common_name) for d in detections])
    except Exception as e:
        logger.warning("Background sound measurement failed for %s: %s", wav_path, e)
        return {"bursts": [], "bands": [], "rumble_db": None}


def _khz(hz: float) -> str:
    return f"{hz / 1000:.1f}"


def _describe_bursts(bursts: list) -> str:
    times = ", ".join(f"{b['t']:.1f}" for b in bursts[:8]) + (" …" if len(bursts) > 8 else "")
    lo = min(b["low_hz"] for b in bursts)
    hi = sorted(b["high_hz"] for b in bursts)[len(bursts) // 2]
    durs = sorted(b["dur"] for b in bursts)
    dur = (f"about {durs[0]:.2f} s" if durs[-1] - durs[0] < 0.05
           else f"{durs[0]:.2f}\u2013{durs[-1]:.2f} s")
    return (f"{len(bursts)} short loud broadband burst{'s' if len(bursts) != 1 else ''} "
            f"({dur} long, energy from about {_khz(lo)} to "
            f"{_khz(hi)} kHz) at {times} s")


def _describe_band(b: dict) -> str:
    return (f"a steady band at about {_khz(b['low_hz'])}\u2013{_khz(b['high_hz'])} kHz, "
            f"{b['prominence_db']:.0f} dB above the background, present through "
            f"{round(b['coverage'] * 100)}% of the recording")


def _background_hint(bg: dict) -> str:
    """Measured non-bird sounds for the user prompt."""
    parts = []
    if bg.get("bursts"):
        inside = sorted({b["in_box"] for b in bg["bursts"] if b.get("in_box")})
        parts.append(
            "Signal analysis also found " + _describe_bursts(bg["bursts"]) + ". On the "
            "spectrogram these are tall vertical smears or stacks of harmonics covering "
            "a wide frequency range at once. That shape fits a dog bark (a harsh harmonic "
            "stack starting around 0.5 kHz, often repeated in quick succession), another "
            "mammal call, a human voice, or a knock; harsh bird calls such as crows, "
            "jays or ducks can look similar, so judge the shape."
            + (f" Some fall inside the boxes for {', '.join(inside)}: say whether those "
               "boxes hold the bird or this sound." if inside else "")
            + " Describe them under **Also visible:** with their times and what they "
            "most likely are.")
    for b in bg.get("bands") or []:
        parts.append(
            "Signal analysis also found " + _describe_band(b) + ". On the spectrogram "
            "this is a continuous horizontal band at that height across the image, "
            "typically an insect chorus (cicadas, katydids, crickets), an electrical "
            "or mechanical whine, or hiss. Describe it under **Also visible:** with its "
            "frequency range, separately from any low-frequency rumble.")
    return ("\n\n" + "\n\n".join(parts)) if parts else ""


_BURST_WORDS = ("bark", "dog", "mammal", "burst", "voice", "knock", "bang", "broadband",
                "yelp", "howl", "vertical")
_BAND_WORDS = ("buzz", "hum", "whine", "hiss", "chorus", "insect", "cicada", "katydid",
               "cricket", "band", "drone", "tone", "electrical")


def _mentions(paragraph: str, words: tuple, near_hz=None) -> bool:
    """Some non-negated sentence uses one of words (and, with near_hz, a
    kHz figure within 1.5 kHz of it, so a rumble line doesn't count as
    describing a 6 kHz buzz)."""
    import re
    for sentence in re.split(r"(?<=[.!?])\s+", paragraph.lower()):
        if not any(w in sentence for w in words) or any(n in sentence for n in _NEGATIONS):
            continue
        if near_hz is None:
            return True
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:\u2013|-|to)?\s*(\d+(?:\.\d+)?)?\s*khz", sentence):
            vals = [float(v) * 1000 for v in m.groups() if v]
            if any(abs(v - near_hz) <= 1500 for v in vals):
                return True
    return False


def _append_also_visible(text: str, addition: str) -> str:
    marker = "**Also visible:**"
    idx = text.find(marker)
    if idx == -1:
        # before a trailing Audio check, else at the end
        return text.rstrip() + "\n\n" + marker + " " + addition
    body = text[idx + len(marker):]
    nxt = body.find("\n\n**")
    end = idx + len(marker) + (len(body) if nxt == -1 else nxt)
    return text[:end].rstrip() + " " + addition + text[end:]


def _also_visible_para(text: str) -> str:
    marker = "**Also visible:**"
    idx = text.find(marker)
    if idx == -1:
        return ""
    body = text[idx + len(marker):]
    nxt = body.find("\n\n**")
    return body if nxt == -1 else body[:nxt]


def _ensure_background_reported(text: str, bg: dict) -> str:
    """Measured bursts and steady high bands are surfaced even when the
    model only describes the low rumble (the reported miss)."""
    if bg.get("bursts") and not _mentions(_also_visible_para(text), _BURST_WORDS):
        text = _append_also_visible(
            text, "Measured in the audio: " + _describe_bursts(bg["bursts"])
            + ", the shape of a dog bark or similar mammal call, voice or knock.")
    for b in bg.get("bands") or []:
        para = _also_visible_para(text)
        if not _mentions(para, _BAND_WORDS, near_hz=b["peak_hz"]):
            lead = "Also measured: " if "Measured in the audio" in para else "Measured in the audio: "
            text = _append_also_visible(
                text, lead + _describe_band(b)
                + ", likely an insect chorus or an electrical/mechanical whine.")
    return text


AI_VIEW_MAX_SECONDS = 60.0   # longer recordings are cropped for the AI image


def _ai_view_window(detections, duration: float, top) -> tuple:
    """
    (start_s, end_s) for the AI image. A 5-minute recording squeezed into
    one image leaves a few pixels per second, too little to judge a call,
    so recordings over AI_VIEW_MAX_SECONDS are cropped to the 60 s stretch
    holding the most detections (always including the top one).
    """
    if not duration or duration <= AI_VIEW_MAX_SECONDS:
        return None
    span = AI_VIEW_MAX_SECONDS
    lo = max(0.0, float(top.end_time) - span)
    hi = min(float(top.start_time), duration - span)
    best, best_n = max(0.0, min(lo, hi)), -1
    candidates = {lo, max(0.0, hi)} | {max(0.0, float(d.start_time) - 2.0) for d in detections}
    for c in sorted(candidates):
        c = min(max(0.0, c), max(0.0, duration - span))
        if not (c <= float(top.start_time) and float(top.end_time) <= c + span):
            continue
        n = sum(1 for d in detections if float(d.start_time) >= c and float(d.end_time) <= c + span)
        if n > best_n:
            best, best_n = c, n
    return (best, min(duration, best + span))


def _species_bands(wav_path: str, groups: dict, exclude_hz=None) -> dict:
    """Measured frequency band per species: the clearest of up to six of
    its detections (largest excess over background). A measured insect
    pulse's frequency is excluded so its chirps aren't read as the bird."""
    try:
        from .audio_processor import measure_detection_bands
        out = {}
        for name, items in groups.items():
            picks = sorted(items, key=lambda d: -d.confidence)[:6]
            bands = [b for b in measure_detection_bands(
                wav_path, [(d.start_time, d.end_time) for d in picks],
                exclude_hz=exclude_hz) if b]
            if bands:
                out[name] = max(bands, key=lambda b: b["excess_db"])
        return out
    except Exception as e:
        logger.warning("Band measurement failed for %s: %s", wav_path, e)
        return {}


_RUMBLE_TOP_HZ = 400.0      # diffuse energy below this is usually wind/traffic
_FAINT_DB = 8.0             # call barely above the background


def _species_evidence(name: str, band, items: list, server_ran: bool) -> list:
    """Measured facts about one species' detections, for the prompt and the
    Audio check paragraph. Empty list = nothing noteworthy."""
    from .audio_processor import LOW_FREQUENCY_CALLERS
    notes = []
    if band is None:
        notes.append("no sound in its boxes stands out from the background noise (measured)")
    else:
        if band["high_hz"] < _RUMBLE_TOP_HZ and name not in LOW_FREQUENCY_CALLERS:
            notes.append(
                f"its measured energy ({band['low_hz'] / 1000:.2f}\u2013{band['high_hz'] / 1000:.2f} kHz) "
                "is in the wind/traffic rumble range, below where this species usually calls")
        if band["excess_db"] < _FAINT_DB:
            notes.append(f"faint: only {band['excess_db']:.0f} dB above the background")
    if server_ran:
        if any(getattr(d, "source", "device") == "server" for d in items):
            notes.append("the server's own BirdNET pass also found it")
        else:
            notes.append("device detection only; the server's BirdNET pass didn't reproduce it")
    return notes


def _shrink_png(image_bytes: bytes, max_width: int = 1344, provider: str = "") -> bytes:
    """Downscale the spectrogram for the vision model and send it as JPEG.
    Image tokens scale with pixels on most models, so a wide image costs
    time for no gain (the measured bands carry the precise frequencies);
    local models get 1024 px. A resampled spectrogram saved as PNG came out
    larger than the original (378 KB from 326 KB); JPEG at quality 88 is
    about a quarter of that with the labels still sharp."""
    if provider == "ollama":
        max_width = min(max_width, 1024)
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        if im.width > max_width:
            im = im.resize((max_width, round(im.height * max_width / im.width)), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=88, optimize=True)
        return out.getvalue()
    except Exception as e:
        logger.debug("Spectrogram downscale skipped: %s", e)
        return image_bytes


def _image_type(image_bytes: bytes) -> str:
    return "image/jpeg" if image_bytes[:3] == b"\xff\xd8\xff" else "image/png"


_DEVICE_ONLY = "device detection only; the server's BirdNET pass didn't reproduce it"
_PLAIN_CAVEATS = [
    (re.compile(r"no sound in its boxes stands out from the background noise(?: \(measured\))?", re.I),
     lambda m, n: "Nothing in its boxes is louder than the background noise."),
    (re.compile(r"its measured energy \(([\d.]+)\u2013([\d.]+) kHz\) is in the wind/traffic rumble range, "
                r"below where this species usually calls", re.I),
     lambda m, n: f"The sound in its boxes sits at {m.group(1)}\u2013{m.group(2)} kHz, the low rumble of "
                  f"wind and traffic, below where {'an' if n[:1].upper() in 'AEIOU' else 'a'} {n} calls."),
    (re.compile(r"faint: only (-?\d+) dB above the background", re.I),
     lambda m, n: f"The call is faint, only {m.group(1)} dB louder than the background."),
    (re.compile(re.escape(_DEVICE_ONLY), re.I),
     lambda m, n: "Only the device picked it up; when the server ran BirdNET on the same "
                  "recording, it didn't find it."),
    (re.compile(r"(\d+) broadband bark-like bursts? fall inside its boxes(?: \(measured\))?", re.I),
     lambda m, n: (f"{m.group(1)} short, loud burst{'s' if m.group(1) != '1' else ''} "
                   "covering a wide pitch range (like a dog's bark) "
                   f"{'fall' if m.group(1) != '1' else 'falls'} inside its boxes.")),
    (re.compile(r"verdict changed from Consistent to Uncertain", re.I),
     lambda m, n: "So the verdict was lowered from Consistent to Uncertain."),
]


def _plain_caveat(note: str, name: str) -> str:
    """One measured caveat as a plain sentence for the note."""
    note = note.strip().rstrip(".")
    for rx, fmt in _PLAIN_CAVEATS:
        m = rx.fullmatch(note)
        if m:
            return fmt(m, name)
    return (note[:1].upper() + note[1:] + ".") if note else ""


def _audio_check_para(name: str, caveats: list) -> str:
    return f"**Audio check for {name}:** " + " ".join(
        s for s in (_plain_caveat(c, name) for c in caveats) if s)


_LEGACY_MEASURED_RE = re.compile(r"\*\*Measured check:\*\*\s*([^:\n]+):\s*([^\n]*)")


def _rewrite_legacy_measured(text: str) -> str:
    """Notes saved before 0.5.10.d end with '**Measured check:** Name: a; b.'
    Show them in the same plain form as new ones."""
    def repl(m):
        name, body = m.group(1).strip(), m.group(2).strip().rstrip(".")
        body = body.replace(_DEVICE_ONLY, "\x00")
        parts = [p.replace("\x00", _DEVICE_ONLY) for p in body.split("; ") if p.strip()]
        return _audio_check_para(name, parts)
    return _LEGACY_MEASURED_RE.sub(repl, text)


def _apply_measured_check(text: str, name: str, band, notes: list) -> str:
    """Append what the audio measurements say against the primary species
    (in plain sentences), and downgrade a CONSISTENT verdict to UNCERTAIN
    when nothing in its boxes rises above the background, or the only thing
    that does is rumble below where the species calls: the image can't
    confirm a call that isn't measurably there."""
    caveats = [n for n in notes if not n.startswith("the server's own BirdNET pass also")]
    if not caveats:
        return text
    verdict, rest = _parse_verdict(text)
    in_rumble = any("rumble range" in c for c in caveats)
    if verdict == "consistent" and (band is None or in_rumble):
        text = "UNCERTAIN\n" + rest
        caveats.append("verdict changed from Consistent to Uncertain")
    return text.rstrip() + "\n\n" + _audio_check_para(name, caveats)

def _fmt_band(b: dict) -> str:
    k = lambda hz: f"{hz / 1000:.2f}" if hz < 1000 else f"{hz / 1000:.1f}"
    return (f"measured peak about {k(b['peak_hz'])} kHz, most energy "
            f"{k(b['low_hz'])}\u2013{k(b['high_hz'])} kHz")


def _reanalyze_bird_call(db, recording, detections, top, proc, provider, api_key) -> str:
    """
    Bird branch of reanalyze_call() below. A recording can have many
    detections — most often the SAME species flagged repeatedly across a
    long recording, not several different species — and the spectrogram
    image already boxes and labels every one of them individually (see
    generate_spectrogram()'s detection-overlay section).

    Reported directly as a problem: an earlier version of this asked
    for 1-2 sentences on EVERY individual detection, which for a
    recording with 15 same-species detections produced 15 near-identical
    paragraphs — an unreadable wall of text, not a useful
    second opinion. Detections are now grouped by SPECIES first, and the
    model is asked for ONE synthesized assessment per species (noting
    which segments look strongest/weakest within that group and why, not
    a separate paragraph per timestamp) — so a recording with 15
    Northern Flicker detections and nothing else gets one focused
    paragraph about Northern Flicker, not fifteen. A recording that
    has several different species still gets one paragraph
    per species, which is the variety worth addressing
    individually. Still gives ONE overall leading verdict word (for the
    primary/top detection's species specifically) so
    _parse_verdict()'s single-verdict-per-recording design and the
    stored ai_reanalysis_verdict column don't need to change shape.
    """
    other = detections[1:]

    # Reuse the same spectrogram generator the /spectrogram endpoint
    # uses — full resolution (thumb=False), no detection-count cap,
    # since this is a one-off request, not a grid of dozens loading
    # at once. Written to a scratch temp dir, not the recording's own
    # cache dir, so this doesn't collide with or invalidate the
    # regular cached thumbnail/full images.
    import tempfile
    from ..models import AppSettings
    _cr_settings = db.query(AppSettings).filter(AppSettings.id == 1).first()
    try:
        import soundfile as _sf
        duration = float(_sf.info(recording.wav_path).duration)
    except Exception:
        duration = float(getattr(recording, "duration_seconds", 0) or 0)
    window = _ai_view_window(detections, duration, top)
    shown = [d for d in detections
             if window is None or (d.end_time > window[0] and d.start_time < window[1])]

    # Group by species, preserving first-appearance order, with the
    # primary/top detection's species always listed first regardless of
    # where its OTHER detections happen to fall chronologically — that's
    # the species the leading verdict word is about, so it belongs at
    # the top of what the model reads.
    groups = {}
    for d in detections:
        groups.setdefault(d.common_name, []).append(d)
    ordered_species = [top.common_name] + [n for n in groups if n != top.common_name]

    # Audio measurements run alongside the spectrogram render.
    from concurrent.futures import ThreadPoolExecutor

    def _measure():
        p = _measure_pulses(recording.wav_path)
        return (p, _species_bands(recording.wav_path, groups, [x["freq_hz"] for x in p]),
                _measure_background(recording.wav_path, detections))

    import time as _time
    _t0 = _time.monotonic()
    _pool = ThreadPoolExecutor(max_workers=1)
    _measured = _pool.submit(_measure)
    with tempfile.TemporaryDirectory() as tmpdir:
        png_path = proc.generate_spectrogram(
            recording.wav_path, tmpdir, recording.id,
            detections=[{
                "common_name": d.common_name, "start_time": d.start_time,
                "end_time": d.end_time, "confidence": d.confidence,
            } for d in shown],
            conf_key="reanalysis", thumb=False,
            color_palette=getattr(_cr_settings, "detection_color_palette", None) or "vivid",
            box_fill=False, time_range=window, mel_axis=True, fig_height=4.2,
        )
        with open(png_path, "rb") as f:
            image_bytes = _shrink_png(f.read(), provider=provider)

    regional_line = _get_regional_plausibility(db, top.common_name)
    pulses, bands, bg = _measured.result()
    _pool.shutdown(wait=False)
    # A cricket's pulse already reported doesn't need a second, band entry.
    bg["bands"] = [b for b in bg.get("bands") or []
                   if not any(b["low_hz"] - 300 <= p["freq_hz"] <= b["high_hz"] + 300 for p in pulses)]
    pulse_hint = _pulse_hint(pulses) + _background_hint(bg)
    server_ran = any(getattr(d, "source", "device") == "server" for d in detections)
    evidence = {name: _species_evidence(name, bands.get(name), groups[name], server_ran)
                for name in ordered_species}
    for name in ordered_species:
        n_in = sum(1 for b in bg.get("bursts") or [] if b.get("in_box") == name)
        if n_in:
            evidence[name].append(
                f"{n_in} broadband bark-like burst{'s' if n_in != 1 else ''} fall inside its boxes (measured)")

    def _ev(name: str) -> str:
        return ("; " + "; ".join(evidence[name])) if evidence.get(name) else ""
    image_note = (
        "The spectrogram's frequency axis is mel-spaced (labels in kHz), so the "
        "low range below 1 kHz, where owls, doves and grouse call, is stretched "
        "for visibility; read heights from the tick labels, not by proportion."
    )
    if bands:
        image_note += (
            " Species lines above that carry a measured band got it from the "
            "loudest part of that species' boxes in the audio; use it to anchor "
            "where on the image to look."
        )
    if window:
        image_note += (
            f" This recording is {duration:.0f} s long; the image shows "
            f"{window[0]:.0f}\u2013{window[1]:.0f} s, the stretch with the most "
            "detections. Detections outside it are listed but not pictured."
        )

    def _fmt_ts(d) -> str:
        return f"{d.start_time:.1f}\u2013{d.end_time:.1f}s ({round(d.confidence * 100)}%)"

    multi_species = len(groups) > 1 or len(other) > 0
    named_species_list = ", ".join(ordered_species)
    grouping_instructions = (
        (
            f"This recording has {len(detections)} detected calls across "
            f"EXACTLY {len(groups)} species: {named_species_list}. Each is "
            "boxed in its own color and labeled with its species name, "
            "timestamp range, and confidence directly on the spectrogram "
            "image — matching the groups given to you below. After your "
            "one-word overall verdict (for the PRIMARY species, listed "
            "first), give ONE synthesized paragraph PER SPECIES GROUP — "
            "not one paragraph per individual detection, "
            f"and — this is a hard boundary — write EXACTLY {len(groups)} "
            f"paragraphs in this section, one for each of {named_species_list} "
            "and nothing else. Before you write this section, treat it as "
            f"a checklist of exactly these {len(groups)} names — if you're "
            "about to write a paragraph for any species not on that list, "
            "stop: it doesn't belong here. If you notice "
            "what looks like a different, additional bird call anywhere else "
            "on the spectrogram — unboxed, unlabeled, not one of the "
            f"{len(groups)} species named above — do NOT give it its own "
            "paragraph here and do NOT fold it into this per-species-group "
            "section at all. That "
            "belongs exclusively in the separate 'Other species detected:' "
            "paragraph described later in these instructions, which comes "
            "AFTER the Overall summary — never here, and never blended into "
            "one of the named species' own paragraphs either. "
            "Within each of the "
            f"{len(groups)} named species' paragraphs, look across ALL of "
            "that species' timestamps together: say roughly how many "
            "segments look strong/consistent vs. weak/questionable and why, "
            "referencing specific visual features at the representative "
            "timestamps rather than narrating every single one. A species "
            "with many repeated detections should still get just one "
            "focused paragraph, not a paragraph per timestamp — keep each "
            "species' paragraph to 3-5 sentences regardless of how many "
            "detections it has. Start each paragraph with the species name "
            "in markdown bold (**Species Name**) so it's clear which group "
            "you're discussing, followed by a blank line before the next "
            "species' paragraph.\n\n"
        )
        if multi_species else ""
    )

    system_prompt = (
        "You are giving a useful second opinion on a bird-call spectrogram "
        "from a home acoustic-monitoring system. An automated model (BirdNET) already "
        "identified this call — you're a sanity check, not a replacement, and not "
        "a rubber stamp either.\n\n"
        + grouping_instructions +
        "Respond in this exact structure:\n"
        "Line 1: exactly one word — CONSISTENT (the spectrogram looks like a "
        "plausible match for the stated species), INCONSISTENT (it doesn't — state why "
        "plainly), or UNCERTAIN (a spectrogram alone isn't enough to tell "
        "either way for this call, which is a legitimate answer, not a "
        "cop-out).\n"
        "Then, reasoning referencing SPECIFIC visual features you can "
        "see: the frequency range a call occupies, "
        "whether it's a clean tonal whistle vs. a buzzy/harsh sound, harmonic structure (a "
        "fundamental with stacked overtones, or a single clean band), the rhythm and "
        "duration of the call/phrase, and how many distinct syllables or notes are visible. "
        "Ground your reasoning in what's visible, not in a restated confidence "
        "percentage. If UNCERTAIN, say specifically what's ambiguous "
        "or what additional information (a clearer recording, the audio instead of "
        "just a spectrogram) would resolve it, not just 'it's hard to tell from an image "
        "alone.'\n"
        "If regional/seasonal context is given below, you may factor it in, but "
        "don't treat it as decisive on its own — an uncommon visitor is still a "
        "possibility, not something to rule out just because it's rare.\n"
        "Measured facts in the request (frequency band, loudness above the "
        "background, whether the server's BirdNET pass agreed, regional "
        "frequency) come from the audio and eBird data and outrank your reading "
        "of the image. Don't answer CONSISTENT when they cut against the "
        "identification — nothing above the background in the boxes, energy only "
        "in the wind/traffic rumble range for a species that calls higher, or a "
        "locally rare species without a clear species-typical shape — unless you "
        "can point to a specific visible feature that outweighs them. Don't claim "
        "regional support that the regional line doesn't give.\n"
        + ("Bold each species name (**Species Name**) the first time its paragraph "
           "starts, and separate each species' paragraph from the next with a blank "
           "line. "
           if multi_species else
           "Bold the species name (**Species Name**) the first time you mention it. ")
        + "Give every species you discuss (flagged, other species you spot, and any animal "
        "under Also visible) a likelihood: your estimate, 0\u2013100%, that it is calling in "
        "this recording, from what you see and the measured facts. Write it right after "
        "the bold name, like **Blue Jay** (likelihood 85%), once, and keep it honest: 50% means "
        "a coin flip, and a low number is useful.\n"
        + ("With several species, go straight from Line 1 to the first species' "
           "paragraph: no opening summary, since the Overall paragraph is the summary. "
           if multi_species else "")
        + "Finish with one short final paragraph, starting with **Overall:**, that "
        "states your bottom-line take in plain terms — for a single species, "
        "restate the verdict in a sentence or two; for multiple species, briefly "
        "say which of them you're confident about versus which are more doubtful, "
        "so someone skimming only that last paragraph still gets the gist. "
        "Keep it to one or two sentences and don't repeat the evidence already "
        "given above. "
        "No bullet points, no headers, no other markdown beyond the bold names "
        "and the Overall line — plain prose paragraphs otherwise.\n\n"
        "After the Overall paragraph, do a SEPARATE, deliberate second pass "
        "over the ENTIRE spectrogram — not just near the boxed/labeled "
        "detection(s) above — specifically looking for anything else visible "
        "that BirdNET didn't flag. Treat this as a real, required step, not "
        "an optional afterthought: a home acoustic monitor's whole point is "
        "catching what an automated classifier misses, and a vision model "
        "given only one task (verify the flagged call) will naturally not "
        "spend effort looking elsewhere unless explicitly told to. There "
        "are two different things to look for, and — this matters — they "
        "go under two SEPARATE headings, not one combined paragraph, so "
        "it's immediately clear which species BirdNET itself flagged versus "
        "which are only here because you spotted them yourself:\n\n"
        "(1) OTHER BIRD CALLS BirdNET didn't flag, or flagged with low "
        "confidence, that aren't the species already covered above — "
        "including, for a multi-species recording, anything beyond the "
        "exact set of named species the per-species-group section above "
        "was capped at. If you "
        "see a call-shaped pattern (clean tonal structure, harmonic stack, "
        "discrete syllables/notes, a rhythm) that looks like a genuine bird "
        "vocalization, actually attempt your own species guess for it from "
        "its visual shape, the same way you would if BirdNET had flagged it "
        "— don't just note \"there's another bird call here\" and stop. "
        "State the guess with honest uncertainty (\"possibly a X, based on "
        "...\" rather than a flat identification) and say what makes you "
        "unsure. If you can't narrow it to a species at all, say what family "
        "or type it resembles (e.g. \"a warbler-type trill\") rather than "
        "nothing. Report this, if you find anything, under its own paragraph "
        "starting with **Other species detected:** — this label is deliberate: "
        "everything here is something YOU found, not BirdNET, so don't blur "
        "it into the verdict paragraphs above by phrasing it as if BirdNET "
        "had also flagged it.\n\n"
        "(2) NON-BIRD sound or animal activity — a dog's bark (short, loud, "
        "harsh vertical stacks of harmonics from about 0.5 kHz up to several kHz, "
        "usually in quick repeats), other mammals (squirrel, deer, fox, "
        "coyote), people talking, an Eastern Chipmunk's chip call (a steady "
        "series of short vertical streaks several kHz tall, around 4\u201310 kHz, "
        "roughly one or two a second for minutes; insects instead make a narrow "
        "band at one pitch), "
        "a cicada/cricket/grasshopper's buzz or trill, wind, rain, "
        "mechanical noise, etc. Look at the WHOLE frequency range: a steady "
        "band HIGH in the image (a few kHz and up: insect chorus, electrical "
        "whine, hiss) is as reportable as low-frequency rumble, and each "
        "gets its own description with its own frequency range. This includes a CONTINUOUS band running "
        "across the entire spectrogram, not just a discrete, localized "
        "event — a nonstop insect chorus (common in a real outdoor "
        "recording, especially a cicada band sitting in a mid-frequency "
        "range) is exactly the kind of thing to call out, not something to "
        "overlook just because it's present the whole time rather than a "
        "one-off event. The same goes for a ROW OF SHORT, EVENLY SPACED "
        "DASHES at one fixed height running across the image — that is the "
        "classic look of cricket or katydid chirps (or a beeping device), "
        "and it's easy to dismiss as background texture. Report this, if "
        "you find anything, under its own paragraph starting with "
        "**Also visible:**, giving its approximate frequency and how often "
        "it repeats.\n\n"
        "Include either, both, or neither paragraph depending on what's "
        "genuinely there — never invent one to fill a template, and when a "
        "category is empty leave its paragraph out entirely rather than writing "
        "that nothing was found. The bar is "
        "real visual evidence, not certainty — a reasonable-confidence guess "
        "is far more useful here than silence, so don't let \"I'm not fully "
        "sure\" become a reason to skip something you can actually see. Skip "
        "either paragraph only if you've actually looked and there's "
        "genuinely nothing in that category — not as a default when unsure."
    )
    confidence_pct = round(top.confidence * 100)
    confidence_context = (
        "very high — BirdNET is rarely this confident on a wrong call, though it can still happen"
        if confidence_pct >= 90 else
        "solidly high, a generally reliable range" if confidence_pct >= 75 else
        "moderate — this is the range where a second look is most worth doing" if confidence_pct >= 50 else
        "on the lower side — BirdNET itself is signaling uncertainty here"
    )
    if multi_species:
        groups_list = "\n".join(
            f"{name} ({len(items)} detection{'s' if len(items) != 1 else ''}): "
            + ", ".join(_fmt_ts(d) for d in items)
            + (f"; {_fmt_band(bands[name])}" if name in bands else "")
            + _ev(name)
            for name in ordered_species
            for items in [groups[name]]
        )
        user_prompt = (
            f"Detected species groups in this recording (listed first = primary):\n"
            f"{groups_list}\n\n"
            f"Primary species confidence context: {confidence_context}.\n\n"
            f"{image_note}\n\n"
            f"{regional_line}\n\n"
            "Give your second opinion on this spectrogram, following the exact structure above "
            "— one synthesized paragraph per species group, not per individual detection."
            + pulse_hint
        )
    else:
        user_prompt = (
            f"Current identification: {top.common_name} at {confidence_pct}% confidence "
            f"({confidence_context})"
            + (f"; {_fmt_band(bands[top.common_name])}" if top.common_name in bands else "")
            + _ev(top.common_name)
            + ".\n\n"
            f"{image_note}\n\n"
            f"{regional_line}\n\n"
            "Give your second opinion on this spectrogram, following the exact structure above."
            + pulse_hint
        )

    _t1 = _time.monotonic()
    text = call_vision_completion(
        provider, api_key, system_prompt, user_prompt, image_bytes, _image_type(image_bytes),
        max_tokens=1000 if multi_species else 700, db=db, feature="call_reanalysis",
    )
    logger.info("AI Second Opinion %s: prep %.1fs, %s model %.1fs, image %d KB",
                recording.id, _t1 - _t0, provider, _time.monotonic() - _t1, len(image_bytes) // 1024)
    text = _tidy_note(_strip_truncated_trailing_section(text), multi_species)
    text = _ensure_pulses_reported(text, pulses)
    text = _ensure_background_reported(text, bg)
    return _apply_measured_check(text, top.common_name, bands.get(top.common_name),
                                 evidence.get(top.common_name) or [])


def _regional_candidates(db, limit: int = 40) -> list:
    """Most frequently reported species here this month (eBird), best first."""
    from ..models import RegionalSpecies
    try:
        rows = db.query(RegionalSpecies).all()
    except Exception:
        return []
    m = datetime.utcnow().month - 1
    scored = []
    for r in rows:
        f = (r.monthly_frequency[m] if r.monthly_frequency and len(r.monthly_frequency) == 12
             else (r.current_likelihood or 0.0))
        if f and f > 0.02:
            scored.append((f, r.common_name))
    return [n for _f, n in sorted(scored, reverse=True)[:limit]]


def _loudest_window(wav_path: str, duration: float) -> tuple:
    """(start, end) of the AI_VIEW_MAX_SECONDS stretch with the most 1-10 kHz
    energy, or None when the recording already fits in one image."""
    if not duration or duration <= AI_VIEW_MAX_SECONDS:
        return None
    try:
        import numpy as np
        import soundfile as sf
        from scipy.signal import butter, sosfilt
        y, sr = sf.read(wav_path, dtype="float32", always_2d=False)
        if y.ndim > 1:
            y = y.mean(axis=1)
        sos = butter(4, [1000, min(10000, sr / 2 - 100)], btype="band", fs=sr, output="sos")
        e = sosfilt(sos, y) ** 2
        per_s = np.add.reduceat(e, np.arange(0, len(e), sr))
        span = int(AI_VIEW_MAX_SECONDS)
        if len(per_s) <= span:
            return None
        c = np.convolve(per_s, np.ones(span), "valid")
        start = float(int(np.argmax(c)))
        return (start, min(duration, start + span))
    except Exception as e:
        logger.warning("Loudest-window search failed for %s: %s", wav_path, e)
        return (0.0, AI_VIEW_MAX_SECONDS)


def _survey_empty_recording(db, recording, hidden, proc, provider, api_key) -> str:
    """Second opinion for a recording with no shown detections: look over the
    whole spectrogram for any bird call BirdNET didn't flag. hidden: stored
    detections under the display threshold, given as BirdNET's weak guesses."""
    import tempfile
    from ..models import AppSettings
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    try:
        import soundfile as _sf
        duration = float(_sf.info(recording.wav_path).duration)
    except Exception:
        duration = float(getattr(recording, "duration_seconds", 0) or 0)
    window = _loudest_window(recording.wav_path, duration)

    import time as _time
    _t0 = _time.monotonic()
    with tempfile.TemporaryDirectory() as tmpdir:
        png_path = proc.generate_spectrogram(
            recording.wav_path, tmpdir, recording.id, detections=None,
            conf_key="reanalysis", thumb=False,
            color_palette=getattr(s, "detection_color_palette", None) or "vivid",
            box_fill=False, time_range=window, mel_axis=True, fig_height=4.2,
        )
        with open(png_path, "rb") as f:
            image_bytes = _shrink_png(f.read(), provider=provider)
    pulses = _measure_pulses(recording.wav_path)
    bg = _measure_background(recording.wav_path, [])
    bg["bands"] = [b for b in bg.get("bands") or []
                   if not any(b["low_hz"] - 300 <= p["freq_hz"] <= b["high_hz"] + 300 for p in pulses)]

    weak = ""
    if hidden:
        weak = ("BirdNET's weak guesses, below the app's display threshold and not shown "
                "to the user (treat as leads to check, not identifications): "
                + "; ".join(f"{d.common_name} {d.start_time:.1f}\u2013{d.end_time:.1f}s "
                            f"({round(d.confidence * 100)}%)" for d in hidden[:8]) + ".\n\n")
    cands = _regional_candidates(db)
    regional = (("Species most often reported near this location this month (eBird), "
                 "most frequent first: " + ", ".join(cands) + ".\n\n") if cands else "")
    view = ""
    if window:
        view = (f"This recording is {duration:.0f} s long; the image shows "
                f"{window[0]:.0f}\u2013{window[1]:.0f} s, the stretch with the most 1\u201310 kHz energy.\n\n")

    system_prompt = (
        "You are reviewing a spectrogram from a home acoustic bird monitor. BirdNET "
        "flagged no bird above the user's threshold in this recording, and the user wants "
        "to know whether any bird is audible anyway.\n\n"
        "Respond in this exact structure:\n"
        "Line 1: exactly one word \u2014 BIRDS (at least one likely bird call is visible), "
        "NONE (you looked across the whole image and see no bird call), or UNCERTAIN "
        "(marks that might be calls but can't be told from noise).\n"
        "Then one paragraph per candidate call, starting with your guess in markdown bold "
        "(**Species Name**, or a type such as **warbler-type trill** when you can't narrow "
        "it): give its time range and frequency range read from the axis labels, its shape "
        "(tonal whistle, buzzy, harmonic stack, number of notes, rhythm), and what makes you "
        "unsure. Prefer species that are plausible here. The frequency axis is mel-spaced "
        "(labels in kHz), so the range below 1 kHz is stretched; read heights from the tick "
        "labels.\n"
        "If BirdNET's weak guesses are listed, say for each whether the image supports it.\n"
        "Then a paragraph starting with **Also visible:** for non-bird sound (insects, "
        "frogs, a chipmunk's chip series, dogs, voices, traffic, wind, rain, hum), with "
        "frequency and repetition, only if present. A steady series of short streaks "
        "several kHz tall is a chipmunk or a bird's chip note, not an insect; insects make "
        "a narrow band at one pitch.\n"
        + "Give every species you discuss (flagged, other species you spot, and any animal "
        "under Also visible) a likelihood: your estimate, 0\u2013100%, that it is calling in "
        "this recording, from what you see and the measured facts. Write it right after "
        "the bold name, like **Blue Jay** (likelihood 85%), and keep it honest: 50% means "
        "a coin flip, and a low number is useful.\n"
        "Finish with **Overall:** and one or two sentences: is there a bird worth "
        "re-analyzing for, and where. No headers or bullets; plain paragraphs. Don't "
        "invent calls to fill the template: NONE is a normal answer."
    )
    user_prompt = (view + weak + regional
                   + "Look over the whole spectrogram for bird calls, following the structure above."
                   + _pulse_hint(pulses) + _background_hint(bg))
    _t1 = _time.monotonic()
    text = call_vision_completion(
        provider, api_key, system_prompt, user_prompt, image_bytes, _image_type(image_bytes),
        max_tokens=900, db=db, feature="call_reanalysis",
    )
    logger.info("AI Second Opinion (no detections) %s: prep %.1fs, %s model %.1fs",
                recording.id, _t1 - _t0, provider, _time.monotonic() - _t1)
    text = _ensure_pulses_reported(_tidy_note(_strip_truncated_trailing_section(text)), pulses)
    return _ensure_background_reported(text, bg)


def reanalyze_call(db, recording) -> None:
    """
    Generates a second-opinion note for one Recording and stores it, or
    stores an error and leaves any previous note in place. `recording` is
    an already-loaded Recording ORM object; this function commits itself.

    Branches early on recording.is_bat — see _reanalyze_bat_call()'s own
    docstring for why the bat path needs a genuinely different prompt
    and spectrogram, not just the same call with different words.
    """
    config = get_feature_config("call_reanalysis", db)
    if config is None:
        return  # feature disabled or unconfigured — nothing to do, silently
    provider, api_key = config

    try:
        from ..models import Detection, AppSettings
        from .audio_processor import AudioProcessor

        # Reported directly, more than once: AI Second Opinion was
        # discussing a species that was never actually shown as a
        # detection at all — not boxed on the spectrogram, not counted
        # in "N species detected". Root cause: this query pulled every
        # Detection row for the recording with no confidence filter,
        # while the spectrogram image, the species-count badge, and the
        # detections list all filter by min_confidence_display (the
        # same threshold recordings.py's own detail endpoint uses —
        # `if d.confidence < display_min_conf: continue`). A detection
        # that exists in the database below that threshold is real data
        # but was never something the user was actually shown as a
        # flagged detection, so it shouldn't be treated as one here
        # either — it's exactly the kind of thing that belongs under
        # "Other species detected:" if AI can actually see it, not
        # silently included as if BirdNET had flagged it at display
        # confidence.
        app_s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        display_min_conf = float(getattr(app_s, "min_confidence_display", 0.0) or 0.0) if app_s else 0.0

        detections = (
            db.query(Detection)
            .filter(Detection.recording_id == recording.id)
            .filter(Detection.confidence >= display_min_conf)
            .order_by(Detection.confidence.desc())
            .all()
        )
        proc = AudioProcessor()
        if not detections and recording.is_bat:
            recording.ai_reanalysis_note = None
            recording.ai_reanalysis_verdict = None
            recording.ai_reanalysis_error = "No bat detection to re-check against."
            recording.ai_reanalysis_generated_at = datetime.utcnow()
            db.commit()
            return

        top = detections[0] if detections else None
        if top is None:
            # Nothing shown: survey the whole recording for birds instead.
            hidden = (db.query(Detection)
                      .filter(Detection.recording_id == recording.id)
                      .filter(Detection.confidence < display_min_conf)
                      .order_by(Detection.confidence.desc()).all())
            text = _survey_empty_recording(db, recording, hidden, proc, provider, api_key)
        elif recording.is_bat:
            text = _reanalyze_bat_call(db, recording, top, proc, provider, api_key)
        else:
            text = _reanalyze_bird_call(db, recording, detections, top, proc, provider, api_key)

        verdict, remainder = _parse_verdict(text)
        recording.ai_reanalysis_note = remainder
        recording.ai_reanalysis_verdict = verdict
        recording.ai_reanalysis_generated_at = datetime.utcnow()
        recording.ai_reanalysis_error = None
        db.commit()
        logger.info("Call re-analysis generated for recording %s via %s (verdict=%s, is_bat=%s)",
                    recording.id, provider, verdict, recording.is_bat)

    except Exception as e:
        logger.warning("Call re-analysis failed for recording %s: %s", recording.id, e)
        recording.ai_reanalysis_error = str(e)[:500]
        db.commit()
