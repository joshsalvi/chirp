"""
Chirp Server — Audio Processor
Generates mel spectrograms and extracts detection clips.

Performance notes:
- librosa is imported once at module level and reused
- Spectrograms are generated at target_sr=22050 (fast enough for display; BirdNET uses 48k)
- DPI is 120 for cached files (96 for thumbnails generated on-demand)
- matplotlib Figure/Canvas are created fresh per call (thread-safe, avoids global state)
"""
import logging
import os

# Bump whenever enhance_audio()'s actual output would change for a
# recording that was already processed under an older version — cached
# WAVs are keyed by recording/detection ID alone (see api/recordings.py's
# cache_path construction), so a pure algorithm change with no filename
# change would otherwise serve the OLD output forever, indistinguishable
# from a legitimate cache hit. Reported directly: the rumble-removal
# normalization fix (skip the boost-to-peak step for bandpass-only mode)
# had no visible effect for any recording that had been rumble-removed
# even once before that fix shipped, because /audio/rumble-removed's
# cache check has no way to tell an old-algorithm file from a new one —
# this is the general fix, replacing the need for a bespoke content-
# sniffing heuristic (c.f. _is_stale_bat_enhanced_cache in recordings.py,
# which solved the same class of bug for the bat-downshift fix the hard
# way, by inspecting sample rate — not reusable here since this change
# doesn't alter sample rate). v2 = the bandpass→highpass +
# boost=apply_noise_reduction fix.
DSP_VERSION = "v3"

import subprocess
import uuid
import json
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

logger = logging.getLogger("chirp.audio_processor")


def soft_limit_and_normalize(audio: np.ndarray, target_peak: float = 0.92, boost: bool = True) -> np.ndarray:
    """
    Gently compress only what's above 90% amplitude (tanh soft-knee) rather
    than linearly rescaling the whole signal to a fixed peak, which can
    audibly squash dynamics around one loud transient. Then, if `boost` is
    true, brings the overall level to `target_peak` for a consistent,
    comfortable loudness.

    Extracted out of enhance_audio()'s own step 4 (unchanged logic) so
    ai_enhance.py's neural-denoising path can reuse the exact same
    post-processing — the actual "increase call level" half of what an
    AI-enhanced clip does, on top of noise suppression handling the
    "reduce background" half. Both callers get identical, consistently-
    tuned loudness behavior rather than two independently-drifting copies.

    boost=False (used by the plain rumble high-pass, which runs with no
    accompanying noise reduction): still applies the tanh safety limiter
    against genuine clipping, but skips the upward boost-to-target-peak
    step entirely. Reported directly: rumble removal still sounded noisy
    after the filter itself was fixed to match Live Detect (a plain
    high-pass, no bandpass) — root cause was THIS step, not the filter.
    A recording's peak is very often set by the low-frequency rumble
    itself; once that's filtered out, whatever's left (the call, but
    also any real ambient hiss/noise) is much quieter than the original
    peak, and boosting it back up to a fixed 0.92 amplifies that ambient
    noise right along with the call — confirmed directly: a synthetic
    clip's true (rumble-free) hiss floor measured ~0.02 RMS, but came out
    at ~0.09 RMS after the old boost-everything-up behavior, a ~4x
    amplification nobody asked for. Live Detect's own rumble filter
    never renormalizes at all — it just filters and passes the result
    through at whatever level results — so boost=False here matches
    that exactly for the one caller (plain rumble removal) that has no
    noise-suppression step of its own to justify a boost afterward.
    """
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if peak <= 1e-6:
        return audio
    out = audio
    if peak > 0.90:
        threshold = 0.90
        sign = np.sign(out)
        mag_ratio = np.abs(out) / peak
        over = mag_ratio > threshold
        compressed = np.where(
            over,
            threshold + (1 - threshold) * np.tanh(
                (mag_ratio - threshold) / max(1 - threshold, 1e-6)
            ),
            mag_ratio,
        )
        out = sign * compressed * peak
    if not boost:
        return out
    new_peak = float(np.max(np.abs(out))) or 1.0
    return out / new_peak * target_peak


def apply_rumble_highpass(audio: np.ndarray, sr: float, low_hz: float) -> np.ndarray:
    """
    Plain single-pass 2nd-order Butterworth high-pass — deliberately the
    same filter shape LiveDetect.jsx's own "Cut low rumble" chain uses (a
    single BiquadFilterNode: causal, single pass, no zero-phase
    doubling), not a bandpass and not the filtfilt-based steep design
    this whole function replaced (see enhance_audio()'s own docstring
    for the "adds a lot of noise" bug that came from that). Nothing
    above the cutoff is touched at all.

    Factored out here so ai_enhance.py's neural-denoising path can run
    the exact same rumble strip on its input before the model ever
    sees it, rather than duplicating this filter design in two places —
    requested directly, since AI Enhance had no rumble-specific
    filtering of its own and relied entirely on the neural model to
    suppress everything, low frequencies included, which it doesn't
    specifically target the way this simple filter does.
    """
    nyq = sr / 2.0
    hp_cutoff = max(low_hz / nyq, 0.001)
    sos = _spsignal.butter(2, hp_cutoff, btype="high", output="sos")
    return _spsignal.sosfilt(sos, audio)


def compute_snr_db(wav_path: str, low_hz: float = 500.0) -> "float | None":
    """
    A rough, species-agnostic signal-to-noise estimate for a whole
    recording — added after measuring, on two real user-provided
    recordings, that nothing anywhere computed or surfaced this at all:
    a genuinely noisy recording (in-band SNR ~4dB on one real example)
    looked no different from a clean one anywhere in the app, so there
    was no way to know AI Enhance would help without exporting the audio
    and measuring it by hand.

    Deliberately NOT species-specific (that would need a known call
    band, which isn't available before/independent of analysis) —
    high-passes at low_hz first (same cutoff and filter as
    apply_rumble_highpass, so this doesn't independently invent a
    second rumble definition) to avoid exactly the failure mode
    confirmed directly on that same real example: a broadband
    percentile measure with no high-pass was dominated by loud
    low-frequency noise transients and swung the wrong direction
    (looked WORSE after denoising that demonstrably helped the actual
    call). After the high-pass, this is the 95th percentile of 100ms-
    window RMS (the loudest, most call-like moments) minus the 50th
    percentile (the typical background) — deliberately percentile-
    based rather than true peak/floor, so a handful of isolated
    transient noise spikes (a car door, a gust) don't swing the whole
    number either direction.

    Returns None (not 0.0 or a raised exception) for anything that
    can't be measured — missing file, unreadable format, a clip too
    short for even one 100ms window — since a missing quality signal
    should read as "unknown," never as "confirmed clean" or a crash
    partway through a recording's own processing pipeline.
    """
    try:
        data, sr = sf.read(wav_path, always_2d=True)
        mono = np.mean(data, axis=1).astype(np.float64)
        if len(mono) < int(sr * 0.1):
            return None
        filtered = apply_rumble_highpass(mono, sr, low_hz)

        win = int(sr * 0.1)
        n_wins = len(filtered) // win
        if n_wins < 2:
            return None
        frame_rms = np.sqrt(
            np.mean(filtered[:n_wins * win].reshape(n_wins, win) ** 2, axis=1) + 1e-12
        )
        frame_db = 20 * np.log10(frame_rms + 1e-12)
        signal_db = float(np.percentile(frame_db, 95))
        floor_db = float(np.percentile(frame_db, 50))
        return round(signal_db - floor_db, 1)
    except Exception as e:
        logger.warning("compute_snr_db failed for %s: %s", wav_path, e)
        return None


def measure_detection_bands(wav_path: str, segments: list,
                            fmin: float = 150.0, fmax: float = 12000.0,
                            exclude_hz: Optional[list] = None) -> list:
    """
    Where each detection's sound sits in frequency, measured from the audio.

    For each (start_s, end_s) segment: the segment's loud-frame spectrum
    minus the recording's median spectrum (the steady background). The
    peak of that excess, plus the band spanning the middle 80 % of bins
    that rise at least halfway (in dB) from background to the peak.
    Vision models read frequency axes poorly, so AI Second Opinion gets
    these numbers alongside the image.

    exclude_hz: centre frequencies of known steady sources (a measured
    cricket, say) to skip, +/-250 Hz each.
    Returns one dict per segment ({peak_hz, low_hz, high_hz, excess_db}),
    or None where nothing stands out from the background.
    """
    from scipy import signal as sps
    data, sr = sf.read(wav_path, always_2d=True)
    x = data.mean(axis=1).astype(np.float64)
    if len(x) < sr // 2:
        return [None] * len(segments)

    def spectra(nper):
        f, t, S = sps.stft(x, sr, nperseg=nper, noverlap=nper - nper // 4, boundary=None)
        P = np.abs(S) ** 2 + 1e-20
        sel = (f >= fmin) & (f <= min(fmax, sr / 2 - 100))
        for fx in exclude_hz or []:
            sel &= np.abs(f - float(fx)) > 250.0
        f, P = f[sel], P[sel]
        return f, t, P, 10 * np.log10(np.median(P, axis=1))

    def band(f, excess, absolute):
        base = float(np.median(excess))      # noise fluctuation sits here
        if excess.max() - base < 6.0:
            return None
        # bins in the top half (in dB) between background and the peak
        w = np.clip(excess - (base + 0.5 * (excess.max() - base)), 0, None)
        c = np.cumsum(w) / w.sum()
        return {
            "peak_hz": float(f[int(np.argmax(excess))]),
            "low_hz": float(f[int(np.searchsorted(c, 0.1))]),
            "high_hz": float(f[min(len(f) - 1, int(np.searchsorted(c, 0.9)))]),
            "excess_db": float(excess.max() if absolute else excess.max() - base),
        }

    # Sustained sound (songs, whistles, hoots): 85 ms frames, the loud 10 %.
    fs, ts, Ps, floor_s = spectra(4096)
    # Short calls (chips, "pik"s, chickadee "chick"s, 20-50 ms) vanish in
    # those frames: 21 ms frames and the loudest 0.5 %, smoothed over
    # 150 Hz. On 17 Oct a Downy Woodpecker and chickadee calling at
    # 6-8 kHz read as "nothing above the background" without this
    # (8-20 dB here, 3.6 dB in a stretch with no calls).
    ft, tt, Pt, floor_t = spectra(1024)
    k = max(1, int(round(150.0 / (ft[1] - ft[0]))))
    out = []
    for start, end in segments:
        best = None
        cols = (ts >= float(start)) & (ts <= float(end))
        if cols.sum() >= 2:
            best = band(fs, 10 * np.log10(np.percentile(Ps[:, cols], 90, axis=1)) - floor_s, True)
        cols = (tt >= float(start)) & (tt <= float(end))
        if best is None and cols.sum() >= 8:
            ex = 10 * np.log10(np.percentile(Pt[:, cols], 99.5, axis=1)) - floor_t
            best = band(ft, np.convolve(ex, np.ones(k) / k, mode="same"), False)
        out.append(best)
    return out


def _norm_acf(x: np.ndarray, max_lag: int) -> np.ndarray:
    """Normalized autocorrelation for lags 0..max_lag (FFT-based)."""
    x = x - x.mean()
    n = len(x)
    if n < 4 or not np.any(x):
        return np.zeros(max_lag + 1)
    spec = np.fft.rfft(x, 2 * n)
    a = np.fft.irfft(spec * np.conj(spec))[: max_lag + 1]
    return a / a[0]


def _pulse_shape(P, f, fr: float, fc: float, env, lag: int) -> dict:
    """Frequency span and length of the pulses of a periodic source.
    Insects and beeps are narrow bands (a few hundred Hz); a chipmunk's
    "chip" or a bird's chip note is a short streak several kHz tall. At
    the strongest pulses, the span is the run of bins 10 dB over each bin's
    median level that includes fc; the length is how long the band stays
    within 6 dB of each pulse's peak."""
    try:
        pk, _ = _spsignal.find_peaks(env, distance=max(1, int(0.6 * lag)))
        if not len(pk):
            return {}
        pk = pk[np.argsort(env[pk])[::-1][:20]]
        floor = 10 * np.log10(np.median(P, axis=1) + 1e-20)
        ic = int(np.argmin(np.abs(f - fc)))
        lows, highs, lens = [], [], []
        for i in pk:
            col = 10 * np.log10(P[:, max(0, i - 1):i + 2].max(axis=1) + 1e-20) - floor
            if col[ic] < 10:
                continue
            lo = hi = ic
            while lo > 0 and col[lo - 1] >= 10:
                lo -= 1
            while hi < len(col) - 1 and col[hi + 1] >= 10:
                hi += 1
            lows.append(f[lo])
            highs.append(f[hi])
            a = b = i
            while a > 0 and env[a - 1] >= env[i] - 6:
                a -= 1
            while b < len(env) - 1 and env[b + 1] >= env[i] - 6:
                b += 1
            lens.append((b - a + 1) * fr)
        if not lows:
            return {}
        low, high = float(np.median(lows)), float(np.median(highs))
        return {"low_hz": round(low), "high_hz": round(high), "span_hz": round(high - low),
                "pulse_ms": round(1000 * float(np.median(lens)))}
    except Exception:
        return {}


def detect_periodic_tonal_pulses(
    wav_path: str,
    fmin: float = 1000.0,
    fmax: float = 12000.0,
    min_prominence_db: float = 5.0,
    min_strength: float = 0.35,
    min_coverage: float = 0.6,
    window_s: float = 5.0,
    period_range: tuple = (0.1, 3.0),
    max_candidates: int = 6,
) -> list:
    """
    Finds a narrowband sound repeating at a steady rate across most of a
    recording — cricket and katydid chirps, or a beeping device. These
    show up on a spectrogram as a row of evenly spaced dashes at one
    height, and a vision model reviewing the image missed one in a real
    recording (a pulse at roughly 5 kHz about once a second, all the way
    through), so this gives AI Second Opinion a measured hint instead of
    relying on the image alone.

    1. Long-term average spectrum: a steady tonal source leaves a narrow
       peak at least min_prominence_db above the surrounding 1 kHz.
    2. For each peak, the level envelope in a 300 Hz band around it is
       tested for periodicity with autocorrelation.
    3. The same period has to hold in at least min_coverage of the 5 s
       windows, so a short repeated bird phrase doesn't qualify.

    Tested on a real field cricket recording (Gryllus pennsylvanicus,
    chirps every 0.42 s at 4.8 kHz, detected alone and mixed into two
    real bird recordings at three levels) and on synthetic pulses; no
    detections on the bird recordings alone, a steady whine, or random
    broadband bursts.

    Returns one dict per source (strongest first) with freq_hz, period_s,
    strength (0-1), coverage (0-1) and prominence_db. Returns [] on any
    failure or for recordings shorter than two windows.
    """
    try:
        from scipy.ndimage import median_filter
        data, sr = sf.read(wav_path, always_2d=True)
        x = np.mean(data, axis=1).astype(np.float64)
        if len(x) / sr < 2 * window_s:
            return []
        nper, hop = 2048, 512
        f, _, Z = _spsignal.stft(x, sr, nperseg=nper, noverlap=nper - hop, boundary=None)
        P = np.abs(Z) ** 2
        fr = hop / sr
        fmax = min(fmax, sr / 2 - 500)
        sel = (f >= fmin) & (f <= fmax)
        fsel = f[sel]
        df = f[1] - f[0]
        ltas = 10 * np.log10(P[sel].mean(axis=1) + 1e-20)
        prom = ltas - median_filter(ltas, size=int(1000 / df) | 1, mode="nearest")
        peaks, props = _spsignal.find_peaks(prom, height=min_prominence_db, distance=max(1, int(400 / df)))
        order = np.argsort(props["peak_heights"])[::-1][:max_candidates]
        lag_lo, lag_hi = int(period_range[0] / fr), int(period_range[1] / fr)
        win = int(window_s / fr)
        found = []
        for k in order:
            fc = float(fsel[peaks[k]])
            band = (f >= fc - 150) & (f <= fc + 150)
            env = 10 * np.log10(P[band].mean(axis=0) + 1e-20)
            env = np.clip(env - median_filter(env, size=int(2.0 / fr) | 1, mode="nearest"), 0, None)
            a = _norm_acf(env, lag_hi)
            seg = a[lag_lo:lag_hi + 1]
            pk, _ = _spsignal.find_peaks(seg)
            if not len(pk):
                continue
            best = int(pk[np.argmax(seg[pk])])
            strength = float(seg[best])
            if strength < min_strength:
                continue
            lag = best + lag_lo
            half = lag // 2
            if half - 2 >= lag_lo and a[half - 2:half + 3].max() >= 0.8 * strength:
                lag = half - 2 + int(np.argmax(a[half - 2:half + 3]))
            tol = max(2, int(0.1 * lag))
            hits = total = 0
            for s0 in range(0, len(env) - win + 1, win):
                total += 1
                w = env[s0:s0 + win]
                if np.any(w) and _norm_acf(w, lag + tol + 1)[lag - tol:lag + tol + 1].max() >= 0.8 * min_strength:
                    hits += 1
            coverage = hits / max(total, 1)
            if coverage < min_coverage:
                continue
            found.append({
                "freq_hz": round(fc),
                "period_s": round(lag * fr, 2),
                "strength": round(strength, 2),
                "coverage": round(coverage, 2),
                "prominence_db": round(float(prom[peaks[k]]), 1),
                **_pulse_shape(P, f, fr, fc, env, lag),
            })
        found.sort(key=lambda r: -r["strength"] * r["prominence_db"])
        # one entry per source: a chirp with harmonics or broadband onsets
        # shows up at several frequencies with the same period
        out = []
        for r in found:
            if any(abs(r["period_s"] - o["period_s"]) <= 0.1 * o["period_s"] for o in out):
                continue
            out.append(r)
        return out
    except Exception as e:
        logger.warning("detect_periodic_tonal_pulses failed for %s: %s", wav_path, e)
        return []


def measure_background_sounds(wav_path: str, boxes: Optional[list] = None,
                              fmin: float = 150.0, fmax: float = 14000.0) -> dict:
    """
    Non-bird sounds a vision model tends to skip on a spectrogram:

    bursts   Short, loud, broadband events (0.06-0.9 s) whose energy spans
             at least 1.5 kHz and starts below 2 kHz: the shape of a dog
             bark (harsh harmonic stack, fast onset), another mammal call,
             a voice, or a knock. Bird notes are narrowband and don't
             qualify. Grouped into one entry per recording with times.
    bands    Steady bands above 1.5 kHz: the recording's quiet-frame
             spectrum (20th percentile over time) against a smooth
             lower-envelope fit across frequency. A span rising >= 6 dB
             for >= 300 Hz is a persistent hum or insect/electrical buzz,
             present the whole time. Rumble below 400 Hz is reported
             separately as rumble_db.

    boxes: [(start_s, end_s, name)] detection boxes; bursts inside one are
    tagged with that name (a bark BirdNET labeled as a bird).
    Returns {"bursts": [...], "bands": [...], "rumble_db": float|None};
    empty lists on failure.
    """
    out = {"bursts": [], "bands": [], "rumble_db": None}
    try:
        from scipy.ndimage import median_filter, uniform_filter1d
        data, sr = sf.read(wav_path, always_2d=True)
        x = data.mean(axis=1).astype(np.float64)
        if len(x) < sr:
            return out
        nper, hop = 1024, 256
        f, t, Z = _spsignal.stft(x, sr, nperseg=nper, noverlap=nper - hop, boundary=None)
        P = np.abs(Z) ** 2 + 1e-20
        fmax = min(fmax, sr / 2 - 200)
        sel = (f >= fmin) & (f <= fmax)
        f, P = f[sel], P[sel]
        L = 10 * np.log10(P)
        fr = hop / sr

        # ── steady bands ──────────────────────────────────────────────
        quiet = np.percentile(L, 20, axis=1)
        quiet = uniform_filter1d(quiet, size=5)
        lf = np.log10(f)
        keep = np.ones_like(lf, dtype=bool)
        for _ in range(4):                     # lower-envelope fit
            coef = np.polyfit(lf[keep], quiet[keep], 2)
            fit = np.polyval(coef, lf)
            keep = quiet <= fit + 1.0
            if keep.sum() < 10:
                break
        resid = quiet - fit
        low = f < 400
        if low.any():
            mid = (f >= 800) & (f <= 3000)
            if mid.any():
                out["rumble_db"] = round(float(np.median(quiet[low]) - np.median(quiet[mid])), 1)
        df = f[1] - f[0]
        hot = (resid >= 6.0) & (f >= 1500)
        i = 0
        while i < len(f):
            if not hot[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(f) and (hot[j + 1] or (j + 2 < len(f) and hot[j + 2])):
                j += 1
            if (j - i + 1) * df >= 300:
                seg = slice(i, j + 1)
                pk = i + int(np.argmax(resid[seg]))
                # persistence: fraction of frames where the band sits above
                # the fitted background by at least half its prominence
                lvl = L[seg].mean(axis=0)
                ref = float(np.mean(fit[seg]))
                cover = float(np.mean(lvl >= ref + 0.5 * float(resid[seg].mean())))
                out["bands"].append({
                    "low_hz": round(float(f[i])), "high_hz": round(float(f[j])),
                    "peak_hz": round(float(f[pk])),
                    "prominence_db": round(float(resid[pk]), 1),
                    "coverage": round(cover, 2),
                })
            i = j + 1
        out["bands"].sort(key=lambda b: -b["prominence_db"])
        out["bands"] = [b for b in out["bands"] if b["coverage"] >= 0.5][:3]

        # ── broadband bursts ─────────────────────────────────────────
        floor = np.median(L, axis=1, keepdims=True)
        exc = L - floor
        wide = (f >= 300) & (f <= 6000)
        # per frame: how many Hz of the 0.3-6 kHz range sit >= 12 dB up
        span = (exc[wide] >= 12.0).sum(axis=0) * df
        span = median_filter(span, size=3)
        on = span >= 1500
        k = 0
        events = []
        while k < len(on):
            if not on[k]:
                k += 1
                continue
            m = k
            while m + 1 < len(on) and (on[m + 1] or (m + 3 < len(on) and on[m + 2:m + 4].any())):
                m += 1
            dur = (m - k + 1) * fr
            if 0.06 <= dur <= 0.9:
                cols = slice(k, m + 1)
                e = np.percentile(exc[:, cols], 90, axis=1)
                up = f[e >= 12.0]
                if len(up) and up.min() < 2000 and up.max() - up.min() >= 1500:
                    events.append({
                        "t": round(float(t[k]), 2), "dur": round(dur, 2),
                        "low_hz": round(float(up.min())), "high_hz": round(float(np.percentile(up, 90))),
                        "peak_hz": round(float(f[int(np.argmax(e))])),
                        "level_db": round(float(e.max()), 1),
                    })
            k = m + 1
        if events:
            for ev in events:
                ev["in_box"] = next((n for s0, s1, n in (boxes or [])
                                     if s0 - 0.1 <= ev["t"] <= s1 + 0.1), None)
            # A continuous chorus trips every frame; bursts must be separable.
            total = len(on) * fr
            busy = sum(e["dur"] for e in events) / max(total, 1e-9)
            if busy <= 0.35:
                out["bursts"] = events
    except Exception as e:
        logger.warning("measure_background_sounds failed for %s: %s", wav_path, e)
    return out


def _atomic_tmp_path(out_path) -> str:
    """
    Build a same-directory temp path for an atomic write, preserving the
    real file extension so format-inference libraries (soundfile.write,
    matplotlib's savefig) still work correctly on the temp file.

    Used by every cache-writing call in this module: write to this path
    first, then os.replace(tmp_path, out_path) to publish atomically — a
    reader can then never observe a partially-written file, regardless
    of how many concurrent writers there are (e.g. two requests for the
    same recording's spectrogram arriving close together, plausible on
    mobile from a double-tap or a page re-render firing a duplicate
    request).

    Uses uuid4, not os.getpid(): confirmed by direct testing that PID is
    NOT sufficient — every thread within the same process shares the
    same PID, so concurrent requests handled by threads in one worker
    process (the realistic case, not just multiple separate worker
    processes) would all compute the IDENTICAL "unique" temp path under
    a PID-based scheme, and one thread's os.replace() could yank the
    file out from under another thread still writing to or reading from
    the same path — a real, different failure (FileNotFoundError) that
    this exact mistake produced on the very next test run after the
    first version of this fix.

    Inserting the temp marker BEFORE the extension (not appended after
    it) matters too: appending ".tmp<id>" after ".wav" or ".png" turned
    the file into "foo.wav.tmp12345", which both soundfile.write and
    matplotlib's savefig failed on outright, since each infers its
    output format from the filename's actual extension.
    """
    s = str(out_path)
    dot = s.rfind(".")
    unique = uuid.uuid4().hex[:12]
    if dot == -1:
        return f"{s}.tmp{unique}"
    return f"{s[:dot]}.tmp{unique}{s[dot:]}"


# Pre-import heavy libs at module load so first spectrogram is fast
try:
    import librosa as _librosa
    _LIBROSA_OK = True
except ImportError:
    _LIBROSA_OK = False
    logger.warning("librosa not installed — spectrogram generation unavailable")

try:
    import matplotlib
    matplotlib.use("Agg")   # non-interactive backend; must be set before pyplot
    import matplotlib.patches as _mpatches
    from matplotlib.colors import LinearSegmentedColormap as _LSC
    from matplotlib.figure import Figure as _Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg as _Canvas
    _MPL_OK = True
except ImportError:
    _MPL_OK = False
    logger.warning("matplotlib not installed — spectrogram generation unavailable")

try:
    import scipy.signal as _spsignal
    _SCIPY_OK = True
except ImportError:
    _SCIPY_OK = False
    logger.warning("scipy not installed — audio enhancement unavailable")

try:
    import noisereduce as _noisereduce
    _NOISEREDUCE_OK = True
except ImportError:
    _NOISEREDUCE_OK = False
    logger.warning("noisereduce not installed — audio enhancement unavailable")

# Detection overlay colours (stable mapping: species index → colour)
# Kept only as the "vivid" palette's own definition and for any legacy
# direct reference — actual per-species assignment now goes through
# pick_species_colors() below, which spreads colors evenly by how many
# species are actually present rather than indexing this sequentially.
# See frontend/src/lib/detectionColors.js for the JS mirror of this
# same logic — the two MUST stay in sync, or the spectrogram's own
# baked-in detection colors would disagree with the detection list
# rendered next to it.
_DET_COLORS = [
    "#ef4444", "#f97316", "#eab308", "#84cc16", "#22c55e",
    "#14b8a6", "#06b6d4", "#3b82f6", "#6366f1", "#a855f7",
    "#ec4899", "#f43f5e",
]

_DETECTION_PALETTES = {
    "vivid": _DET_COLORS,
    "colorblind_safe": [
        "#E69F00", "#56B4E9", "#009E73", "#F0E442",
        "#0072B2", "#D55E00", "#CC79A7", "#999999",
    ],
    "pastel": [
        "#fca5a5", "#fdba74", "#fde047", "#bef264", "#86efac",
        "#5eead4", "#67e8f9", "#93c5fd", "#a5b4fc", "#d8b4fe",
        "#f9a8d4", "#fda4af",
    ],
    "high_contrast": [
        "#ffffff", "#facc15", "#22d3ee", "#f472b6",
        "#4ade80", "#818cf8", "#fb923c", "#c084fc",
    ],
}


def spectrogram_filename(recording_id: str, conf_key, thumb: bool = False, palette: str = "vivid") -> str:
    """File name of a cached bird spectrogram: one per display threshold
    (conf_key), full or thumbnail ("_thumb2"), and colour palette (the
    default "vivid" has no suffix)."""
    suffix = "_thumb2" if thumb else ""
    pal = f"_pal-{palette}" if palette and palette != "vivid" else ""
    return f"{recording_id}_spectrogram_{conf_key}{suffix}{pal}.png"


def pick_species_colors(unique_species_names, palette_key="vivid"):
    """
    Returns {species_name: color_hex}, spreading assignments evenly
    around the chosen palette's own wheel based on how many species
    are actually present — not assigned sequentially from index 0 (see
    this module's own _DET_COLORS comment for why that was the actual
    bug: with only 2-3 species, sequential assignment always lands on
    whichever colors happen to sit next to each other at the start of
    the wheel). Must stay logically identical to
    frontend/src/lib/detectionColors.js's own pickSpeciesColors().
    """
    colors = _DETECTION_PALETTES.get(palette_key, _DET_COLORS)
    n = len(unique_species_names)
    result = {}
    for i, name in enumerate(unique_species_names):
        idx = 0 if n <= 1 else round(i * len(colors) / n) % len(colors)
        result[name] = colors[idx]
    return result

# Chirp dark-theme colour map (silence = near-black, loud = yellow-white)
_CMAP = None
def _get_cmap():
    global _CMAP
    if _CMAP is None and _MPL_OK:
        _CMAP = _LSC.from_list("chirp", [
            (0.04, 0.06, 0.08),
            (0.05, 0.15, 0.20),
            (0.05, 0.35, 0.30),
            (0.10, 0.60, 0.40),
            (0.50, 0.85, 0.40),
            (0.95, 0.98, 0.60),
        ], N=256)
    return _CMAP


# Species whose calls sit low enough that an 800 Hz high-pass would cut
# into the call itself, not just rumble: owls (Great Horned ~200-400 Hz,
# Barred ~300-600 Hz), doves and pigeons (coos ~400-700 Hz), grouse and
# bitterns. Same reasoning as chirp-device's Stage 1 low cutoff (150 Hz).
# Any detection of one of these drops the saved recording's rumble
# cutoff to LOW_FREQUENCY_HIGH_PASS_HZ.
LOW_FREQUENCY_CALLERS = {
    "Barred Owl", "Great Horned Owl", "Barn Owl", "Eastern Screech-Owl",
    "Western Screech-Owl", "Great Gray Owl", "Snowy Owl", "Long-eared Owl",
    "Short-eared Owl", "Boreal Owl", "Northern Saw-whet Owl",
    "Northern Hawk Owl", "Spotted Owl", "Burrowing Owl", "Flammulated Owl",
    "Whiskered Screech-Owl", "Elf Owl",
    "Mourning Dove", "Eurasian Collared-Dove", "Rock Pigeon", "White-winged Dove",
    "Band-tailed Pigeon", "Inca Dove", "Common Ground Dove",
    "Ruffed Grouse", "Spruce Grouse", "Dusky Grouse", "Sooty Grouse",
    "Sharp-tailed Grouse", "Greater Prairie-Chicken", "Greater Sage-Grouse",
    "American Bittern", "Least Bittern",
}
LOW_FREQUENCY_HIGH_PASS_HZ = 150.0


def notch_steady_tones(audio: np.ndarray, sr: float, freqs_hz, keep_band=None,
                       half_width_hz: float = 200.0) -> tuple:
    """
    Cut steady narrowband sources measured by detect_periodic_tonal_pulses
    (a cricket or katydid chirping all through the recording). Spectral
    gating can't remove them: they're in the noise profile only as an
    average, so every chirp still rises above the gate. A zero-phase
    band-stop +/-half_width_hz around each tone removes them outright.
    keep_band: (low_hz, high_hz) of the call itself; a tone inside it is
    left alone so the bird is never notched. Returns (audio, notched_hz).
    """
    if not _SCIPY_OK or not freqs_hz:
        return audio, []
    out = audio.astype(np.float64)
    done = []
    for fc in freqs_hz:
        fc = float(fc)
        if keep_band and keep_band[0] <= fc <= keep_band[1]:
            continue
        lo, hi = fc - half_width_hz, fc + half_width_hz
        if lo <= 50 or hi >= sr / 2 - 50:
            continue
        sos = _spsignal.butter(2, [lo, hi], btype="bandstop", fs=sr, output="sos")
        out = _spsignal.sosfiltfilt(sos, out)
        done.append(fc)
    return out.astype(np.float32), done


def recommended_high_pass_hz(common_names) -> float:
    """
    800 Hz cuts low-frequency rumble (traffic, wind, HVAC) out of a saved
    recording without touching most bird calls — but a recording whose
    own detection(s) include a low-frequency caller like an owl needs a
    much lower cutoff, or the "cleanup" removes the bird along with the
    rumble. Checks ALL of a recording's detections, not just the top
    one — a recording can span more than one species, and the owl-safe
    150 Hz is harmless for the OTHER species in the same recording (bird
    calls generally have negligible energy that low anyway), so there's
    no real tradeoff to erring toward the lower cutoff whenever any
    detection warrants it.
    """
    for name in (common_names or []):
        if name in LOW_FREQUENCY_CALLERS:
            return LOW_FREQUENCY_HIGH_PASS_HZ
    return 800.0


class AudioProcessor:
    """
    Handles all server-side audio processing:
      - Mel spectrogram generation (annotated PNG) with HTTP-cache-friendly output
      - Detection clip extraction (short WAV files)
      - Waveform data for browser waveform display
    """

    def generate_spectrogram(
        self,
        wav_path: str,
        output_dir: str,
        recording_id: str,
        detections: Optional[list] = None,
        conf_key: str = "0",          # cache key: stringified threshold × 100
        dpi: int = 120,               # 120 for normal; pass thumb=True below for a real thumbnail
        thumb: bool = False,          # generate a small, fast thumbnail variant instead
        color_palette: str = "vivid", # which named palette (see pick_species_colors) to draw detection boxes in
        box_fill: bool = True,        # False = outline-only boxes, so nothing inside a box is tinted (used for AI Second Opinion)
        time_range: Optional[tuple] = None,  # (start_s, end_s) crop; axis keeps absolute times
        mel_axis: bool = False,       # mel-spaced frequency axis: low calls (owls, doves) get real height
        fig_height: Optional[float] = None,
    ) -> str:
        """
        Generate a mel spectrogram PNG for a WAV recording with detection overlays.

        The file is named  {recording_id}_spectrogram_{conf_key}.png  so different
        confidence thresholds each get their own cached file — the HTTP endpoint
        can always serve from disk. When thumb=True, the file is instead named
        {recording_id}_spectrogram_{conf_key}_thumb.png and rendered at a lower
        DPI and capped width — this was previously a dead, half-wired feature:
        the `dpi` parameter already flowed through to fig.savefig() correctly,
        but no caller ever passed anything but the 120 default, so every
        spectrogram (full detail view AND small grid-view thumbnails) paid the
        same generation cost and file size regardless of how large it would
        actually be displayed.

        Returns the path to the saved PNG.
        """
        if not _LIBROSA_OK or not _MPL_OK:
            raise RuntimeError("librosa / matplotlib not available")

        if thumb:
            dpi = 60
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)
        # Include conf_key in filename so each threshold is cached separately;
        # thumbnails get their own distinct suffix so they're never confused
        # for (or accidentally served as) the full-resolution version.
        # "_thumb2" (not "_thumb") deliberately — this generator just
        # dropped detection overlays for thumbnails entirely, and every
        # thumbnail already on disk under the old "_thumb" name was
        # generated with those overlays baked in. Without a distinct
        # suffix, every existing recording would keep serving its old
        # cluttered cached thumbnail indefinitely (the fast-path check
        # below is "does a file already exist at this exact path", so it
        # would never know to regenerate) instead of getting the cleaner
        # version automatically. Old "_thumb" files are simply orphaned,
        # unused disk space — not deleted, just never served again.
        # A non-default palette changes the actual pixels drawn (the
        # detection box colors), so it needs its own distinct cache
        # filename — otherwise switching palettes in Settings would
        # never invalidate an already-cached PNG (the fast-path check
        # below is "does a file already exist at this exact path", not
        # "was it generated with today's settings"), and the old
        # colors would silently keep being served forever. The default
        # ("vivid") deliberately gets NO suffix, so every spectrogram
        # generated before this feature existed is still considered
        # correctly cached rather than needlessly regenerated.
        out_path = output_dir_path / spectrogram_filename(recording_id, conf_key, thumb, color_palette)

        # ── Load audio ──────────────────────────────────────────────────────
        # Resample to 22050 Hz — sufficient for 0–11 kHz display, 2× faster than 48k
        TARGET_SR = 22050
        t_offset = 0.0
        if time_range:
            t_offset = max(0.0, float(time_range[0]))
            y, sr = _librosa.load(wav_path, sr=TARGET_SR, mono=True, offset=t_offset,
                                  duration=max(0.5, float(time_range[1]) - t_offset))
        else:
            y, sr = _librosa.load(wav_path, sr=TARGET_SR, mono=True)

        # ── Mel spectrogram ─────────────────────────────────────────────────
        n_mels     = 128
        hop_length = 512
        fmax       = min(11025, sr // 2)
        S = _librosa.feature.melspectrogram(
            y=y, sr=sr, n_mels=n_mels,
            fmax=fmax, n_fft=2048, hop_length=hop_length,
        )
        S_dB = _librosa.power_to_db(S, ref=np.max)
        logger.debug(
            "generate_spectrogram %s (conf_key=%s): loaded %d samples @ %dHz (%.2fs), "
            "mel array shape=%s, fig_width will be %.2f in",
            recording_id, conf_key, len(y), sr, len(y) / sr if sr else 0,
            S_dB.shape, min(16, max(6, len(y) / sr * 2.0)) if sr else 0,
        )

        # ── Figure ──────────────────────────────────────────────────────────
        BG = "#0a0f14"
        if thumb:
            # Thumbnails are displayed at a small, fixed grid-cell size, so a
            # long recording doesn't need the same wide aspect ratio the full
            # detail view uses — capping width keeps the file small and
            # consistent regardless of recording length.
            fig_width, fig_height = 4.0, 2.0
        else:
            fig_width = min(16, max(6, len(y) / sr * 2.0))
            fig_height = fig_height or 3.2
        fig = _Figure(figsize=(fig_width, fig_height), facecolor=BG)
        ax  = fig.add_axes([0, 0, 1, 1])
        ax.set_facecolor(BG)

        times = _librosa.frames_to_time(
            np.arange(S_dB.shape[1]), sr=sr, hop_length=hop_length
        ) + t_offset
        freqs = _librosa.mel_frequencies(n_mels=n_mels, fmax=fmax)

        ax.pcolormesh(times, freqs / 1000, S_dB,
                      cmap=_get_cmap(), shading="auto", vmin=-80, vmax=0)

        # Auto-zoom y-axis to highest frequency with significant energy
        freq_energy = S_dB.max(axis=1)
        sig_mask = freq_energy > -60
        if sig_mask.any():
            max_sig_freq = freqs[sig_mask].max() / 1000
            ax.set_ylim(0, min(max(max_sig_freq * 1.2, 4.0), 11.0))
        else:
            ax.set_ylim(0, 11)
        if mel_axis:
            # Same spacing the mel bins already have, so 0.3-1 kHz gets a
            # fair share of the image instead of the bottom few pixels.
            _to_mel = lambda k: 2595.0 * np.log10(1.0 + np.maximum(k, 0) * 1000.0 / 700.0)
            _from_mel = lambda m: (10 ** (np.asarray(m) / 2595.0) - 1.0) * 700.0 / 1000.0
            ax.set_yscale("function", functions=(_to_mel, _from_mel))
            top_k = ax.get_ylim()[1]
            ticks = [k for k in (0.25, 0.5, 1, 2, 3, 4, 6, 8, 10) if k < top_k]
            ax.set_yticks(ticks)
            ax.set_yticklabels([f"{k:g} kHz" for k in ticks])
            # Room for readable axis labels: this image is read by a model,
            # not overlaid by the frontend, so the labels must be inside it.
            ax.set_position([0.055, 0.1, 0.94, 0.88])
        if time_range and len(times):
            ax.set_xlim(times[0], times[-1])

        # ── Detection overlays ──────────────────────────────────────────────
        # Skipped entirely for thumbnails: the frontend already overlays a
        # confidence badge and species photo badge on top of the thumbnail
        # image itself (RecordingsList.jsx's grid view), so the same
        # per-detection colored box + "species name\nconfidence%" text label
        # this draws for the full detail view is duplicate information at
        # thumbnail size — and with several detections in one recording
        # (a common case), the boxes and tiny labels overlap and crowd a
        # 4x2 inch image badly, which is exactly the "cluttered" look this
        # was meant to avoid, not add to.
        if detections and not thumb:
            unique_species = list(dict.fromkeys(
                d.get("common_name", "Unknown") for d in detections
            ))
            species_color = pick_species_colors(unique_species, color_palette)
            ymax = ax.get_ylim()[1]
            for det in detections:
                name  = det.get("common_name", "Unknown")
                c     = species_color[name]
                start = float(det.get("start_time", 0))
                end   = float(det.get("end_time", 3))
                conf  = float(det.get("confidence", 0))
                rect  = _mpatches.Rectangle(
                    (start, 0), end - start, ymax,
                    linewidth=1.5, edgecolor=c, facecolor=(c + "28") if box_fill else "none",
                )
                ax.add_patch(rect)
                ax.text(
                    start + (end - start) / 2, ymax * 0.93,
                    f"{name if mel_axis else name[:12]}\n{conf:.0%}",
                    color=c, fontsize=6, ha="center", va="top", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.12", facecolor=BG,
                              alpha=0.78, edgecolor=c, linewidth=0.7),
                )

            # NOTE: no ax.legend() here by design. Each detection segment
            # already carries its own species name + confidence label
            # directly on the spectrogram (the ax.text() call above), and
            # the frontend's CollapsibleLegend (RecordingDetail.jsx) shows
            # the same species/color mapping above the player — a legend
            # box baked into the image itself duplicated both, while also
            # visually overlapping the rightmost detection segment on
            # longer recordings (it's pinned to the upper-right corner
            # regardless of how many segments are there).

        # ── Axes styling ────────────────────────────────────────────────────
        ax.set_xlabel("Time (s)", color="#9ca3af", fontsize=8)
        ax.yaxis.set_tick_params(colors="#6b7280", labelsize=7)
        ax.xaxis.set_tick_params(colors="#6b7280", labelsize=7)
        ax.tick_params(colors="#6b7280", labelsize=7)
        if mel_axis:
            ax.tick_params(colors="#d1d5db", labelsize=9)
        for spine in ax.spines.values():
            spine.set_edgecolor("#374151")
        fig.subplots_adjust(left=0.045, right=0.998, bottom=0.12, top=0.99)

        # ── Save ────────────────────────────────────────────────────────────
        # Written to a temp path first, then atomically renamed into place.
        # Without this, fig.savefig() writes directly to the final cache
        # path — if two requests for the same recording's spectrogram
        # arrive close together (plausible on mobile: a double-tap, or a
        # page re-render firing a duplicate request) and both pass the
        # "does the cache file already exist" check before either has
        # finished writing, a reader could observe a partially-written,
        # corrupted PNG. os.replace() is atomic on the same filesystem —
        # a reader always sees either the complete old file or the
        # complete new one, never a partial write, regardless of how many
        # concurrent writers there are. Tried directly to reproduce this
        # exact race (concurrent requests on a cold cache, a 60s
        # recording to widen the write-duration window, a thread barrier
        # forcing true simultaneity) and could not catch it in the act —
        # this fix is applied as a correct defensive practice regardless,
        # since it closes the entire category of risk at near-zero cost,
        # not because the race was conclusively proven.
        canvas = _Canvas(fig)
        canvas.draw()
        tmp_path = _atomic_tmp_path(out_path)
        fig.savefig(tmp_path, dpi=dpi, facecolor=BG, edgecolor="none")
        os.replace(tmp_path, str(out_path))

        # Sidecar bounds JSON for frontend spectrogram overlay alignment —
        # same atomic-write treatment for the same reason.
        ax_pos = ax.get_position()
        bounds_path = str(out_path).replace(".png", "_bounds.json")
        bounds_tmp = bounds_path + f".tmp{os.getpid()}"
        with open(bounds_tmp, "w") as f:
            json.dump({
                "left_frac":   ax_pos.x0,
                "right_frac":  ax_pos.x1,
                "bottom_frac": ax_pos.y0,
                "top_frac":    ax_pos.y1,
            }, f)
        os.replace(bounds_tmp, bounds_path)

        logger.info("Spectrogram: %s  %dKB  conf_key=%s",
                    out_path.name, os.path.getsize(str(out_path)) // 1024, conf_key)
        return str(out_path)

    def generate_bat_spectrogram(
        self,
        wav_path: str,
        output_dir: str,
        recording_id: str,
        dpi: int = 120,
    ) -> str:
        """
        Generate a spectrogram for a bat-echolocation recording.

        Deliberately NOT a reuse of generate_spectrogram() above with
        different parameters — that function resamples to 22050 Hz before
        analysis (TARGET_SR), which would alias away virtually all real
        echolocation content, since bat calls run from ~9 kHz to over
        150 kHz (well above what 22050 Hz can represent — Nyquist caps
        representable frequency at half the sample rate, ~11 kHz). This
        function loads the WAV at its true native rate instead (no
        resampling) and uses a plain STFT rather than a mel-scale spectrogram:
        mel weighting is a perceptual scale tuned to human (and by extension
        BirdNET's bird-call) hearing, and has no defensible meaning applied
        to a frequency range bats use but humans and most mammals never
        evolved to perceive — a linear Hz axis is the honest representation
        here.

        Y-axis is fixed at 0–96 kHz: the practical Nyquist ceiling for this
        device's bat-capable hardware path (AudioMoth-class mics sampling
        at 192 kHz minimum — see chirp-device/chirp/bat_detector.py's
        min_sample_rate), and comfortably covers the full range of
        documented bat call frequencies for any recording made at or above
        that rate. If a clip's native rate is lower, the axis is capped at
        that clip's own Nyquist frequency instead, so the plot never
        implies data the recording couldn't have captured.
        """
        if not _LIBROSA_OK or not _MPL_OK:
            raise RuntimeError("librosa / matplotlib not available")

        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)
        out_path = output_dir_path / f"{recording_id}_spectrogram_bat.png"

        # Native rate — no resampling. sr=None tells librosa to keep the
        # file's own sample rate rather than defaulting to 22050.
        y, sr = _librosa.load(wav_path, sr=None, mono=True)

        n_fft      = 1024
        hop_length = 256
        S = _librosa.stft(y, n_fft=n_fft, hop_length=hop_length)
        S_dB = _librosa.amplitude_to_db(np.abs(S), ref=np.max)

        BG = "#0a0f14"
        fig_width = min(16, max(6, len(y) / sr * 2.0))
        fig = _Figure(figsize=(fig_width, 3.2), facecolor=BG)
        ax  = fig.add_axes([0, 0, 1, 1])
        ax.set_facecolor(BG)

        times = _librosa.frames_to_time(
            np.arange(S_dB.shape[1]), sr=sr, hop_length=hop_length
        )
        freqs = _librosa.fft_frequencies(sr=sr, n_fft=n_fft)

        ax.pcolormesh(times, freqs / 1000, S_dB,
                      cmap=_get_cmap(), shading="auto", vmin=-80, vmax=0)

        nyquist_khz = (sr / 2) / 1000
        ax.set_ylim(0, min(96.0, nyquist_khz))

        # Light gridlines at common bat-call reference frequencies (kHz),
        # the ultrasonic equivalent of the time-axis ticks below — gives a
        # visual sense of scale even without species identification.
        for ref_khz in (20, 40, 60, 80):
            if ref_khz < ax.get_ylim()[1]:
                ax.axhline(ref_khz, color="#374151", linewidth=0.5, alpha=0.5, zorder=0)

        ax.set_xlabel("Time (s)", color="#9ca3af", fontsize=8)
        ax.set_ylabel("Frequency (kHz)", color="#9ca3af", fontsize=8)
        ax.yaxis.set_tick_params(colors="#6b7280", labelsize=7)
        ax.xaxis.set_tick_params(colors="#6b7280", labelsize=7)
        for spine in ax.spines.values():
            spine.set_edgecolor("#374151")
        fig.subplots_adjust(left=0.06, right=0.998, bottom=0.12, top=0.99)

        canvas = _Canvas(fig)
        canvas.draw()
        tmp_path = _atomic_tmp_path(out_path)
        fig.savefig(tmp_path, dpi=dpi, facecolor=BG, edgecolor="none")
        os.replace(tmp_path, str(out_path))

        logger.info(
            "Bat spectrogram: %s  %dKB  native_sr=%dHz  ylim=0-%.0fkHz",
            out_path.name, os.path.getsize(str(out_path)) // 1024, sr, min(96.0, nyquist_khz),
        )
        return str(out_path)

    def extract_clip(
        self,
        wav_path: str,
        clips_dir: str,
        detection_id: str,
        start_time: float,
        end_time: float,
        padding: float = 1.0,
        is_bat: bool = False,
    ) -> str:
        """
        Extract a short audio clip centred on a detection, compressed.

        Investigated directly in response to a database-overhead question:
        clips_dir was 129.4 GB across 148,764 files — one uncompressed
        16-bit PCM WAV per detection. Clips are purely for human listening
        (confirmed: nothing in this codebase ever reads clip_path back for
        BirdNET re-analysis), so lossy compression has zero effect on bird
        detection accuracy. MP3 over the more space-efficient Opus for
        universal <audio> playback support across every browser/device
        this app targets.

        Bats are NOT included in that "safe to compress lossily" reasoning
        — caught directly after this shipped MP3-only, by testing a 40kHz
        tone (bat calls typically span 20-60kHz) through the exact ffmpeg
        command below: standard MP3 tops out at 48kHz sample rate, so
        ffmpeg silently resampled a 192kHz source down first, and the
        40kHz content was completely gone on decode (0.0000% of its
        original energy) — not degraded, erased. Bat clips exist
        specifically so the ultrasonic call itself can be reviewed, so
        losing it defeats the clip's entire purpose. is_bat=True instead
        writes losslessly as FLAC (soundfile/libsndfile supports FLAC as
        a write format directly, so bats don't need ffmpeg at all here) —
        verified on the same 40kHz/192kHz test: exact sample rate and
        peak frequency preserved, ~78% smaller than the equivalent WAV.
        Go-forward only either way: this changes what NEW clips get
        written as, not anything already on disk. Existing .wav clips are
        untouched and keep serving exactly as before (see get_clip()'s
        own media_type handling in recordings.py, which checks the
        actual file extension rather than assuming one format).
        """
        clips_dir_path = Path(clips_dir)
        clips_dir_path.mkdir(parents=True, exist_ok=True)

        data, sr = sf.read(wav_path, always_2d=True)
        total_samples = len(data)
        start_sample  = max(0, int((start_time - padding) * sr))
        end_sample    = min(total_samples, int((end_time + padding) * sr))
        segment = data[start_sample:end_sample]

        if is_bat:
            out_path = clips_dir_path / f"{detection_id}.flac"
            tmp_path = _atomic_tmp_path(out_path)
            sf.write(tmp_path, segment, sr, format="FLAC")
            os.replace(tmp_path, str(out_path))
            return str(out_path)

        out_path = clips_dir_path / f"{detection_id}.mp3"
        # soundfile/libsndfile can't write MP3 directly — write the
        # extracted segment to a throwaway temp WAV first, then encode
        # that to MP3 via ffmpeg (already a hard dependency of this app
        # elsewhere, e.g. live_detect.py's session-audio decoding).
        tmp_wav_path = clips_dir_path / f"{detection_id}_tmp.wav"
        sf.write(str(tmp_wav_path), segment, sr, subtype="PCM_16")
        tmp_mp3_path = _atomic_tmp_path(out_path)
        try:
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", str(tmp_wav_path), "-codec:a", "libmp3lame",
                 "-b:a", "96k", tmp_mp3_path],
                capture_output=True, timeout=30,
            )
            if result.returncode != 0 or not os.path.exists(tmp_mp3_path):
                raise RuntimeError(
                    f"ffmpeg clip encode failed (code {result.returncode}): "
                    f"{result.stderr.decode(errors='replace')[-300:]}"
                )
            os.replace(tmp_mp3_path, str(out_path))
        finally:
            tmp_wav_path.unlink(missing_ok=True)
            if os.path.exists(tmp_mp3_path):
                os.unlink(tmp_mp3_path)

        return str(out_path)

    def get_audio_duration(self, wav_path: str) -> float:
        try:
            return sf.info(wav_path).duration
        except Exception:
            return 0.0

    def _detect_call_band(
        self,
        signal: np.ndarray,
        sr: int,
        call_start: Optional[float],
        call_end: Optional[float],
        fallback_low: float,
        fallback_high: float,
    ) -> tuple:
        """
        Derive a bandpass range from the actual spectral content of the call,
        instead of using one fixed band for every species. This is what lets
        a tight, high-pitched call (e.g. a Black-capped Chickadee, mostly
        2.5–4 kHz) get a much narrower, more isolating filter than a broad
        croak (e.g. a Common Raven, with energy from a few hundred Hz up).

        Method: take an STFT over the call window (if known) and find the
        smallest [low, high] band that contains 85% of the in-band energy,
        using the quietest 20% of the clip as a noise floor so background
        hum/hiss frequencies aren't mistaken for "where the call lives".
        Falls back to (fallback_low, fallback_high) if there's no usable
        call window (e.g. enhancing a full multi-species recording) or the
        signal is too short/quiet to get a stable estimate.

        Returns (low_hz, high_hz, used_adaptive: bool).
        """
        if not _SCIPY_OK or call_start is None or call_end is None:
            return fallback_low, fallback_high, False

        try:
            n_fft = 1024
            hop = 256
            freqs, times, Zxx = _spsignal.stft(signal, fs=sr, nperseg=n_fft, noverlap=n_fft - hop)
            mag = np.abs(Zxx)

            call_mask = (times >= call_start) & (times <= call_end)
            if call_mask.sum() < 2:
                return fallback_low, fallback_high, False

            # Noise floor: median spectrum of the quietest 20% of frames overall
            # (covers pre-roll / padding outside the call, which is mostly
            # background — works whether or not it's literally silent).
            frame_energy = mag.sum(axis=0)
            n_quiet = max(2, int(len(frame_energy) * 0.2))
            quiet_idx = np.argsort(frame_energy)[:n_quiet]
            noise_floor = np.median(mag[:, quiet_idx], axis=1) + 1e-8

            call_spec = np.mean(mag[:, call_mask], axis=1)
            snr = call_spec / noise_floor

            # Restrict candidate bins to a sane bird-vocalization range up front
            # (150 Hz–14 kHz) so a stray low-frequency rumble or ultrasonic
            # spike inside the call window can't pull the band somewhere odd.
            band_mask = (freqs >= 150) & (freqs <= 14000)   # 150 Hz keeps owl hoots
            if not band_mask.any():
                return fallback_low, fallback_high, False

            # Per-bin SNR threshold (not a cumulative-energy-share threshold):
            # a share-of-total-energy approach gets diluted badly when
            # broadband background noise is present *during* the call itself
            # (the realistic case for an outdoor recording), since many weak
            # bins each contribute a little and together force a wide band
            # just to reach the target share. Thresholding each bin
            # individually — "is this bin meaningfully louder than its own
            # noise floor" — stays tight around the call's actual harmonics
            # regardless of how much ambient noise is mixed in elsewhere.
            SNR_THRESHOLD = 1.8   # ~5 dB above the noise floor
            passing = band_mask & (snr > SNR_THRESHOLD)
            if not passing.any():
                # Nothing clearly stands out — fall back rather than guess
                return fallback_low, fallback_high, False

            passing_idx = np.where(passing)[0]
            low_bin, high_bin = passing_idx.min(), passing_idx.max()
            low_hz  = max(float(freqs[low_bin]) - 150, 150.0)
            high_hz = min(float(freqs[high_bin]) + 250, sr / 2 - 100)

            if high_hz - low_hz < 400:
                # Too narrow to be a real bandpass — widen symmetrically rather
                # than risk filtering out the call's own harmonics/overtones.
                center = (low_hz + high_hz) / 2
                low_hz, high_hz = max(150.0, center - 400), center + 400

            if high_hz <= low_hz:
                return fallback_low, fallback_high, False

            return low_hz, high_hz, True
        except Exception as e:
            logger.debug("Adaptive band detection failed, using fallback band: %s", e)
            return fallback_low, fallback_high, False

    def _reduce_noise(self, filtered, sr, taper_samples, call_start, call_end, low, high, cache_id):
        """
        Spectral gating noise reduction — lifted verbatim out of
        enhance_audio's own step 3 so it can be skipped cleanly (see
        apply_noise_reduction there) without an awkward inline
        try/except-inside-if. Behavior is unchanged from before this was
        extracted — same steps, same variable names, same logic.

        Returns (reduced_audio, noise_sample_or_None) — the caller only
        uses noise_sample for its own debug logging.
        """
        try:
            noise_sample = None
            if call_start is not None and call_end is not None:
                pre_end = max(0, int(call_start * sr) - taper_samples)
                post_start = min(len(filtered), int(call_end * sr) + taper_samples)
                noise_chunks = []
                if pre_end > sr * 0.1:           # at least 100ms of lead-in
                    noise_chunks.append(filtered[:pre_end])
                if len(filtered) - post_start > sr * 0.1:
                    noise_chunks.append(filtered[post_start:])
                if noise_chunks:
                    noise_sample = np.concatenate(noise_chunks)

            if noise_sample is not None and len(noise_sample) > sr * 0.1:
                reduced = _noisereduce.reduce_noise(
                    y=filtered, sr=sr, y_noise=noise_sample,
                    stationary=True, prop_decrease=0.65,
                )
                # 3b. Quiet-tail protection — restore part of what the gate
                # removed, but ONLY within the call's own detected frequency
                # band AND only within the call's own time window. Some
                # species' calls have a loud onset and a much quieter
                # trailing note (e.g. an Eastern Wood-Pewee's "PEE-a-WEE"
                # followed by a fading "...weeee" — confirmed against real
                # species data: the whole call runs ~1s, with a genuinely
                # quiet tail that's still a real, audible, identifying part
                # of the song, not noise). Spectral gating with a fixed
                # threshold can't distinguish "quiet because it's the tail
                # of a real call" from "quiet because it's background," and
                # measured directly: the tail was being suppressed to ~27%
                # of its original energy while the loud onset was being
                # amplified ~2x by the normalization step below — making an
                # already-quiet, real part of the call disappear even
                # further relative to the now-louder beginning.
                # Confining the restoration to the call's own band (not a
                # blanket reduction in reduction strength) keeps true
                # background noise reduction fully intact everywhere else —
                # verified directly: background-only RMS was identical
                # before and after adding this step.
                try:
                    band_sos = _spsignal.butter(2, [low, high], btype="band", output="sos")
                    removed = filtered - reduced
                    removed_inband = _spsignal.sosfiltfilt(band_sos, removed)

                    fade_samples = min(int(sr * 0.05), len(filtered) // 8)  # 50ms fade
                    call_start_samp = max(0, int(call_start * sr))
                    call_end_samp = min(len(filtered), int(call_end * sr))
                    time_mask = np.zeros(len(filtered), dtype=np.float32)
                    time_mask[call_start_samp:call_end_samp] = 1.0
                    if fade_samples > 0:
                        if call_start_samp > fade_samples:
                            time_mask[call_start_samp - fade_samples:call_start_samp] = \
                                np.linspace(0, 1, fade_samples)
                        if call_end_samp + fade_samples < len(time_mask):
                            time_mask[call_end_samp:call_end_samp + fade_samples] = \
                                np.linspace(1, 0, fade_samples)

                    reduced = reduced + 0.5 * removed_inband * time_mask
                except Exception as e:
                    # Protection step is an enhancement on top of an
                    # already-valid `reduced` signal — if it fails for any
                    # reason, just keep the unprotected result rather than
                    # fail the whole enhancement request over it.
                    logger.debug("Call-tail protection skipped for %s: %s", cache_id, e)
            else:
                reduced = _noisereduce.reduce_noise(
                    y=filtered, sr=sr, stationary=False, prop_decrease=0.65,
                )
            return reduced, noise_sample
        except Exception as e:
            # Fall back to just the bandpass result if noisereduce itself
            # fails on some edge-case input (e.g. all-silence clip) —
            # still better than failing the whole enhancement request.
            logger.warning("noisereduce failed for %s, using bandpass-only: %s", cache_id, e)
            return filtered, None

    def enhance_audio(
        self,
        wav_path: str,
        output_dir: str,
        cache_id: str,
        low_hz: float = 500.0,
        high_hz: float = 10000.0,
        call_start: Optional[float] = None,
        call_end: Optional[float] = None,
        apply_bandpass: bool = True,
        apply_noise_reduction: bool = True,
    ) -> str:
        """
        Produce a "cleaned" version of a WAV recording that better isolates
        bird vocalizations from background noise, for an alternate playback
        option.

        Pipeline (all CPU-only, no GPU/ML model needed):

          1. Edge taper — a short Hann-window fade (15 ms) at the very start
             and end of the signal. filtfilt-style filtering can otherwise
             produce an audible click/ring right at the clip boundary where
             the signal cuts sharply to silence.
          2. Adaptive bandpass — when `call_start`/`call_end` are given (the
             clip-enhancement path always has these; the full-recording path
             doesn't, since one recording can span several different species
             at different pitches), the band is derived from the call's own
             spectral content via `_detect_call_band` rather than using one
             fixed range for every species. A tight high-pitched call gets a
             narrow band; a low croak gets a wide one. Falls back to the
             fixed low_hz–high_hz range otherwise. Uses `sosfiltfilt`
             (second-order sections) rather than transfer-function `filtfilt`
             — numerically more stable for narrow/high-order bands, which
             reduces ringing artifacts versus the b/a form.
          3. Spectral-gating noise reduction (`noisereduce`). When an
             explicit noise-only sample is available (the padding outside
             the call window) it's passed in directly for a more accurate
             noise profile instead of relying on automatic non-stationary
             estimation. `prop_decrease` is set to 0.65 rather than the
             library's default of 1.0 — full-strength reduction is what was
             producing the "musical noise" warble/distortion on quieter
             clips. Lowered further from an initial 0.8 after continued
             reports of audible distortion — spectral gating's musical-noise
             artifact (a warbly, robotic quality) scales with how aggressively
             it suppresses low-SNR bins, so pulling back further trades a
             slightly less "clean" noise floor for markedly less artifact.
          4. Soft limiting instead of hard peak-normalization — anything
             above 90% amplitude is gently compressed (tanh) rather than the
             whole signal being linearly rescaled to a fixed peak, which
             avoids audibly squashing dynamics on a clip that has one loud
             transient.

        Downmixes to mono first (stereo doesn't help isolate a single call,
        and halves the processing cost). Output is 16-bit PCM WAV.

        Cached on disk as {output_dir}/{cache_id}_enhanced.wav — callers
        should check for that file's existence before calling this, the
        same pattern used by generate_spectrogram/extract_clip.

        apply_bandpass / apply_noise_reduction: requested directly, as two
        independently-toggleable options rather than one bundled
        "Enhanced" — a person may want just the rumble cutoff without the
        spectral-gating noise reduction, or vice versa. Both default True
        (existing callers that don't pass either get the original,
        unchanged bundled behavior). Setting apply_bandpass=False skips
        step 2 entirely (mono passes straight through as `filtered`);
        setting apply_noise_reduction=False skips step 3 (this
        function's `filtered` becomes `reduced` unchanged, keeping steps
        1 and 4 — edge taper and soft limiting — either way, since
        neither is specific to noise reduction or the bandpass).
        """
        if not (_SCIPY_OK and _NOISEREDUCE_OK):
            raise RuntimeError("Audio enhancement requires scipy and noisereduce to be installed")

        out_dir_path = Path(output_dir)
        out_dir_path.mkdir(parents=True, exist_ok=True)
        out_path = out_dir_path / f"{cache_id}_enhanced.wav"

        data, sr = sf.read(wav_path, always_2d=True)
        # Downmix to mono
        mono = np.mean(data, axis=1).astype(np.float32)

        if len(mono) < 64:
            # Too short for a meaningful filtfilt/STFT pass — just copy through
            tmp_path = _atomic_tmp_path(out_path)
            sf.write(tmp_path, mono, sr, subtype="PCM_16")
            os.replace(tmp_path, str(out_path))
            return str(out_path)

        # 1. Edge taper — avoids a filtfilt click/ring right at the clip boundary
        taper_samples = min(int(sr * 0.015), len(mono) // 4)
        if taper_samples > 4:
            window = np.hanning(taper_samples * 2)
            mono = mono.copy()
            mono[:taper_samples] *= window[:taper_samples]
            mono[-taper_samples:] *= window[taper_samples:]

        # 2. High-pass ONLY (species-aware cutoff) — a plain, single-pass
        #    2nd-order Butterworth high-pass, deliberately matching the same
        #    filter LiveDetect.jsx's real-time "Cut low rumble" chain uses
        #    (a single BiquadFilterNode, type 'highpass' — causal, single
        #    pass, no zero-phase doubling).
        #
        #    Reported directly: the previous design here was a true
        #    BANDPASS — it cut everything above the call's own adaptively-
        #    detected frequency range too, not just rumble below it — applied
        #    via sosfiltfilt at an EFFECTIVE 6th-to-8th order (filtfilt runs
        #    forward+backward, doubling the nominal order 3-4 passed to
        #    butter()). That's a steep, zero-phase filter that rings audibly
        #    right at the band edges, and it was removing real high-frequency
        #    call content "Rumble removed" was never supposed to touch in the
        #    first place — exactly the "adds a lot of noise" behavior
        #    reported, and exactly what Live Detect's own, much gentler
        #    single-biquad rumble filter never has. Fixed by switching the
        #    AUDIBLE filter to a plain high-pass, single pass (sosfilt, not
        #    sosfiltfilt), true order 2, at the fixed species-aware low_hz
        #    cutoff (not the adaptive band) — nothing above the cutoff is
        #    touched at all now, and the cutoff itself is predictable rather
        #    than varying call-to-call, matching Live Detect's own fixed-
        #    cutoff behavior.
        #
        #    _detect_call_band's adaptive-band detection is still computed
        #    below and still used — but now ONLY to tell step 3's noise-
        #    reduction tail-protection which frequency range is "the call's
        #    own band" for confining its restoration, a different, narrower
        #    purpose than the audible high-pass above. That's a real,
        #    separate use of the same detector, not dead code.
        if apply_bandpass:
            band_low, band_high, adaptive = self._detect_call_band(
                mono, sr, call_start, call_end, low_hz, high_hz
            )
            nyq = sr / 2.0
            low = max(band_low / nyq, 0.001)
            high = min(band_high / nyq, 0.99)
            filtered = apply_rumble_highpass(mono, sr, low_hz)
        else:
            # Skipped entirely — same as before this fix: avoids both the
            # filter cost AND the _detect_call_band STFT-analysis cost for
            # a step that wasn't asked for. low/high still need real
            # values here even with bandpass skipped — step 3's quiet-tail
            # protection (below) reuses them to confine its restoration to
            # "the call's own band," and that logic runs whenever noise
            # reduction is on, independent of apply_bandpass. Near-full-
            # spectrum bounds make that restoration effectively
            # unrestricted by band, which is the correct behavior when
            # there's no band to confine it to in the first place —
            # unchanged from before this fix.
            band_low, band_high, adaptive = 0.0, sr / 2.0, False
            low, high = 0.001, 0.99
            filtered = mono
            low, high = 0.001, 0.99

        # 3. Spectral gating noise reduction — explicit noise sample when we
        #    know where the call is (padding outside the call window is the
        #    best available "background only" reference); otherwise let
        #    noisereduce's non-stationary mode estimate it automatically.
        #    Extracted into its own method (below) so it can be skipped
        #    cleanly via apply_noise_reduction without an awkward inline
        #    try/except-inside-if indentation mess.
        notched = []
        if apply_noise_reduction:
            # 3a. Steady insect/beep tones: measured, then notched out unless
            #     they sit inside the call's own band (clip path).
            try:
                tones = [p["freq_hz"] for p in detect_periodic_tonal_pulses(wav_path)]
                keep = (band_low, band_high) if adaptive else None
                if keep is None and call_start is not None and call_end is not None:
                    kl, kh, ok = self._detect_call_band(filtered, sr, call_start, call_end, 0.0, 0.0)
                    keep = (kl, kh) if ok else None
                filtered, notched = notch_steady_tones(filtered, sr, tones, keep_band=keep)
            except Exception as e:
                logger.debug("Steady-tone notch skipped for %s: %s", cache_id, e)
            reduced, noise_sample = self._reduce_noise(
                filtered, sr, taper_samples, call_start, call_end, low, high, cache_id
            )
        else:
            reduced, noise_sample = filtered, None

        # 4. Soft limiting + level normalization — see soft_limit_and_normalize()
        #    above (also reused by ai_enhance.py's neural-denoising path).
        #    boost=apply_noise_reduction: only boost the level back up when
        #    noise reduction actually ran to justify it — plain rumble
        #    removal (apply_noise_reduction=False) skips the boost so it
        #    doesn't amplify whatever ambient noise the filter didn't
        #    touch, matching Live Detect's own filter-only behavior.
        reduced = soft_limit_and_normalize(reduced, boost=apply_noise_reduction)

        had_noise_sample = noise_sample is not None
        out_peak = float(np.max(np.abs(reduced))) if len(reduced) else 0.0
        out_rms = float(np.sqrt(np.mean(reduced.astype(np.float64) ** 2))) if len(reduced) else 0.0
        out_has_nan = bool(np.any(np.isnan(reduced)))
        out_has_inf = bool(np.any(np.isinf(reduced)))
        logger.debug(
            "enhance_audio %s: band=%.0f-%.0fHz adaptive=%s noise_sample=%s notched=%s | "
            "in_samples=%d in_sr=%d in_peak=%.4f | "
            "out_samples=%d out_peak=%.4f out_rms=%.4f out_nan=%s out_inf=%s",
            cache_id, band_low, band_high, adaptive, had_noise_sample, notched,
            len(mono), sr, float(np.max(np.abs(mono))) if len(mono) else 0.0,
            len(reduced), out_peak, out_rms, out_has_nan, out_has_inf,
        )
        if out_has_nan or out_has_inf:
            # A degenerate output (NaN/Inf) would render as visually corrupted
            # — flagged separately at WARNING level (not just DEBUG, which may
            # not be enabled in production) since this is exactly the kind of
            # thing that would explain a corrupted-looking spectrogram for a
            # specific real recording while a clean synthetic test recording
            # processes correctly through the identical code path.
            logger.warning(
                "enhance_audio %s produced NaN/Inf in output (nan=%s inf=%s) — "
                "replacing with silence rather than writing/caching a corrupted "
                "file that would render incorrectly on every future request",
                cache_id, out_has_nan, out_has_inf,
            )
            reduced = np.nan_to_num(reduced, nan=0.0, posinf=0.0, neginf=0.0)

        tmp_path = _atomic_tmp_path(out_path)
        sf.write(tmp_path, reduced.astype(np.float32), sr, subtype="PCM_16")
        os.replace(tmp_path, str(out_path))
        return str(out_path)

    def get_waveform_data(self, wav_path: str, num_points: int = 2000) -> list:
        """Return downsampled waveform as [[min, max], …] for browser display."""
        try:
            y, _ = sf.read(wav_path, dtype="float32", always_2d=False)
            if y.ndim > 1:
                y = y.mean(axis=1)
            chunk = max(1, len(y) // num_points)
            return [
                [float(np.min(y[i:i+chunk])), float(np.max(y[i:i+chunk]))]
                for i in range(0, len(y), chunk)
            ]
        except Exception as e:
            logger.debug("Waveform error: %s", e)
            return []

    def downshift_bat_clip(
        self,
        wav_path: str,
        output_dir: str,
        cache_id: str,
        expansion_factor: int = 10,
    ) -> str:
        """
        "Enhance" a bat-activity clip by downshifting it into human hearing
        range — this is a fundamentally different operation from
        enhance_audio() above (which does noise reduction for bird calls).
        Bat echolocation runs ~15-120kHz; raw playback at that native sample
        rate is silent or barely-perceptible to humans, so there's nothing
        to "clean up" — the original signal itself needs to be shifted down.

        Technique: time expansion. Writing the same high-rate samples into a
        WAV file tagged with a lower nominal sample rate (sample_rate /
        expansion_factor) divides every frequency in the signal by that same
        factor, with no resampling/DSP needed — exactly what dedicated bat
        detector hardware does for human playback. A 10x expansion turns a
        ~40kHz call into a clearly audible ~4kHz tone, and slows the
        playback duration by the same factor (a 5ms pulse becomes 50ms,
        which also makes the characteristic FM sweep easier to actually
        hear rather than perceiving it as a single instantaneous click).

        Cached on disk as {output_dir}/{cache_id}_enhanced.wav, same
        existence-check-before-calling convention as enhance_audio().
        """
        out_dir_path = Path(output_dir)
        out_dir_path.mkdir(parents=True, exist_ok=True)
        out_path = out_dir_path / f"{cache_id}_enhanced.wav"

        data, sr = sf.read(wav_path, always_2d=False)
        new_sr = max(1, int(sr / expansion_factor))
        tmp_path = _atomic_tmp_path(out_path)
        sf.write(tmp_path, data, new_sr, subtype="PCM_16")
        os.replace(tmp_path, str(out_path))
        return str(out_path)

    def remove_bat_wobble(
        self,
        wav_path: str,
        output_dir: str,
        cache_id: str,
        band_hz: tuple = (15000, 40000),
        attenuation_db: float = 25.0,
    ) -> str:
        """
        Experimental: attenuate the persistent wobbling-tone interference
        documented in the AudioMoth/cooling-fan investigation — a
        continuous ridge (measured on real hardware wobbling roughly
        22.5-31kHz, ~28.8Hz modulation rate) that sits inside the same
        band as genuine bat echolocation calls, unlike a fixed-frequency
        hum a simple static notch filter could target.

        Technique: per-frame adaptive notch via STFT. For each time frame,
        find the dominant frequency bin within band_hz (the same
        "track the ridge, don't assume a fixed frequency" approach used to
        analyze it in the first place) and attenuate a narrow window
        around just that bin by attenuation_db, leaving every other
        frequency — including the actual bat calls, which are transient
        broadband spikes rather than the continuous ridge — untouched.
        Reconstructed via inverse STFT (scipy.signal.istft).

        This is a blunt instrument, not a guarantee: if the ridge and a
        genuine call's instantaneous frequency coincide in the same
        frame, attenuating the ridge will attenuate that slice of the
        call too. Tested against a synthetic signal (measured wobble tone
        + a synthetic FM-sweep "call" overlapping it in time): with the
        parameters below, the tracked interference peak is reduced
        roughly 24dB, and a call overlapping the tone in time retains
        roughly 70% of its RMS energy — a real, measurable cost, not
        nothing.

        Also tested against a real recorded bat clip with the actual
        interference ridge present (not synthetic): reduction there was
        only ~11dB, notably less than the clean synthetic test — real
        audio has background noise, harmonics, and per-frame jitter a
        clean synthetic tone doesn't, which likely pulls the per-frame
        peak tracker off the true ridge more often than it does on the
        idealized test signal. The five real bat pulses in that same
        clip retained 67-81% of their energy, consistent with (if
        anything slightly better than) the synthetic test's ~70%. Report
        the real-world number, not just the synthetic one, when
        describing what this actually does — the synthetic test
        validates the mechanism works at all; the real clip is closer to
        what an actual user will experience.

        Off by default and explicitly labeled experimental for exactly
        this reason — it trades a known, measured interference source
        for that real risk to overlapping call content, and that trade
        should be an explicit choice, not a silent default.

        Window size matters more than it might look: an earlier version
        of this method used a 2048-sample STFT window (10.7ms at
        192kHz) — reasonable for typical bat-call analysis, but far too
        long relative to the ~34.7ms period (28.8Hz) of the wobble this
        targets. Each 2048-sample frame covers ~31% of a full wobble
        cycle, meaning the tone's instantaneous frequency itself sweeps
        substantially DURING a single analysis window, smearing its
        energy across dozens of bins rather than concentrating it near
        one tracked peak — confirmed directly: a narrow ±2-bin notch at
        that window size measured under 5dB of real attenuation against
        a 25dB target, not the 25dB implied by the attenuation_db
        parameter. A 512-sample window (2.7ms, ~7.7% of the wobble
        period) keeps the tone quasi-stationary within each frame, and
        measured close to the target attenuation in the same test.

        Cached on disk as {output_dir}/{cache_id}_dewobbled.wav, same
        existence-check-before-calling convention as the other cached
        derivatives in this class.
        """
        if not _SCIPY_OK:
            raise RuntimeError("Wobble removal requires scipy to be installed")

        out_dir_path = Path(output_dir)
        out_dir_path.mkdir(parents=True, exist_ok=True)
        out_path = out_dir_path / f"{cache_id}_dewobbled.wav"

        data, sr = sf.read(wav_path, always_2d=False)
        if data.ndim > 1:
            data = data[:, 0]
        data = data.astype(np.float64)

        # 512/128 (75% overlap) — see docstring for why window size is
        # tuned to the wobble's own timescale rather than a generic
        # bat-analysis default. Swept against several window/hop/notch
        # combinations during testing; this combination sat at the
        # attenuation/call-retention plateau rather than a sharp optimum,
        # so it isn't unusually fragile to the exact real wobble rate
        # differing slightly device to device.
        nperseg = 512
        noverlap = nperseg - 128
        f, t, Zxx = _spsignal.stft(data, fs=sr, nperseg=nperseg, noverlap=noverlap)

        band_mask = (f >= band_hz[0]) & (f <= band_hz[1])
        band_idx = np.where(band_mask)[0]
        if len(band_idx) == 0:
            # Band doesn't exist at this sample rate (e.g. a low-rate
            # recording well below band_hz) — nothing to do, pass through.
            sf_out = data
        else:
            mag = np.abs(Zxx)
            attenuation = 10 ** (-attenuation_db / 20.0)
            # Notch width: +/- 2 bins around the tracked ridge frequency
            # per frame. At this window size that's ~750Hz total width,
            # which the same test confirmed comfortably covers the
            # tone's real per-frame spread without needing to widen
            # further (widening to +/-3 bins measured under 1dB of
            # additional attenuation benefit for a real cost in call
            # content, not worth the tradeoff).
            notch_half_width = 2
            for frame_i in range(Zxx.shape[1]):
                col_mag = mag[band_idx, frame_i]
                if col_mag.size == 0:
                    continue
                peak_local = np.argmax(col_mag)
                peak_global = band_idx[peak_local]
                lo = max(0, peak_global - notch_half_width)
                hi = min(len(f), peak_global + notch_half_width + 1)
                Zxx[lo:hi, frame_i] *= attenuation

            _, sf_out = _spsignal.istft(Zxx, fs=sr, nperseg=nperseg, noverlap=noverlap)
            # istft can return a slightly different length than the input
            # due to frame boundary effects — trim/pad to match exactly so
            # duration metadata computed elsewhere from this file stays
            # correct.
            if len(sf_out) > len(data):
                sf_out = sf_out[:len(data)]
            elif len(sf_out) < len(data):
                sf_out = np.pad(sf_out, (0, len(data) - len(sf_out)))

        tmp_path = _atomic_tmp_path(out_path)
        sf.write(tmp_path, sf_out.astype(np.float32), sr, subtype="PCM_16")
        os.replace(tmp_path, str(out_path))
        return str(out_path)
