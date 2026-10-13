"""
Chirp Server — AI Enhance (Experimental)
============================================================================
On-demand neural-network denoising for bird recordings/clips, as a
separate, independent alternative to the classical bandpass + spectral-
gating pipeline in audio_processor.py's enhance_audio(). Uses a
pretrained Demucs-based model released by Earth Species Project
(biodenoising16k_dns48), trained specifically on animal vocalizations —
not a generic speech-enhancement model repurposed for this.

The feature itself is off by default (AppSettings.ai_enhance_enabled) —
enabling it in Settings is what actually turns this on. torch/torchaudio
ARE installed by default in requirements.txt (per direct request, so
the feature works out of the box once enabled rather than needing a
manual rebuild first) — unlike bat_species_id.py's BatDetect2
integration, which keeps its own torch dependency commented out.
Still lazy-imported below rather than at module load: a server that
never enables the setting never pays torch's import cost, and this
also keeps the code working (just reporting unavailable) for anyone
who deliberately strips torch back out of their own build. Same
_ensure_loaded()/is_available() shape as bat_species_id.py, for
consistency.

REAL, KNOWN LIMITATION — read before enabling
----------------------------------------------------------------------------
The pretrained model runs at 16kHz. Chirp records bird audio at 48kHz
(see chirp-device/config.yaml). Audio is downsampled to 16kHz for the
model pass and upsampled back afterward — any real frequency content
above 8kHz (the 16kHz Nyquist limit) is lost from the denoised result.
Most bird vocalizations sit well under 8kHz, but some high-pitched
callers (e.g. several warblers, kinglets) carry meaningful energy above
it — for those, the classical Enhanced/Rumble removed toggles
(full-bandwidth, audio_processor.py) preserve content this can't. Bat
echolocation (15-120kHz) is entirely out of range for this model — AI
Enhance is bird-only, the same scope restriction Rumble removed already
has and for the same underlying reason.

Verified directly against the real downloaded checkpoint on synthetic
noisy audio before shipping (measured, not assumed from the paper's own
claims): a quiet background-only region's peak amplitude dropped to
silence while a call region's own peak was preserved (~5% reduction vs.
the background's ~100%) — genuine, measured noise suppression, not a
blind pass-through.

Model source: https://github.com/earthspecies/biodenoising (MIT).
Weights are hosted publicly by Earth Species Project, no auth required.
See _vendor/biodenoising/__init__.py for why the inference code here is
vendored rather than depending on the upstream PyPI package directly.
"""
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

from ..config import settings

logger = logging.getLogger("chirp.ai_enhance")

BIO_DNS_48_URL = "https://storage.googleapis.com/esp-public-files/biodenoising/model-16kHz-dns48.th"
MODEL_SAMPLE_RATE = 16000
MODEL_FILENAME = "biodenoising16k_dns48.th"

# Bumped whenever enhance_wav()'s actual output would change for a
# recording/clip already processed under an older version — same
# reasoning, and same bug this is preventing a repeat of, as
# audio_processor.py's own DSP_VERSION: a cached WAV keyed by
# recording/detection ID alone would otherwise keep serving the OLD
# output forever after an algorithm change, indistinguishable from a
# legitimate cache hit. v2 = added the rumble high-pass pre-filter
# below (previously AI Enhance had no rumble-specific filtering at
# all and relied entirely on the neural model, which doesn't
# specifically target low frequencies the way this simple filter does).
# v3: split-band output — see _restore_high_band's docstring. Bumped so
# every previously cached AI-Enhanced file/spectrogram regenerates.
# v4: steady insect/beep tones notched before the model (see enhance_wav
# step 0b).
AI_ENHANCE_VERSION = "v4"

# Split-band constants — tuned on real recordings, see _restore_high_band.
SPLIT_CROSSOVER_HZ = 7000.0      # below the model's 8kHz Nyquist, with room for the filter transition
SPLIT_MIN_HIGH_BAND_SNR_DB = 8.0 # high band must contain call-like content to be restored at all
SPLIT_GATE_REDUCTION_DB = 24.0   # attenuation applied to near-floor frames in the restored high band
SPLIT_GATE_MARGIN_DB = 6.0       # frames this far above the high band's median level pass untouched

_VENDOR_DIR = str(Path(__file__).parent / "_vendor")

# Lazy import / lazy model load — torch is a genuinely heavy dependency
# with no reason to pay its import cost (or risk an ImportError) on
# every server startup when the feature defaults to off. Same pattern
# as bat_species_id.py's _BATDETECT2_AVAILABLE/_api.
_TORCH_AVAILABLE: Optional[bool] = None
_torch = None
_torchaudio = None
_model = None  # lazily-loaded singleton nn.Module, reused across requests


def _ensure_loaded() -> bool:
    """Import torch/torchaudio and load the pretrained model on first real
    use only. Returns True if AI Enhance is usable in this environment.
    Cheap to call repeatedly after the first call — result is cached."""
    global _TORCH_AVAILABLE, _torch, _torchaudio, _model
    if _TORCH_AVAILABLE is not None:
        return _TORCH_AVAILABLE

    try:
        import torch
        import torchaudio
        _torch = torch
        _torchaudio = torchaudio
    except ImportError as e:
        _TORCH_AVAILABLE = False
        logger.warning(
            "torch/torchaudio not installed — AI Enhance unavailable. Install with: "
            "pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu "
            "(see requirements.txt) (%s)", e,
        )
        return False

    if _VENDOR_DIR not in sys.path:
        # Must resolve as a genuine top-level `biodenoising` module, not
        # app.services.something — see _vendor/biodenoising/__init__.py's
        # own docstring for why (the pretrained checkpoint's pickle
        # references this exact module path at unpickle time).
        sys.path.insert(0, _VENDOR_DIR)

    try:
        _model = _load_model()
    except Exception as e:
        _TORCH_AVAILABLE = False
        logger.warning("AI Enhance model failed to load: %s", e)
        return False

    _TORCH_AVAILABLE = True
    logger.info("AI Enhance model loaded (biodenoising16k_dns48, CPU inference)")
    return True


def _load_model():
    """Build the Demucs architecture and load the pretrained checkpoint.
    Weights are cached on the persistent data volume
    (settings.ai_models_dir) via torch.hub's own model_dir/file_name
    caching — not torch's default $HOME cache, which may not survive a
    container rebuild on Unraid. torch.hub.load_state_dict_from_url
    already skips the download when the cached file is present, so no
    separate existence check is needed here."""
    from biodenoising.denoiser.demucs import Demucs
    from biodenoising.denoiser.utils import load_model_state_dict

    Path(settings.ai_models_dir).mkdir(parents=True, exist_ok=True)

    model = Demucs(hidden=48, sample_rate=MODEL_SAMPLE_RATE)
    logger.info("Loading AI Enhance model weights (~75MB, cached after first run) from %s", BIO_DNS_48_URL)
    state_dict = _torch.hub.load_state_dict_from_url(
        BIO_DNS_48_URL, map_location="cpu",
        model_dir=str(settings.ai_models_dir), file_name=MODEL_FILENAME,
    )
    if isinstance(state_dict, dict) and "model" in state_dict:
        state_dict = state_dict["model"]["state"]
    model = load_model_state_dict(model, state_dict)
    model.eval()
    return model


def is_available() -> bool:
    """Whether AI Enhance can actually run in this environment (torch
    installed and the model loads). Cheap to call repeatedly — result is
    cached after the first call, same convention as
    bat_species_id.is_available()."""
    return _ensure_loaded()


def enhance_wav(
    wav_path: str,
    output_dir: str,
    cache_id: str,
    dry: float = 0.1,
    low_hz: float = 500.0,
) -> str:
    """
    Run the AI Enhance neural-denoising pass on a bird WAV file (a short
    detection clip or a full recording) and write the result to
    {output_dir}/{cache_id}_aienhanced.wav.

    Pipeline:
      0. Rumble high-pass (audio_processor.apply_rumble_highpass, same
         filter Live Detect and the classical Rumble Removed toggle
         use) at low_hz, applied BEFORE the neural pass — added
         directly in response to AI Enhance still sounding noisy: the
         model alone doesn't specifically target rumble/low-frequency
         content the way this simple filter does, so residual hum/
         traffic rumble could survive the denoising pass untouched.
         Stripping it first also means the model isn't spending any of
         its own capacity on that content, rather than fighting it
         after the fact.
      1. Downmix to mono, resample to the model's native 16kHz via
         torchaudio's sinc-interpolation resampler (julius isn't a
         dependency here, unlike upstream — torchaudio's own resample is
         the quality-equivalent, already-available replacement).
      2. Zero-pad to the model's required valid_length (a plain conv-net
         receptive-field constraint of the Demucs architecture itself,
         not an arbitrary choice).
      3. Single forward pass through the pretrained model — one shot
         over the whole (padded) clip, no streaming/chunking. Fast
         enough on CPU for a single on-demand recording/clip (roughly
         0.2-0.3x realtime measured during development — see this
         module's own docstring), so this is fine as an on-demand,
         cache-on-first-request operation like every other
         audio_processor.py enhancement, not something meant to run
         continuously across every incoming recording.
      4. Dry/wet mix at the model's own sample rate: `dry` fraction of
         the original (resampled, ALREADY rumble-filtered) signal
         blended back in with (1-dry) of the denoised estimate.
         dry=0.1 (this function's default, matching biodenoising's own
         upstream CLI default) softens occasional over-processed/
         artifact-y stretches a fully-wet pass can produce, at a small
         SNR cost — configurable via AppSettings.ai_enhance_dry.
      5. Resample back to the original sample rate.
      6. Soft-limit + normalize via the SAME
         audio_processor.soft_limit_and_normalize() the classical
         Enhanced pipeline's own step 4 uses — this is the concrete
         "increase call level" half of what AI Enhance does; steps 0
         and 3 above are the "reduce background" half.

    Raises RuntimeError if AI Enhance isn't available (not installed, or
    the model failed to load) — callers should check is_available()
    first and surface a clear error rather than let this raise blind.
    """
    if not _ensure_loaded():
        raise RuntimeError(
            "AI Enhance is not available (torch/torchaudio not installed, "
            "or the model failed to load — check server logs)"
        )

    from .audio_processor import soft_limit_and_normalize, apply_rumble_highpass, _atomic_tmp_path

    out_dir_path = Path(output_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)
    out_path = out_dir_path / f"{cache_id}_aienhanced.wav"

    data, sr = sf.read(wav_path, always_2d=True)
    mono = np.mean(data, axis=1).astype(np.float32)
    # Step 0 — see docstring above. Applied at the file's own native
    # sample rate, before any resampling, matching exactly how the
    # classical pipeline applies it.
    mono = apply_rumble_highpass(mono, sr, low_hz).astype(np.float32)
    # Step 0b — a cricket or katydid chirping through the whole recording
    # is "animal sound" to the model, so it survives denoising. Measured
    # and notched first, the same as the classical Enhanced path.
    try:
        from .audio_processor import detect_periodic_tonal_pulses, notch_steady_tones
        tones = [p["freq_hz"] for p in detect_periodic_tonal_pulses(wav_path)]
        mono, notched = notch_steady_tones(mono, sr, tones)
        if notched:
            logger.info("AI Enhance %s: notched steady tones at %s Hz", cache_id,
                        ", ".join(f"{f:.0f}" for f in notched))
    except Exception as e:
        logger.debug("AI Enhance steady-tone notch skipped for %s: %s", cache_id, e)


    if len(mono) < 64:
        # Too short for a meaningful model pass — just copy through,
        # same convention as enhance_audio()'s own short-clip guard.
        tmp_path = _atomic_tmp_path(out_path)
        sf.write(tmp_path, mono, sr, subtype="PCM_16")
        os.replace(tmp_path, str(out_path))
        return str(out_path)

    t_start = time.time()
    audio_t = _torch.from_numpy(mono).float().unsqueeze(0)  # (1, samples)
    if sr != MODEL_SAMPLE_RATE:
        audio_t = _torchaudio.functional.resample(audio_t, sr, MODEL_SAMPLE_RATE)
    n_native = audio_t.shape[-1]

    valid_len = _model.valid_length(n_native)
    pad = valid_len - n_native
    if pad > 0:
        audio_t = _torch.nn.functional.pad(audio_t, (0, pad))

    with _torch.no_grad():
        estimate = _model(audio_t.unsqueeze(0))  # (1, 1, valid_len)
    estimate = estimate.squeeze(0).squeeze(0)[:n_native]
    noisy_16k = audio_t.squeeze(0)[:n_native]

    dry = max(0.0, min(1.0, dry))
    mixed = (1 - dry) * estimate + dry * noisy_16k

    if sr != MODEL_SAMPLE_RATE:
        mixed = _torchaudio.functional.resample(mixed.unsqueeze(0), MODEL_SAMPLE_RATE, sr).squeeze(0)

    out_audio = mixed.numpy()
    # Length can drift by a sample or two across the resample-down/up
    # round trip — trim/pad back to the original length so playback
    # duration and any downstream duration math (waveform display,
    # detection-overlay positioning) matches the source exactly.
    if len(out_audio) > len(mono):
        out_audio = out_audio[:len(mono)]
    elif len(out_audio) < len(mono):
        out_audio = np.pad(out_audio, (0, len(mono) - len(out_audio)))

    out_audio = _restore_high_band(out_audio, mono, sr)

    out_audio = soft_limit_and_normalize(out_audio.astype(np.float32))

    out_has_nan = bool(np.any(np.isnan(out_audio)))
    out_has_inf = bool(np.any(np.isinf(out_audio)))
    if out_has_nan or out_has_inf:
        logger.warning(
            "ai_enhance %s produced NaN/Inf in output — replacing with silence "
            "rather than writing/caching a corrupted file", cache_id,
        )
        out_audio = np.nan_to_num(out_audio, nan=0.0, posinf=0.0, neginf=0.0)

    logger.debug(
        "ai_enhance %s: sr=%d duration=%.1fs dry=%.2f inference_time=%.2fs",
        cache_id, sr, len(mono) / sr, dry, time.time() - t_start,
    )

    tmp_path = _atomic_tmp_path(out_path)
    sf.write(tmp_path, out_audio, sr, subtype="PCM_16")
    os.replace(tmp_path, str(out_path))
    return str(out_path)


def _frame_gate(x: np.ndarray, sr: int, reduction_db: float, margin_db: float, win_s: float = 0.05) -> np.ndarray:
    """Frame-level downward expander: 50ms frames near the signal's own
    median level are attenuated by up to reduction_db; frames margin_db
    or more above it pass untouched. Gain is smoothed over 3 frames to
    avoid audible stepping."""
    w = max(1, int(sr * win_s))
    n = len(x) // w
    if n < 3:
        return x
    frames = x[:n * w].reshape(n, w)
    db = 20 * np.log10(np.sqrt(np.mean(frames ** 2, axis=1) + 1e-15))
    thr = np.percentile(db, 50) + margin_db
    gain_db = np.where(db < thr, -reduction_db * np.clip((thr - db) / margin_db, 0, 1), 0.0)
    gain = np.convolve(10 ** (gain_db / 20), np.ones(3) / 3, mode="same")
    gain = np.repeat(gain, w)
    gain = np.pad(gain, (0, len(x) - len(gain)), mode="edge")
    return x * gain


def _band_snr_db(x: np.ndarray, sr: int) -> float:
    """95th minus 50th percentile of 50ms-frame level — same percentile
    approach as audio_processor.compute_snr_db."""
    w = max(1, int(sr * 0.05))
    n = len(x) // w
    if n < 3:
        return 0.0
    db = 20 * np.log10(np.sqrt(np.mean(x[:n * w].reshape(n, w) ** 2, axis=1) + 1e-15))
    return float(np.percentile(db, 95) - np.percentile(db, 50))


def _restore_high_band(denoised: np.ndarray, original: np.ndarray, sr: int) -> np.ndarray:
    """
    The model runs at 16kHz, so everything above 8kHz is lost — Tufted
    Titmouse calls reaching 9-11kHz were visibly truncated. This keeps
    the denoised output below SPLIT_CROSSOVER_HZ and restores the
    original (rumble-filtered) signal above it, gated so between-call
    noise is attenuated.

    Crossover uses zero-phase 4th-order Butterworth low/high-pass
    (sosfiltfilt): Butterworth is power-complementary, so the two
    zero-phase bands sum back flat (reconstruction error measured at
    about -110 dB on real recordings).

    The high band is only restored when it contains call-like content
    (its own SNR at least SPLIT_MIN_HIGH_BAND_SNR_DB). When it is just
    noise, the denoised output is returned unchanged, so recordings with
    nothing above 7kHz sound exactly as before.

    Measured on two real recordings:
      Tufted Titmouse (calls 8-11kHz): call-band SNR 19.9 -> 35.6 dB,
        calls preserved up to 12kHz instead of cut off around 9kHz.
      White-breasted Nuthatch (calls ~2kHz, high band SNR 1.6 dB):
        high band skipped, output identical to the previous version.
    """
    try:
        import scipy.signal as sps
    except ImportError:
        return denoised
    if sr <= 2 * SPLIT_CROSSOVER_HZ:
        return denoised
    hp = sps.butter(4, SPLIT_CROSSOVER_HZ, "high", fs=sr, output="sos")
    high = sps.sosfiltfilt(hp, original.astype(np.float64))
    if _band_snr_db(high, sr) < SPLIT_MIN_HIGH_BAND_SNR_DB:
        return denoised
    lp = sps.butter(4, SPLIT_CROSSOVER_HZ, "low", fs=sr, output="sos")
    low = sps.sosfiltfilt(lp, denoised.astype(np.float64))
    high = _frame_gate(high, sr, SPLIT_GATE_REDUCTION_DB, SPLIT_GATE_MARGIN_DB)
    return (low + high).astype(np.float32)
