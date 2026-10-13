"""
AI Second Opinion note clean-up: species headings and the duplicate
opening summary.

    python3 -m pytest -q tests/test_ai_note_tidy.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services.call_reanalysis import _tidy_note, tidy_stored_note  # noqa: E402

NOTE = """CONSISTENT

The calls match both species: the Wren's buzz and the Jay's whistle.

**Carolina Wren** (likelihood 95%) Buzzy bursts at 2.7-3.2 kHz.

**Blue Jay** (likelihood **Blue Jay** (likelihood 85%) A clean whistle.

**Overall:** Both are well supported.

**Also visible:** an insect band at 4.3-7.9 kHz."""


def test_multi_species_note():
    out = _tidy_note(NOTE, multi_species=True)
    assert out.startswith("CONSISTENT\n\n**Carolina Wren** (likelihood 95%)")
    assert "**Blue Jay** (likelihood 85%) A clean whistle." in out
    assert "match both species" not in out
    assert out.count("Blue Jay") == 1
    assert out.endswith("**Also visible:** an insect band at 4.3-7.9 kHz.")


def test_headings():
    assert _tidy_note("**Blue Jay (likelihood 85%)** x") == "**Blue Jay** (likelihood 85%) x"
    assert _tidy_note("Blue Jay (likelihood Blue Jay (likelihood 85%) x") == "Blue Jay (likelihood 85%) x"
    assert _tidy_note("**Blue Jay** (Likelihood  85 %) x") == "**Blue Jay** (likelihood 85%) x"


def test_single_species_keeps_text():
    t = "BirdNET looks right. **Blue Jay** (likelihood 90%) whistle.\n\n**Overall:** fine"
    assert tidy_stored_note(t) == t
    assert tidy_stored_note(None) is None


def test_stored_multi_drops_intro():
    stored = NOTE.split("\n\n", 1)[1]
    out = tidy_stored_note(stored)
    assert out.startswith("**Carolina Wren**") and out.count("Blue Jay") == 1


def test_audio_check_plain_language():
    from app.services.call_reanalysis import _apply_measured_check
    old = ("**Blue Jay** (likelihood 40%) A faint whistle.\n\n**Overall:** Doubtful.\n\n"
           "**Measured check:** Blue Jay: faint: only 6 dB above the background; device detection "
           "only; the server's BirdNET pass didn't reproduce it; verdict changed from Consistent to Uncertain.")
    out = tidy_stored_note(old)
    assert "Measured check" not in out and "**Audio check for Blue Jay:**" in out
    assert "only 6 dB louder than the background" in out
    assert "lowered from Consistent to Uncertain" in out
    assert out.startswith("**Blue Jay** (likelihood 40%)")
    new = _apply_measured_check("CONSISTENT\nx", "Eastern Owl", None,
                                ["no sound in its boxes stands out from the background noise (measured)"])
    assert new.startswith("UNCERTAIN\n")
    assert new.endswith("**Audio check for Eastern Owl:** Nothing in its boxes is louder than the "
                        "background noise. So the verdict was lowered from Consistent to Uncertain.")
