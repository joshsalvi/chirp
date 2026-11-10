"""
The song line: a one-row picture of a recording for the players on the
Standard dashboard and in Chirp Lite. Bars are the clip's loudness in the
bird band (1.5–9 kHz). Where a bird was identified comes from its
detections, overlapping windows merged, and is shown as a highlighted range.
No per-call marks: BirdNET labels 3–5 s windows, so a mark placed from
loudness can land on another bird or noise. `calls` stays in the response,
always empty, because Chirp Lite 1.1 for iPhone expects the key.

Computed from the WAV on request and kept in memory (about 70 numbers per
recording), so there's nothing to store.
"""
import os
from collections import OrderedDict
from typing import Optional

import numpy as np

FRAME_S = 0.125           # analysis step
LOW_HZ, HIGH_HZ = 1500, 9000
BARS = 70

_cache: "OrderedDict[tuple, tuple]" = OrderedDict()
_CACHE_MAX = 256


def merge(spans):
    """Overlapping or touching (start, end) pairs → sorted, merged pairs."""
    out = []
    for a, b in sorted((float(a), float(b)) for a, b in spans if b > a):
        if out and a <= out[-1][1] + 0.01:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [[round(a, 2), round(b, 2)] for a, b in out]


def band_energy(samples: np.ndarray, rate: int) -> np.ndarray:
    """RMS in the bird band for each FRAME_S step."""
    hop = max(64, int(rate * FRAME_S))
    n = len(samples) // hop
    if n == 0:
        return np.zeros(0)
    frames = samples[: n * hop].reshape(n, hop) * np.hanning(hop)
    spec = np.abs(np.fft.rfft(frames, axis=1))
    freqs = np.fft.rfftfreq(hop, 1 / rate)
    band = (freqs >= LOW_HZ) & (freqs <= HIGH_HZ)
    return np.sqrt((spec[:, band] ** 2).mean(axis=1))


def _energy(path: str) -> Optional[np.ndarray]:
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        return None
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    try:
        import soundfile as sf
        y, rate = sf.read(path, always_2d=True, dtype="float32")
    except Exception:
        return None
    e = band_energy(y.mean(axis=1), rate)
    _cache[key] = e
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)
    return e


def bars_of(energy: np.ndarray, count: int = BARS) -> list:
    """The loudest step in each of `count` slices, scaled above the noise floor to 0…1."""
    if len(energy) == 0:
        return []
    floor = float(np.percentile(energy, 15))
    top = float(energy.max())
    span = max(top - floor, 1e-9)
    edges = np.linspace(0, len(energy), count + 1).astype(int)
    out = []
    for i in range(count):
        part = energy[edges[i]:max(edges[i] + 1, edges[i + 1])]
        out.append(round(float(np.clip((part.max() - floor) / span, 0, 1)), 3))
    return out


def build(path: Optional[str], duration: float, segments: dict, bird: Optional[str]) -> dict:
    """The song line for one recording. segments: {bird: [(start, end), …]}."""
    merged = {name: merge(spans) for name, spans in segments.items()}
    energy = _energy(path) if path else None
    if energy is not None and len(energy):
        duration = duration or len(energy) * FRAME_S
    return {
        "duration": round(float(duration or 0), 2),
        "bird": bird,
        "bars": bars_of(energy) if energy is not None else [],
        "segments": merged,
        "calls": [],
    }
