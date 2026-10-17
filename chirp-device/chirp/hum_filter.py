"""
Mains hum filter (1.4.2).

A mic cable near a power supply, or a ground loop between the Pi, its power
supply and the network, adds a steady tone at the mains frequency and its
harmonics (60, 180, 300 Hz… in North America, 50, 150, 250 Hz… elsewhere).
On one station it was the loudest thing in every recording: 60 Hz at
-40 dBFS, about 11 dB above everything else combined.

This removes it with narrow notches (3 Hz wide) at the mains frequency and
each multiple up to 1 kHz, so owl hoots between the harmonics are kept,
unlike a low cut. One filter per mic, run on each chunk before anything else
sees the audio (detection, pre-roll, recordings, night audio).

config audio.hum_filter: "auto" (default), "60", "50" or "off". "auto" looks
for hum in the first 10 s from each mic and every 5 minutes after, and only
filters when a mains tone stands at least 10 dB above its neighbours.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

MAX_HZ = 1000.0          # notch harmonics up to here
BANDWIDTH_HZ = 3.0       # each notch's -3 dB width
DETECT_SECONDS = 10.0
RECHECK_SECONDS = 300.0
MIN_PROMINENCE_DB = 10.0  # turn on at this
OFF_PROMINENCE_DB = 5.0   # once on, only turn off below this, twice in a row


def _design(f0: float, sr: int) -> np.ndarray:
    from scipy.signal import iirnotch, tf2sos
    secs = []
    k = 1
    while k * f0 <= min(MAX_HZ, sr / 2 - BANDWIDTH_HZ):
        f = k * f0
        b, a = iirnotch(f, f / BANDWIDTH_HZ, fs=sr)
        secs.append(tf2sos(b, a))
        k += 1
    return np.vstack(secs)


def hum_prominence(y: np.ndarray, sr: int, f0: float, harmonics: int = 5) -> float:
    """Strongest of the first few mains harmonics, in dB above the spectrum
    within 10 Hz either side of it (1 Hz resolution)."""
    from scipy.signal import welch
    n = min(len(y), sr)
    if n < sr // 4:
        return 0.0
    f, p = welch(y.astype(np.float64), sr, nperseg=n)
    pd = 10 * np.log10(p + 1e-20)
    df = f[1] - f[0]
    best = 0.0
    for k in range(1, harmonics + 1):
        fk = k * f0
        if fk > sr / 2 - 12:
            break
        i = int(round(fk / df))
        peak = pd[max(0, i - 1):i + 2].max()
        side = np.r_[pd[max(0, i - int(10 / df)):max(0, i - int(3 / df))],
                     pd[i + int(3 / df) + 1:i + int(10 / df) + 1]]
        if len(side):
            best = max(best, float(peak - np.median(side)))
    return best


def measure_mains(y: np.ndarray, sr: int) -> tuple:
    """(50.0 or 60.0, its prominence in dB), whichever stands out more."""
    p50, p60 = hum_prominence(y, sr, 50.0), hum_prominence(y, sr, 60.0)
    return (60.0, p60) if p60 >= p50 else (50.0, p50)


def detect_mains(y: np.ndarray, sr: int, threshold: float = MIN_PROMINENCE_DB) -> Optional[float]:
    """50.0, 60.0, or None when neither stands out."""
    f0, p = measure_mains(y, sr)
    return f0 if p >= threshold else None


class HumFilter:
    """Streaming notch filter for one mic. process() takes and returns mono
    float32 chunks of any length; filter state carries across chunks."""

    def __init__(self, sr: int, mode: str = "auto", name: str = "mic"):
        self.sr = sr
        self.mode = str(mode or "auto").lower()
        self.name = name
        self.f0: Optional[float] = None
        self._sos = None
        self._zi = None
        self._buf: list = []
        self._buffered = 0
        self._since_check = 0
        self._quiet_checks = 0
        self.last_db: Optional[float] = None   # hum level at the last check, dB above its neighbours
        if self.mode in ("50", "60"):
            self._set(float(self.mode))

    @property
    def active(self) -> bool:
        return self._sos is not None

    def _set(self, f0: Optional[float]) -> None:
        if f0 == self.f0:
            return
        self.f0 = f0
        if f0 is None:
            self._sos = self._zi = None
            logger.info("Hum filter (%s): no mains hum found; off", self.name)
            return
        self._sos = _design(f0, self.sr)
        self._zi = np.zeros((self._sos.shape[0], 2))
        logger.info("Hum filter (%s): removing %g Hz hum and harmonics up to %g Hz",
                    self.name, f0, MAX_HZ)

    def _watch(self, x: np.ndarray) -> None:
        """auto: gather DETECT_SECONDS of unfiltered audio, decide, then
        look again every RECHECK_SECONDS."""
        if self._since_check > 0:
            self._since_check -= len(x)
            return
        self._buf.append(x.copy())
        self._buffered += len(x)
        if self._buffered >= DETECT_SECONDS * self.sr:
            y = np.concatenate(self._buf)
            self._buf, self._buffered = [], 0
            self._since_check = int(RECHECK_SECONDS * self.sr)
            try:
                f0, db = measure_mains(y, self.sr)
                self.last_db = round(db, 1)
                logger.info("Hum check (%s): %g Hz stands %.1f dB above its neighbours", self.name, f0, db)
                if self._sos is None:
                    if db >= MIN_PROMINENCE_DB:
                        self._set(f0)
                elif db < OFF_PROMINENCE_DB:
                    # Birdsong or rain can hide the hum for a moment; one
                    # quiet check (as on 17 Oct, off for 5 minutes at a
                    # time) shouldn't let it back in.
                    self._quiet_checks += 1
                    if self._quiet_checks >= 2:
                        self._quiet_checks = 0
                        self._set(None)
                else:
                    self._quiet_checks = 0
                    if f0 != self.f0 and db >= MIN_PROMINENCE_DB:
                        self._set(f0)
            except Exception as e:        # never let detection break capture
                logger.warning("Hum filter (%s): detection failed: %s", self.name, e)

    def process(self, chunk: np.ndarray) -> np.ndarray:
        if self.mode == "off" or chunk is None or len(chunk) == 0:
            return chunk
        x = np.asarray(chunk)
        if x.ndim != 1:
            return chunk
        if self.mode == "auto":
            self._watch(x)
        if self._sos is None:
            return chunk
        from scipy.signal import sosfilt
        out, self._zi = sosfilt(self._sos, x.astype(np.float64), zi=self._zi)
        return out.astype(x.dtype, copy=False)
