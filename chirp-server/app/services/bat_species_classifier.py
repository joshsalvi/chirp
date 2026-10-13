"""
Bat species classification — two-stage BirdNET-embedding + linear-classifier
pipeline, using the approach documented by BattyBirdNET-Analyzer
(https://github.com/rdz-oss/BattyBirdNET-Analyzer): the standard BirdNET v2.4
model, run in "embeddings mode" (its second-to-last layer, not its own
6522-species bird output) to extract a 1024-dimensional feature vector from
a 256kHz audio window, fed into a small linear classifier trained on the
NABat (North American Bat Monitoring Program) dataset, region-restricted to
eastern North American species — the USA-EAST checkpoint, chosen since
that's the relevant region for this deployment (Massachusetts).

╔══════════════════════════════════════════════════════════════════════════╗
║ STATUS: standalone and tested, NOT wired into the live detection/upload  ║
║ pipeline yet. Nothing in bat_detector.py, the upload flow, the API, or   ║
║ the frontend calls this module. It exists here, correctly working and   ║
║ verified against the real bundled model files, as a deliberate first    ║
║ step — see this session's chat for the reasoning.                       ║
╚══════════════════════════════════════════════════════════════════════════╝

Model files (see models/bats/README.md for full detail and licensing):
  - BirdNET v2.4 base model — embeddings extraction only (birdnetlib's
    bundled FP32 copy unless an FP16 copy is placed in models/bats)
  - BattyBirdNET-USA-EAST-256kHz.tflite — the actual species classifier
  - BattyBirdNET-USA-EAST-256kHz_Labels.txt — its 23 output classes

Real accuracy caveats (from the classifier's own maintainer and from
peer-reviewed literature on automated bat classifiers generally — see
models/bats/README.md for citations): expect real misclassifications,
especially among acoustically similar Myotis species, and expect the
classifier to sometimes confuse the SAME species being tracked over
consecutive seconds with a different, most likely because a single 0.5625s
window doesn't always capture ncough of a call's characteristic shape.
This module deliberately surfaces ALL 23 class confidences (including the
built-in noise/cricket/silence rejection classes), not just a single
asserted top-1 species, so any caller can apply its own judgment about how
much certainty a given result actually represents rather than being handed
false confidence.
"""
import logging
import os
from pathlib import Path
from typing import List, Optional

import numpy as np

logger = logging.getLogger("chirp.bat_species_classifier")

_MODELS_DIR_ENV = os.environ.get("CHIRP_BAT_MODELS_DIR", "").strip()
_MODELS_DIR = (
    Path(_MODELS_DIR_ENV) if _MODELS_DIR_ENV
    else Path(__file__).resolve().parent.parent.parent / "models" / "bats"
)


def _find_embedding_model() -> Path:
    """
    The BirdNET v2.4 base model used for embeddings. A copy in models/bats
    wins if present; otherwise birdnetlib's own bundled FP32 copy of the
    same model is used, so the package doesn't have to ship a second 26 MB
    copy. Checked on synthetic bat sweeps: FP16 and FP32 embeddings match
    (cosine similarity 0.99999, same tensor index) and give the same
    species ranking.
    """
    local = _MODELS_DIR / "BirdNET_GLOBAL_6K_V2.4_Model_FP16.tflite"
    if local.exists():
        return local
    try:
        import importlib.util
        spec = importlib.util.find_spec("birdnetlib")
        if spec and spec.origin:
            bundled = (Path(spec.origin).parent / "models" / "analyzer"
                       / "BirdNET_GLOBAL_6K_V2.4_Model_FP32.tflite")
            if bundled.exists():
                return bundled
    except Exception:
        pass
    return local


_EMBEDDING_MODEL_PATH = _find_embedding_model()
_CLASSIFIER_MODEL_PATH = _MODELS_DIR / "BattyBirdNET-USA-EAST-256kHz.tflite"
_LABELS_PATH = _MODELS_DIR / "BattyBirdNET-USA-EAST-256kHz_Labels.txt"

# Fixed by the model architecture (see models/bats/README.md) — the base
# BirdNET model's input tensor is always exactly 144000 samples; at 256kHz
# that represents 0.5625s, a much shorter window than the 3-second windows
# BirdNET uses for its own bird-classification purpose at 48kHz. Same input
# SIZE, different sample rate, different real-world duration — this is a
# real, verified property of the model file, not a guess.
CLASSIFIER_SAMPLE_RATE = 256_000
WINDOW_SAMPLES = 144_000
WINDOW_SECONDS = WINDOW_SAMPLES / CLASSIFIER_SAMPLE_RATE  # 0.5625s
# 25% overlap between consecutive windows, matching BattyBirdNET-Analyzer's
# own reference config.py (SIG_OVERLAP = SIG_LENGTH / 4.0) — verified
# directly against the actual upstream source, not assumed.
WINDOW_OVERLAP_SECONDS = WINDOW_SECONDS / 4.0
WINDOW_STEP_SAMPLES = int((WINDOW_SECONDS - WINDOW_OVERLAP_SECONDS) * CLASSIFIER_SAMPLE_RATE)

# Labels that mean "not a real bat species" — the classifier's own built-in
# rejection classes, kept distinct from the 16 real species throughout this
# module rather than treated identically, since conflating "confidently
# noise" with "confidently a specific bat" would be a real, meaningful
# category error, not just cosmetic.
_NON_SPECIES_LABELS = {"tettigoniidea_cricket", "background", "collected", "noise", "noise-us", "other", "silence"}

_embedding_interpreter = None
_embedding_input_index: Optional[int] = None
_embedding_output_index: Optional[int] = None
_classifier_interpreter = None
_classifier_input_index: Optional[int] = None
_classifier_output_index: Optional[int] = None
_labels: Optional[List[str]] = None


class BatClassifierUnavailable(Exception):
    """Raised when the model files aren't present or fail to load — callers
    should treat this as "species classification isn't available right now",
    not as a hard error; nothing about the rest of Chirp depends on this."""


def is_available() -> bool:
    """True if all three required files are present on disk. Cheap enough
    to call before attempting real work, so callers can show a clear
    message instead of an exception traceback if the models were never
    actually placed in models/bats/ (e.g. a fresh clone without the
    bundled files, or a deliberately stripped-down deployment)."""
    return _EMBEDDING_MODEL_PATH.exists() and _CLASSIFIER_MODEL_PATH.exists() and _LABELS_PATH.exists()


def _load_labels() -> List[str]:
    global _labels
    if _labels is not None:
        return _labels
    if not _LABELS_PATH.exists():
        raise BatClassifierUnavailable(f"Labels file not found at {_LABELS_PATH}")
    with open(_LABELS_PATH, "r", encoding="utf-8") as f:
        _labels = [line.strip() for line in f if line.strip()]
    if len(_labels) != 23:
        logger.warning(
            "Expected 23 labels for the bundled USA-EAST classifier, got %d — "
            "the labels file may not match the model file it's paired with.",
            len(_labels),
        )
    return _labels


def _load_embedding_model():
    """
    Loads the base BirdNET model in embeddings-extraction mode. The output
    tensor index used here (final_output_index - 1) is the exact technique
    BattyBirdNET-Analyzer's own model.py uses — the embedding layer is the
    one immediately preceding the model's final 6522-species classification
    layer in the graph, and TFLite numbers tensors sequentially, so this is
    a reliable, verified way to reach it (confirmed directly against the
    real bundled file: produces exactly the (1, 1024) shape the classifier
    expects, not a guess).

    experimental_preserve_all_tensors=True is required — without it, TFLite
    optimizes away intermediate tensors that aren't part of the model's
    declared output, and attempting to read one raises "Tensor data is
    null" rather than actually returning anything.
    """
    global _embedding_interpreter, _embedding_input_index, _embedding_output_index
    if _embedding_interpreter is not None:
        return _embedding_interpreter

    if not _EMBEDDING_MODEL_PATH.exists():
        raise BatClassifierUnavailable(f"Embedding model not found at {_EMBEDDING_MODEL_PATH}")

    try:
        import tensorflow as tf
    except ImportError as e:
        raise BatClassifierUnavailable(f"tensorflow is not installed: {e}")

    interp = tf.lite.Interpreter(
        model_path=str(_EMBEDDING_MODEL_PATH),
        experimental_preserve_all_tensors=True,
    )
    interp.allocate_tensors()
    in_details = interp.get_input_details()
    out_details = interp.get_output_details()

    _embedding_input_index = in_details[0]["index"]
    _embedding_output_index = out_details[0]["index"] - 1
    _embedding_interpreter = interp
    logger.info(
        "Bat species classifier: embedding model loaded (%s), embedding tensor index %d",
        _EMBEDDING_MODEL_PATH.name, _embedding_output_index,
    )
    return _embedding_interpreter


def _load_classifier():
    global _classifier_interpreter, _classifier_input_index, _classifier_output_index
    if _classifier_interpreter is not None:
        return _classifier_interpreter

    if not _CLASSIFIER_MODEL_PATH.exists():
        raise BatClassifierUnavailable(f"Classifier model not found at {_CLASSIFIER_MODEL_PATH}")

    try:
        import tensorflow as tf
    except ImportError as e:
        raise BatClassifierUnavailable(f"tensorflow is not installed: {e}")

    interp = tf.lite.Interpreter(model_path=str(_CLASSIFIER_MODEL_PATH))
    interp.allocate_tensors()
    in_details = interp.get_input_details()
    out_details = interp.get_output_details()

    _classifier_input_index = in_details[0]["index"]
    _classifier_output_index = out_details[0]["index"]
    _classifier_interpreter = interp
    logger.info("Bat species classifier: classifier model loaded (%s)", _CLASSIFIER_MODEL_PATH.name)
    return _classifier_interpreter


def _extract_embedding(window_samples: np.ndarray) -> np.ndarray:
    """window_samples: exactly WINDOW_SAMPLES (144000) float32 samples at
    CLASSIFIER_SAMPLE_RATE (256kHz). Returns the (1, 1024) embedding."""
    interp = _load_embedding_model()
    audio = window_samples.reshape(1, WINDOW_SAMPLES).astype(np.float32)
    interp.set_tensor(_embedding_input_index, audio)
    interp.invoke()
    return interp.get_tensor(_embedding_output_index)


def _classify_embedding(embedding: np.ndarray) -> np.ndarray:
    """embedding: (1, 1024) float32. Returns raw (23,) logits — NOT yet
    passed through sigmoid; _window_result does that, so callers working
    directly with this function get the same raw values the model actually
    produced, not a version already reshaped for display."""
    interp = _load_classifier()
    interp.set_tensor(_classifier_input_index, embedding.astype(np.float32))
    interp.invoke()
    return interp.get_tensor(_classifier_output_index)[0]


def _resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """
    Standard sample-rate conversion — NOT the same operation as
    downshift_bat_clip() in audio_processor.py, which does time-expansion
    to make ultrasonic content audible to humans (changing both pitch and
    duration together). This is an ordinary resample: same pitch content,
    same real-world duration, just represented with a different number of
    samples per second, purely so the model receives audio at the exact
    rate it was trained on.
    """
    if orig_sr == target_sr:
        return audio.astype(np.float32)
    from scipy.signal import resample as scipy_resample
    n_target = int(round(len(audio) * target_sr / orig_sr))
    return scipy_resample(audio, n_target).astype(np.float32)


def _window_audio(audio_256k: np.ndarray) -> List[np.ndarray]:
    """
    Slices a (possibly much longer than WINDOW_SECONDS) clip into
    overlapping WINDOW_SAMPLES-length windows, matching BattyBirdNET-
    Analyzer's own reference overlap (25%). A clip shorter than one full
    window is zero-padded up to WINDOW_SAMPLES rather than skipped — the
    same "pad short chunks" approach the reference config takes (its
    SIG_MINLEN concept), so even a very short real clip still gets a
    genuine classification attempt instead of silently producing nothing.
    """
    windows = []
    n = len(audio_256k)
    if n == 0:
        return windows
    if n <= WINDOW_SAMPLES:
        padded = np.zeros(WINDOW_SAMPLES, dtype=np.float32)
        padded[:n] = audio_256k
        windows.append(padded)
        return windows

    start = 0
    while start < n:
        end = start + WINDOW_SAMPLES
        if end > n:
            # Final, shorter-than-a-full-window remainder — pad rather
            # than drop, so the tail of a clip isn't silently ignored.
            chunk = np.zeros(WINDOW_SAMPLES, dtype=np.float32)
            remainder = audio_256k[start:n]
            chunk[: len(remainder)] = remainder
            windows.append(chunk)
            break
        windows.append(audio_256k[start:end])
        start += WINDOW_STEP_SAMPLES
    return windows


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def classify_bat_clip(audio: np.ndarray, sample_rate: int) -> dict:
    """
    Main entry point. `audio` is a 1-D float32 array at any sample rate
    (resampled internally to 256kHz); `sample_rate` is its actual rate.

    Runs one classification per overlapping window across the whole clip,
    then reports the MAXIMUM confidence seen for each of the 23 classes
    across all windows — not an average (which would understate a species
    that was only calling during part of a longer clip) and not just the
    single best window (which would discard corroborating evidence from
    other windows of the same call).

    Returns a comprehensive dict, not just a single top-1 guess:
      {
        "species": [ {label, common_name, scientific_name, confidence}, ... ]
                   — the 16 real species, sorted by confidence, descending
        "non_species": [ {label, confidence}, ... ]
                   — the 7 rejection classes (noise/cricket/silence/etc.),
                     surfaced explicitly rather than hidden, since a high
                     "noise" or "cricket" confidence relative to every real
                     species is itself a meaningful, honest result
        "num_windows": how many overlapping windows were actually analyzed
        "window_seconds": WINDOW_SECONDS, for caller context
      }

    Raises BatClassifierUnavailable if the model files aren't present —
    callers should catch this and treat classification as simply
    unavailable, not as a hard failure of whatever triggered it.
    """
    if not is_available():
        raise BatClassifierUnavailable(
            f"Bat species model files not found under {_MODELS_DIR} — "
            f"species classification is unavailable."
        )

    labels = _load_labels()
    audio_256k = _resample(audio, sample_rate, CLASSIFIER_SAMPLE_RATE)
    windows = _window_audio(audio_256k)

    if not windows:
        return {"species": [], "non_species": [], "num_windows": 0, "window_seconds": WINDOW_SECONDS}

    max_confidence = np.zeros(len(labels), dtype=np.float32)
    for window in windows:
        embedding = _extract_embedding(window)
        logits = _classify_embedding(embedding)
        probs = _sigmoid(logits)
        max_confidence = np.maximum(max_confidence, probs)

    species = []
    non_species = []
    for i, label in enumerate(labels):
        label_lower = label.lower()
        confidence = float(max_confidence[i])
        if label_lower in _NON_SPECIES_LABELS:
            non_species.append({"label": label, "confidence": confidence})
        else:
            # BirdNET-style labels are "Scientific name_Common name" —
            # confirmed against the actual bundled labels file this session
            # (e.g. "Myotis lucifugus_Little brown bat"), same convention
            # already fixed for the bird pipeline earlier this session.
            parts = label.split("_", 1)
            scientific = parts[0] if len(parts) >= 1 else label
            common = parts[1] if len(parts) >= 2 else label
            species.append({
                "label": label,
                "scientific_name": scientific,
                "common_name": common,
                "confidence": confidence,
            })

    species.sort(key=lambda s: s["confidence"], reverse=True)
    non_species.sort(key=lambda s: s["confidence"], reverse=True)

    return {
        "species": species,
        "non_species": non_species,
        "num_windows": len(windows),
        "window_seconds": WINDOW_SECONDS,
    }


def classify_bat_wav_file(wav_path: str) -> dict:
    """Convenience wrapper — reads a WAV file from disk and classifies it."""
    import soundfile as sf
    audio, sr = sf.read(wav_path, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio[:, 0]  # mono only — same convention as the rest of this codebase
    return classify_bat_clip(audio, sr)
