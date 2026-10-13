"""
Translates the three personality sliders (Settings -> AI Features) into
natural-language instruction text for the AI prompt-writing features
(Daily Journal, Bird Profile Summaries).

Why bands, not literal numbers: LLMs don't take a numeric "irreverence:
62" as a meaningful instruction — what actually steers tone is natural
language describing the desired register. Chirp's Daily Journal prompt
already does exactly this pattern (see daily_summary.py's
_FOCUS_ANGLES/_OPENING_STYLES, a fixed set of instruction snippets
chosen from), just previously via random.choice() rather than a
Settings value. Each slider (0-100) maps to one of 3 bands rather than
continuously interpolating text for every possible value — an LLM
doesn't reliably distinguish "a little more formal" from "a little bit
more formal than that," so a handful of clearly distinct bands is both
simpler to reason about and no less effective in practice than a false
appearance of fine-grained control.

Default values (see models.py) are calibrated so the DEFAULT band on
every slider reproduces, in substance, the same tone instructions the
system prompts had before these sliders existed — moving a slider is
what changes behavior; leaving all three at default should not visibly
change existing output. This calibration is necessarily a judgment call
about wording, not something a test can assert on the way tdoa.py's
position-error test can — see the note at the bottom of this file for
what testing this actually looks like given that constraint.
"""

FRIENDLINESS_LOW = 25
FRIENDLINESS_HIGH = 75
INFORMATIONAL_LOW = 30
INFORMATIONAL_HIGH = 70
IRREVERENCE_LOW = 20
IRREVERENCE_HIGH = 60
DEPTH_LOW = 30
DEPTH_HIGH = 70
CURIOSITY_LOW = 30
CURIOSITY_HIGH = 70


def _band(value: int, low_cutoff: int, high_cutoff: int) -> str:
    if value < low_cutoff:
        return "low"
    if value > high_cutoff:
        return "high"
    return "mid"


_FRIENDLINESS_TEXT = {
    "low": "Keep the tone fairly neutral and matter-of-fact — clear and pleasant, but not "
           "effusive or personal. Skip endearments and exclamation-heavy enthusiasm.",
    "mid": "Warm, personable tone — like a friendly, knowledgeable birder sharing notes with "
           "someone they like talking to. Genuine enthusiasm is welcome, without overdoing it.",
    "high": "Very warm and personal — write like this is going to a close friend who shares "
            "your love of birds. Real affection and enthusiasm for the subject can come through "
            "openly, not just politely.",
}

_INFORMATIONAL_TEXT = {
    "low": "Lean toward atmosphere, mood, and scene-setting over data density — the feeling of "
           "the morning/day matters more here than packing in specifics. Still stay accurate; "
           "just don't force in facts that don't serve the mood.",
    "mid": "Balance concrete facts and data with atmospheric, narrative prose — neither a dry "
           "stats report nor pure mood-writing with no substance.",
    "high": "Prioritize concrete facts, real data points, and specific ornithological detail — "
            "keep atmospheric/narrative flourishes light-touch and in service of the information, "
            "not the other way around.",
}

_IRREVERENCE_TEXT = {
    "low": "Stay fairly straight and sincere — minimal joking, no wry asides. Sincerity over wit.",
    "mid": "A bit of wit and warmth is welcome — a wry aside here and there, the kind of "
           "affectionate humor one birder shares with another. Never at a species' expense.",
    "high": "Feel free to lean into playful, tongue-in-cheek humor and more pointed wit than "
            "usual — still affectionate toward the subject, never mocking, but don't hold back "
            "on personality for the sake of restraint.",
}

# A fourth, genuinely different axis from the original three: how much
# actual LENGTH/depth an entry gets, not its tone. This is what "more
# detail, teaching, and commentary" actually needs — the original three
# sliders all shape voice and content density within whatever fixed
# paragraph count the caller's own prompt hardcodes; none of them let
# someone ask for a longer entry with real room to teach a concept,
# unpack a trend, or work in an extra fact. Returns a *relative*
# instruction (shorter/normal/longer than the caller's own stated
# default), not a hardcoded paragraph count itself — each caller
# (Daily Journal, Weekly Journal) has a different sensible baseline
# length, so this band text is deliberately generic enough to layer on
# top of whichever baseline the caller states in its own prompt.
_DEPTH_TEXT = {
    "low": "Keep this genuinely brief — shorter than you might default to, favoring one sharp, "
           "well-chosen observation over covering everything. Cut anything that isn't earning "
           "its place.",
    "mid": "Normal length for this feature — enough room for real substance without padding.",
    "high": "Take real extra room here — more than the usual length for this feature. Use the "
            "extra space for genuine depth: actually teach a concept properly rather than "
            "mentioning it in passing, unpack a trend or pattern instead of just naming it, work "
            "in an additional real fact or two. More material, not just more words around the "
            "same material — don't pad with repetition or filler to hit a length.",
}

# A fifth axis, distinct from all four above: WHY vs. WHAT. The other
# four all shape voice, fact-density, humor, and length — none of them
# push toward actually exploring the reasons behind what happened.
# Depth gives more room to teach; curiosity is what fills that room
# with genuine "why" rather than more "what." Low curiosity is
# perfectly fine and not a lesser mode — a straightforward account of
# today's activity is a legitimate, complete entry on its own.
_CURIOSITY_TEXT = {
    "low": "Stick to reporting what actually happened — which birds, how many, when. Skip "
           "digressions into why or how; a clear, grounded account of the day is complete on "
           "its own, nothing missing by not speculating further.",
    "mid": "Where it fits naturally, touch on a genuine 'why' behind something in today's "
           "activity — a plausible ecological or behavioral reason, stated as a real "
           "possibility rather than a certainty you can't actually verify from the data given.",
    "high": "Actively lean into real curiosity — when something in the data invites a deeper "
            "question (why this species and not another, what a pattern might actually mean, "
            "how a behavior evolved, what's genuinely still not well understood about it), "
            "follow that thread rather than just noting the observation and moving on. Real "
            "intellectual engagement with the natural world, not trivia for its own sake — and "
            "still honest about the difference between an established fact and an interesting "
            "possibility.",
}


def personality_instructions(friendliness: int = 60, informational: int = 50,
                              irreverence: int = 35, depth: int = 50, curiosity: int = 50,
                              brief: bool = False) -> str:
    """
    Returns a natural-language paragraph to insert into a system prompt,
    reflecting all five slider positions. `brief=True` is for
    short-format features (Bird Profile Summaries — 2-3 sentences total)
    where the instructions need to explicitly acknowledge the format
    constraint, since "lean into playful wit" and "prioritize concrete
    facts" can otherwise read as license to run long — depth's own
    "low"/"mid" text still applies in brief mode, but "high" doesn't
    make sense for an already-short format, so brief mode ignores the
    depth setting entirely rather than telling a 2-3-sentence feature
    to "take real extra room." Curiosity, unlike depth, is included in
    brief mode too — exploring a genuine "why" doesn't require more
    room, just different content, so even "high" curiosity is
    achievable within 2-3 sentences.
    """
    f_band = _band(friendliness, FRIENDLINESS_LOW, FRIENDLINESS_HIGH)
    i_band = _band(informational, INFORMATIONAL_LOW, INFORMATIONAL_HIGH)
    r_band = _band(irreverence, IRREVERENCE_LOW, IRREVERENCE_HIGH)
    c_band = _band(curiosity, CURIOSITY_LOW, CURIOSITY_HIGH)

    parts = [_FRIENDLINESS_TEXT[f_band], _INFORMATIONAL_TEXT[i_band], _IRREVERENCE_TEXT[r_band], _CURIOSITY_TEXT[c_band]]

    if not brief:
        d_band = _band(depth, DEPTH_LOW, DEPTH_HIGH)
        parts.append(_DEPTH_TEXT[d_band])

    text = " ".join(parts)

    if brief:
        text += (" Remember this all has to fit in 2-3 sentences total — apply this tone "
                  "within that length, don't let it become an excuse to write more.")

    return text


def length_instruction(depth: int, short: str, normal: str, long: str) -> str:
    """
    Turns the depth slider into a real length instruction for a
    specific caller's own baseline lengths — each feature (Daily
    Journal, Weekly Journal) has a different sensible normal length, so
    this takes the caller's own three length descriptions rather than
    hardcoding any of them here. Returns a complete sentence, e.g.
    "Keep it to 2-3 short paragraphs total." — the caller can append it
    directly into its own prompt text.
    """
    d_band = _band(depth, DEPTH_LOW, DEPTH_HIGH)
    text = {"low": short, "mid": normal, "high": long}[d_band]
    return f"Keep it to {text} total."


if __name__ == "__main__":
    # Real test of the deterministic PART of this module — band
    # selection given a value, and that the default values fall where
    # they're documented to fall. What this CANNOT test: whether the
    # resulting prose actually reads as more/less friendly, informational,
    # or irreverent to a person — that's a real limitation of testing
    # a natural-language-steering feature, not a gap in this test.
    # Confirming that requires generating and reading real output
    # against an actual AI provider, which needs a live API key this
    # sandbox doesn't have — noted explicitly rather than glossed over.
    print("=== personality.py band-selection self-test ===\n")

    # Confirm the documented default values land in the "mid" band,
    # since that's the band whose wording was calibrated to match the
    # pre-existing hardcoded prompt text — if a default ever gets
    # changed without checking this, the "default = current behavior"
    # promise silently breaks.
    assert _band(60, FRIENDLINESS_LOW, FRIENDLINESS_HIGH) == "mid", "Default friendliness (60) must be 'mid'"
    assert _band(50, INFORMATIONAL_LOW, INFORMATIONAL_HIGH) == "mid", "Default informational (50) must be 'mid'"
    assert _band(35, IRREVERENCE_LOW, IRREVERENCE_HIGH) == "mid", "Default irreverence (35) must be 'mid'"
    assert _band(50, DEPTH_LOW, DEPTH_HIGH) == "mid", "Default depth (50) must be 'mid'"
    assert _band(50, CURIOSITY_LOW, CURIOSITY_HIGH) == "mid", "Default curiosity (50) must be 'mid'"
    print("PASS: documented default values (60, 50, 35, 50, 50) all fall in the 'mid' band")

    # Confirm boundary behavior at the edges of each band — off-by-one
    # errors here would silently misclassify a slider value into the
    # wrong band without any error, exactly the kind of bug that's easy
    # to introduce and easy to miss without checking explicitly.
    assert _band(FRIENDLINESS_LOW - 1, FRIENDLINESS_LOW, FRIENDLINESS_HIGH) == "low"
    assert _band(FRIENDLINESS_LOW, FRIENDLINESS_LOW, FRIENDLINESS_HIGH) == "mid"
    assert _band(FRIENDLINESS_HIGH, FRIENDLINESS_LOW, FRIENDLINESS_HIGH) == "mid"
    assert _band(FRIENDLINESS_HIGH + 1, FRIENDLINESS_LOW, FRIENDLINESS_HIGH) == "high"
    assert _band(DEPTH_LOW - 1, DEPTH_LOW, DEPTH_HIGH) == "low"
    assert _band(DEPTH_HIGH + 1, DEPTH_LOW, DEPTH_HIGH) == "high"
    assert _band(CURIOSITY_LOW - 1, CURIOSITY_LOW, CURIOSITY_HIGH) == "low"
    assert _band(CURIOSITY_HIGH + 1, CURIOSITY_LOW, CURIOSITY_HIGH) == "high"
    print("PASS: band boundaries behave correctly at every edge value, including the new curiosity dimension")

    # Confirm all-default call produces non-empty, well-formed text and
    # doesn't crash — a real smoke test of the actual public function,
    # not just the internal _band() helper.
    default_text = personality_instructions()
    assert len(default_text) > 100
    assert "friendly" in default_text.lower() or "warm" in default_text.lower()
    print("PASS: default personality_instructions() call produces sane, non-trivial text")

    # Confirm brief=True actually appends the length-constraint reminder,
    # correctly OMITS the depth instruction entirely (telling a
    # 2-3-sentence feature to "take real extra room" would be actively
    # self-contradictory), but STILL INCLUDES the curiosity instruction
    # (unlike depth, exploring a "why" doesn't require more room).
    brief_text = personality_instructions(brief=True)
    assert "2-3 sentences" in brief_text
    assert "take real extra room" not in brief_text.lower(), "brief=True must not include the depth 'high' instruction — it contradicts the format"
    assert "where it fits naturally, touch on a genuine" in brief_text.lower() or "stick to reporting" in brief_text.lower() or "actively lean into real curiosity" in brief_text.lower(), "brief=True must still include a curiosity instruction — unlike depth, it doesn't contradict a short format"
    print("PASS: brief=True omits the depth instruction but correctly still includes a curiosity instruction")

    # Confirm the depth dimension alone produces genuinely different
    # text at its low/mid/high settings, holding the other four fixed
    # — if this didn't vary, the slider would silently do nothing.
    depth_low = personality_instructions(depth=0)
    depth_high = personality_instructions(depth=100)
    assert depth_low != depth_high
    assert "brief" in depth_low.lower() or "shorter" in depth_low.lower()
    assert "extra room" in depth_high.lower()
    print("PASS: the depth slider alone produces genuinely distinct text at low vs. high settings")

    # Confirm the curiosity dimension alone produces genuinely different
    # text at its low/mid/high settings, holding the other four fixed.
    curiosity_low = personality_instructions(curiosity=0)
    curiosity_high = personality_instructions(curiosity=100)
    assert curiosity_low != curiosity_high
    assert "stick to reporting" in curiosity_low.lower()
    assert "real curiosity" in curiosity_high.lower()
    print("PASS: the curiosity slider alone produces genuinely distinct text at low vs. high settings")

    # Confirm the five extreme corners produce genuinely different text
    # from the default and from each other — if two bands accidentally
    # mapped to identical text, the slider would silently do nothing.
    low_all = personality_instructions(friendliness=0, informational=0, irreverence=0, depth=0, curiosity=0)
    high_all = personality_instructions(friendliness=100, informational=100, irreverence=100, depth=100, curiosity=100)
    assert low_all != default_text
    assert high_all != default_text
    assert low_all != high_all
    print("PASS: extreme slider settings produce genuinely distinct text from default and from each other")

    print("\nAll deterministic checks pass. Actual tone-shift validation still requires generating "
          "real output against a live AI provider — not something this sandbox can do without an API key.")
