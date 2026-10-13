"""
Chirp Server — Bat Species Classification (Experimental, via BatDetect2)
============================================================================
Optional, off-by-default species guess for bat-echolocation recordings,
using the open-source BatDetect2 model (macaodha/batdetect2 on GitHub,
PyPI package `batdetect2`).

READ THIS BEFORE ENABLING OR TRUSTING ANY OUTPUT FROM THIS MODULE
--------------------------------------------------------------------------
The bundled, pretrained BatDetect2 model classifies among 17 UK bat
species ONLY. Chirp's documented example deployment is Natick,
Massachusetts — nowhere near the UK, and with an entirely different set
of bat species present. None of the species this model can predict are
native to Massachusetts (or most of North America). Running it on a
North American recording does not produce "no match" — the model has no
out-of-distribution rejection built in, so it will confidently assign the
call to whichever of its 17 UK species sounds acoustically closest, which
is not the same thing as a correct identification, and in most US
deployments will simply be wrong.

This module exists so the integration can be exercised and tested end to
end (model loading, inference, storage shape) ahead of either: (a) a
future BatDetect2 release or community model trained on North American
species, or (b) fine-tuning a custom model on local reference calls,
which the upstream project's tooling explicitly supports. Until one of
those happens, every prediction this module produces is stored with
validated=False and should be treated as "closest UK acoustic match,"
not a species identification — see bat_profile_content.py and this
module's plan for how that's meant to surface once it's trustworthy:
species-level BirdProfile-style pages, the same pattern individual bird
species already get, but only once a model exists worth showing anyone
without a disclaimer attached to every result.

Nothing in this module is called from the frontend today. It's wired
into the bat background-processing pipeline (see
api/recordings.py:_process_bat_recording_bg) behind the
bat_species_id_enabled setting, which defaults to False, so it has zero
effect on a normal deployment unless explicitly turned on by someone who
has read this docstring.

Dependency note: `batdetect2` (and its own dependencies — notably
PyTorch) are NOT in requirements.txt by default, the same pattern as
optional heavy dependencies elsewhere in this codebase (e.g. playwright
for headless-browser range maps). Install with:
    pip install "batdetect2>=1.3.1,<2"
pinned below 2.0 deliberately — 2.x is a beta release as of this writing
with a different API shape; see the upstream migration guide.
"""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("chirp.bat_species_id")

MODEL_NAME = "batdetect2"
MODEL_TRAINED_ON = "17 UK bat species (macaodha/batdetect2 default checkpoint)"

# Lazy import / lazy model load — batdetect2 pulls in PyTorch, a genuinely
# heavy dependency with no reason to pay its import cost (or risk an
# ImportError) on every server startup when the feature defaults to off.
_BATDETECT2_AVAILABLE: Optional[bool] = None
_api = None


def _ensure_loaded() -> bool:
    """Import batdetect2 on first real use only. Returns True if available."""
    global _BATDETECT2_AVAILABLE, _api
    if _BATDETECT2_AVAILABLE is not None:
        return _BATDETECT2_AVAILABLE
    try:
        import batdetect2.api as _bd2_api
        _api = _bd2_api
        _BATDETECT2_AVAILABLE = True
        logger.info("batdetect2 loaded successfully (model: %s)", MODEL_TRAINED_ON)
    except ImportError as e:
        _BATDETECT2_AVAILABLE = False
        logger.warning(
            "batdetect2 not installed — bat species ID unavailable. "
            "Install with: pip install \"batdetect2>=1.3.1,<2\" (%s)", e,
        )
    return _BATDETECT2_AVAILABLE


def is_available() -> bool:
    """Whether batdetect2 is importable in this environment. Cheap to call
    repeatedly after the first call — result is cached."""
    return _ensure_loaded()


def classify_bat_clip(wav_path: str) -> Optional[dict]:
    """
    Run BatDetect2 on a single bat-echolocation WAV clip (the same
    native-rate raw audio used for the spectrogram — NOT the time-expanded
    "enhanced" playback version, which would have the wrong frequency
    content for the model).

    Returns None if batdetect2 isn't installed, the file doesn't exist, or
    inference fails for any reason — every failure mode here is non-fatal
    to the caller, since species ID is a pure bonus on top of activity
    detection, which already succeeded by the time this runs.

    Returns a dict shaped for storage directly into Recording.bat_metadata
    under the "species_guess" key:
        {
            "model": "batdetect2",
            "model_trained_on": "<human-readable caveat string>",
            "predicted_class": str,       # file-level top prediction
            "class_prob": float,          # 0-1, classification confidence
                                           # GIVEN it's one of the 17 UK species
                                           # — does not account for the
                                           # possibility that it's none of them
            "det_prob": float,            # 0-1, confidence a real call was
                                           # present at all (separate from
                                           # which species)
            "call_count": int,            # number of individual call
                                           # annotations BatDetect2 found
                                           # within the clip
            "validated": False,           # always False today — see module
                                           # docstring
        }
    """
    if not _ensure_loaded():
        return None

    p = Path(wav_path)
    if not p.exists():
        logger.debug("classify_bat_clip: file not found: %s", wav_path)
        return None

    try:
        result = _api.process_file(p)
    except Exception as e:
        logger.warning("BatDetect2 inference failed for %s: %s", wav_path, e)
        return None

    pred = result.get("pred_dict") or {}
    annotations = pred.get("annotation") or []

    # File-level top prediction. If BatDetect2 found no calls at all in this
    # clip (possible — Chirp's own energy/pulse-train detector and
    # BatDetect2's are different algorithms and can disagree), there's
    # nothing to report; return None rather than a hollow all-zero result.
    if not annotations:
        logger.debug("BatDetect2 found no calls in %s (Chirp's detector did)", wav_path)
        return None

    # det_prob/class_prob: take the highest-detection-confidence call as
    # representative, rather than averaging across all calls in the clip —
    # a single confidently-detected call is more informative than diluting
    # it with quieter/edge calls the model is less sure about.
    best = max(annotations, key=lambda a: a.get("det_prob", 0.0))

    return {
        "model": MODEL_NAME,
        "model_trained_on": MODEL_TRAINED_ON,
        "predicted_class": pred.get("class_name") or best.get("individual") or "Unknown",
        "class_prob": float(best.get("class_prob", 0.0)),
        "det_prob": float(best.get("det_prob", 0.0)),
        "call_count": len(annotations),
        "validated": False,
    }
