"""
Chirp Lite's card picture of a recording: a clean spectrogram strip of the
bird band (1-10 kHz), no boxes or labels, contrast set per clip so faint
calls show, in Lite's night-meadow colors. Saved with the spectrograms as
{id}_spectrogram_strip<N>.png, so recording clean-up removes it too.
"""
import os
from typing import Optional

import numpy as np

LOW_HZ, HIGH_HZ = 1000, 10000
WIDTH, HEIGHT = 900, 150
# Dark green → green → sun yellow → cream (Theme colors in the app).
STOPS = [(0.0, (11, 26, 18)), (0.35, (20, 83, 52)), (0.62, (52, 168, 96)),
         (0.85, (250, 204, 21)), (1.0, (255, 248, 220))]


def _lut() -> np.ndarray:
    x = np.linspace(0, 1, 256)
    pos = [s[0] for s in STOPS]
    return np.stack([np.interp(x, pos, [s[1][c] for s in STOPS]) for c in range(3)], axis=1).astype(np.uint8)


LUT = _lut()


def image(samples: np.ndarray, rate: int) -> Optional[np.ndarray]:
    """HEIGHT×WIDTH×3 uint8, or None for a clip too short to draw."""
    n_fft = 1024 if rate <= 48000 else 2048
    hop = max(64, (len(samples) - n_fft) // (WIDTH * 4) or 64)
    if len(samples) < n_fft + hop:
        return None
    count = 1 + (len(samples) - n_fft) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(count)[:, None]
    frames = samples[idx] * np.hanning(n_fft)
    spec = np.abs(np.fft.rfft(frames, axis=1)).T          # freq × time
    freqs = np.fft.rfftfreq(n_fft, 1 / rate)
    band = (freqs >= LOW_HZ) & (freqs <= min(HIGH_HZ, rate / 2))
    db = 20 * np.log10(spec[band] + 1e-10)
    # Each frequency row minus its median removes steady hum and hiss; each
    # time column minus its median removes clicks and gusts that cover every
    # pitch at once. A call stands above both.
    db -= np.median(db, axis=1, keepdims=True)
    db -= np.maximum(np.median(db, axis=0, keepdims=True), 0)
    lo, hi = np.percentile(db, 82), np.percentile(db, 99.8)
    v = np.clip((db - lo) / max(hi - lo, 1e-6), 0, 1) ** 0.9
    v = v[::-1]                                           # high pitch on top
    from PIL import Image
    # Height: average neighbouring bins. Width: keep the loudest moment of
    # each column, so a short call isn't thinned away when the clip is squeezed.
    v = np.asarray(Image.fromarray((v * 255).astype(np.uint8)).resize((v.shape[1], HEIGHT), Image.BOX))
    cols = v.shape[1]
    if cols >= WIDTH:
        edges = np.linspace(0, cols, WIDTH + 1).astype(int)
        small = np.maximum.reduceat(v, edges[:-1], axis=1)
    else:
        small = np.asarray(Image.fromarray(v).resize((WIDTH, HEIGHT), Image.BILINEAR))
    return LUT[small]


VERSION = 2   # bump when the picture changes; older files are replaced on request


def path_for(spectrograms_dir: str, recording_id: str, version: int = VERSION) -> str:
    tag = "strip" if version == 1 else f"strip{version}"
    return os.path.join(spectrograms_dir, f"{recording_id}_spectrogram_{tag}.png")


def build(wav_path: str, out_path: str) -> bool:
    try:
        import soundfile as sf
        y, rate = sf.read(wav_path, always_2d=True, dtype="float32")
    except Exception:
        return False
    rgb = image(y.mean(axis=1), rate)
    if rgb is None:
        return False
    from PIL import Image
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = out_path + ".tmp.png"
    Image.fromarray(rgb).save(tmp, optimize=True)
    os.replace(tmp, out_path)
    folder, name = os.path.split(out_path)
    rid = name.split("_spectrogram_")[0]
    for v in range(1, VERSION):
        try:
            os.remove(path_for(folder, rid, v))
        except OSError:
            pass
    return True
