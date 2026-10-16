"""
Server BirdNET pass: the one place the server runs BirdNET (device uploads,
manual uploads, Re-analyze, Live Detect), so every path scores the same way.

Inference runs on BirdNET's TFLite model directly rather than through
birdnetlib's Recording loop: windows are scored in batches (one invoke per
BATCH windows instead of one per window, with a resize and tensor
allocation each time), interpreters come from a small pool so two
recordings can be scored at once, and the full score matrix stays
available for near-miss logging. Chunking, the sigmoid and its
sensitivity mapping match birdnetlib 0.18 exactly
(tests/test_birdnet_pass.py compares the two).

Owls get two corrections, both measured on a HaikuBox Barred Owl clip that
came back with no detections:

1. Location filter. BirdNET's location model is built from eBird checklist
   frequency, which is tiny for nocturnal birds: Barred Owl in eastern
   Massachusetts never passes 0.03 in any week (Great Horned 0.006), so the
   filter dropped every owl before its score was looked at. Night callers
   pass when their best week of the year reaches OWL_LOCATION_MIN (owls)
   or NIGHT_LOCATION_MIN.

2. Masking. An insect chorus (2-5 kHz) and low hum bury faint hoots:
   full-band BirdNET scored the Barred Owl 0.05-0.2 and called the katydids
   Eastern Screech-Owl at 0.37. Owls (except Barn Owl, whose screech is
   broadband) are scored on a 200-2000 Hz copy (Barred Owl 0.44), kept only
   where the audio holds a hoot at a pitch that species uses, and only the
   best owl per window. A strong full-band owl that the band-limited copy
   agrees with is kept without the hoot check.

The band-limited copy is scored only for windows that could keep an owl:
windows with a hoot, windows where the full band scores an owl at
STRONG_OWL_CONF or more, and windows holding an earlier owl detection. Any
other window can't produce an owl under the rules above, so skipping it
changes no result; daytime songbird recordings usually need no band pass.
"""
import json
import logging
import os
import queue
import re
import threading
import time
from typing import Optional

import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)

# Night callers score lower than day birds (faint, far, low SNR), so they
# are kept down to this floor; everything else needs the min_conf setting.
NIGHT_SPECIES_MIN_CONF = 0.10
NIGHT_CALLER_RE = re.compile(
    r"\b(Owl|Whip-poor-will|Nighthawk|Chuck-will's-widow|Poorwill|Woodcock|"
    r"Night-Heron|Rail|Sora|Bittern)\b")

LOCATION_THRESHOLD = 0.03      # birdnetlib's default
# Best week of the year, night callers only. Owls are the least reported, so
# they get the lower bar (Long-eared Owl in Massachusetts peaks at 0.0018);
# 0.005 keeps vagrants like Eurasian Woodcock (0.002) out.
OWL_LOCATION_MIN = 0.0015
NIGHT_LOCATION_MIN = 0.005
LOW_BAND_HZ = (200.0, 2000.0)

# Owl hoot fundamentals (Hz), generous. Owls not listed use GENERIC_OWL_PITCH.
OWL_PITCH_HZ = {
    "Great Horned Owl": (150, 500),
    "Great Gray Owl": (120, 400),
    "Long-eared Owl": (250, 550),
    "Short-eared Owl": (200, 600),
    "Snowy Owl": (200, 700),
    "Barred Owl": (300, 1000),
    "Spotted Owl": (300, 1000),
    "Flammulated Owl": (300, 650),
    "Eastern Screech-Owl": (450, 1400),
    "Western Screech-Owl": (450, 1400),
    "Whiskered Screech-Owl": (450, 1400),
    "Boreal Owl": (500, 1100),
    "Northern Saw-whet Owl": (800, 1400),
    "Northern Pygmy-Owl": (800, 1400),
}
GENERIC_OWL_PITCH = (150, 1500)
_OWL_RE = re.compile(r"\bOwl\b")

# Owl rules, tuned on 32 labeled owl clips plus 17 owl-free night clips,
# each owl clip also mixed with katydid and cricket choruses (see
# scripts/owl-eval/README.md). Before tuning: 86 of 96 owl clips found,
# 80 wrong owls reported alongside, owls on 7 of 18 owl-free clips.
# After: 81 found, 8 wrong owls, 1 owl-free clip.
#
# Full-band owl hit this strong, with the band-limited copy at least half of
# it, stands without the tonal check (screams and barks aren't tonal).
# 0.45 since 0.5.12.m (see HOOT_FULL_MIN).
STRONG_OWL_CONF = 0.45
# Owls (not Barn Owl) need this score, whatever the general minimum is (a
# per-species threshold overrides it). At 0.10, crickets, a pigeon and an
# engine scored as owls; 0.25 was best on the set, 0.20 keeps fainter owls.
OWL_MIN_CONF = 0.20
# One recording rarely holds two owl species, but BirdNET often scores a
# second owl in a few windows of a one-owl recording. A second (third...)
# owl species is kept when it reaches SECOND_OWL_RATIO of the top owl's
# score (1.0: only a tie) or SECOND_OWL_MIN outright.
SECOND_OWL_RATIO = 1.0
SECOND_OWL_MIN = 0.7
# A hooted owl found on the band-limited copy also needs at least this
# full-band score for that owl in the same window. On Natick's daytime
# recordings the band-limited copy scored pigeon coos, engines and distant
# voices as Great Horned or Long-eared Owl at 0.35-0.62 while the full band
# said 0.02-0.34. Tuned with the clip set plus 16 field Barred Owl
# recordings and 231 midday field recordings (scripts/owl-eval/README.md):
# false owls on the midday set 20 -> 1, clip set 81 hits / 7 wrong / 0
# false alarms (was 81 / 8 / 1), field Barred Owls 16 of 16 either way.
HOOT_FULL_MIN = 0.30
MIN_HOOT_S = 0.2               # tonal evidence needed inside a 3 s window
# A tonal event longer than this is a drone (engine, hum, fan), not a hoot:
# Great Horned and Barred Owl notes last under 1.5 s, screech-owl trills and
# whinnies up to about 3 s. An engine at 180 Hz scored as Great Horned Owl
# 0.14-0.20 on a daytime Tufted Titmouse recording.
MAX_HOOT_S = 4.0

# Re-analysis of compressed (Opus) or AI-Enhanced audio: a detection the
# earlier pass found on the original WAV keeps its earlier score when the new
# pass scores the same species and window within this much of it. Opus moves
# BirdNET scores by up to ~0.15, enough to push calls near the threshold (or
# under the 0.15 display floor) out of view.
PRIOR_TOLERANCE = 0.15

# Near misses: night callers that scored at least this much in some window
# but weren't kept. Stored per recording to set per-species thresholds.
NEAR_MISS_FLOOR = 0.03

SAMPLE_RATE = 48000
CHUNK_S = 3.0
MIN_CHUNK_S = 1.5              # birdnetlib drops a last chunk shorter than this

# Inference sizing. BATCH windows per invoke; WORKERS interpreters (each
# scores one recording at a time); THREADS per interpreter. Measured on a
# 2-core container: batch 16 with 2 threads 35 ms/window vs 48 ms for
# birdnetlib's one-window, one-thread loop.
_CPU = os.cpu_count() or 2
BATCH = int(os.environ.get("CHIRP_BIRDNET_BATCH", "16"))
THREADS = int(os.environ.get("CHIRP_BIRDNET_THREADS", str(max(1, min(4, _CPU)))))
WORKERS = int(os.environ.get("CHIRP_BIRDNET_WORKERS", str(max(1, min(2, _CPU // THREADS)))))

_pool: Optional[queue.Queue] = None
_pool_lock = threading.Lock()
_labels: list = []
_meta_lock = threading.Lock()  # SpeciesList holds one meta-model interpreter
_species_list = None
_day_cache: dict = {}
_night_cache: dict = {}


def _interpreter_class():
    try:
        import tflite_runtime.interpreter as tflite
        return tflite.Interpreter
    except Exception:
        pass
    try:
        from ai_edge_litert.interpreter import Interpreter
        return Interpreter
    except Exception:
        pass
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from tensorflow import lite as tflite
    return tflite.Interpreter


class _Model:
    """One interpreter, resized only when the batch size changes."""

    def __init__(self, cls, path):
        self.it = cls(model_path=path, num_threads=THREADS)
        self.it.allocate_tensors()
        self.inp = self.it.get_input_details()[0]["index"]
        self.out = self.it.get_output_details()[0]["index"]
        self.n = 1

    def run(self, x: np.ndarray) -> np.ndarray:
        if x.shape[0] != self.n:
            self.it.resize_tensor_input(self.inp, [x.shape[0], x.shape[1]])
            self.it.allocate_tensors()
            self.n = x.shape[0]
        self.it.set_tensor(self.inp, x)
        self.it.invoke()
        return np.array(self.it.get_tensor(self.out))


def _get_pool() -> queue.Queue:
    global _pool, _labels
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                from birdnetlib.analyzer import MODEL_PATH, LABEL_PATH
                with open(LABEL_PATH) as f:
                    _labels = [ln.rstrip("\n") for ln in f]
                cls = _interpreter_class()
                q: queue.Queue = queue.Queue()
                for _ in range(max(1, WORKERS)):
                    q.put(_Model(cls, MODEL_PATH))
                logger.info("Server BirdNET: %d interpreter(s), %d thread(s) each, batch %d",
                            max(1, WORKERS), THREADS, BATCH)
                _pool = q
    return _pool


def labels() -> list:
    _get_pool()
    return _labels


def warm_up() -> None:
    """Load the model (and labels) ahead of the first analysis."""
    _get_pool()


def logits(chunks: np.ndarray) -> np.ndarray:
    """Raw BirdNET outputs for chunks (N, 144000) float32, N x labels."""
    pool = _get_pool()
    if len(chunks) == 0:
        return np.zeros((0, len(_labels)), dtype=np.float32)
    m = pool.get()
    try:
        parts = [m.run(np.ascontiguousarray(chunks[i:i + BATCH], dtype=np.float32))
                 for i in range(0, len(chunks), BATCH)]
    finally:
        pool.put(m)
    return np.concatenate(parts, axis=0)


def to_confidence(raw: np.ndarray, sensitivity: float) -> np.ndarray:
    """birdnetlib's sigmoid: Recording maps the user's sensitivity (higher =
    more detections) to the sigmoid slope, clamped to 0.5-1.5."""
    slope = max(0.5, min(1.0 - (float(sensitivity) - 1.0), 1.5))
    return 1.0 / (1.0 + np.exp(-slope * np.clip(raw, -15, 15)))


def split_chunks(y: np.ndarray, overlap: float) -> tuple:
    """birdnetlib's Recording.process_audio_data: 3 s windows every
    (3 - overlap) s, a short last window zero-padded, one under 1.5 s
    dropped. Returns (chunks, start_times) with start times accumulated the
    same way birdnetlib does, so they compare equal to its output."""
    n = int(CHUNK_S * SAMPLE_RATE)
    step = int((CHUNK_S - overlap) * SAMPLE_RATE)
    out, starts = [], []
    start = 0.0
    for i in range(0, len(y), max(1, step)):
        seg = y[i:i + n]
        if len(seg) < int(MIN_CHUNK_S * SAMPLE_RATE):
            break
        if len(seg) < n:
            seg = np.concatenate([seg, np.zeros(n - len(seg), dtype=y.dtype)])
        out.append(seg)
        starts.append(start)
        start += CHUNK_S - overlap
    if not out:
        return np.zeros((0, n), dtype=np.float32), []
    return np.stack(out).astype(np.float32), starts


def is_low_owl(common_name: str) -> bool:
    return bool(_OWL_RE.search(common_name or "")) and common_name != "Barn Owl"


# How night callers are thresholded (AppSettings.night_threshold_mode):
#   "night"        their own floors: OWL_MIN_CONF for owls, NIGHT_SPECIES_MIN_CONF
#                  (or min_conf, if lower) for the rest
#   "global"       min_conf, like every other species
#   "per_species"  night_threshold_species {common name: True (night floor) /
#                  False (min_conf)}; species not listed use the night floor
# A per-species score (birdnet_species_thresholds) overrides all three.
NIGHT_MODES = ("night", "global", "per_species")


def uses_night_floor(name: str, mode: str = "night", per_species: Optional[dict] = None) -> bool:
    """Whether this species gets the night-caller floor instead of min_conf."""
    if not NIGHT_CALLER_RE.search(name or ""):
        return False
    if mode == "global":
        return False
    if mode == "per_species":
        return bool((per_species or {}).get(name, True))
    return True


def species_required(name: str, min_conf: float, overrides: Optional[dict] = None,
                     mode: str = "night", per_species: Optional[dict] = None) -> float:
    """Score a detection of this species needs to be kept."""
    if overrides and name in overrides:
        return float(overrides[name])
    if uses_night_floor(name, mode, per_species):
        return OWL_MIN_CONF if is_low_owl(name) else min(float(min_conf), NIGHT_SPECIES_MIN_CONF)
    return float(min_conf)


def night_rules(app_s) -> dict:
    """run_birdnet / species_required keyword arguments from AppSettings."""
    mode = (getattr(app_s, "night_threshold_mode", None) or "night") if app_s else "night"
    if mode not in NIGHT_MODES:
        mode = "night"
    raw = (getattr(app_s, "night_threshold_species", None) or {}) if app_s else {}
    return {"mode": mode, "per_species": {str(k): bool(v) for k, v in dict(raw).items()}}


def night_species_for(lat: Optional[float], lon: Optional[float]) -> list:
    """Night callers BirdNET can report at lat/lon (any week), common names."""
    if lat is None or lon is None:
        return []
    try:
        data = _location_lists((round(float(lat), 2), round(float(lon), 2)))
    except Exception as e:
        logger.debug("Night species list unavailable: %s", e)
        return []
    return sorted({_split_label(lbl)[1] for lbl in data.get("night", [])})


def _week_48(when) -> int:
    import calendar
    import math
    doy = when.timetuple().tm_yday
    days = 366 if calendar.isleap(when.year) else 365
    return max(1, min(48, math.ceil(doy / days * 48)))


def _cache_path(key: tuple) -> Optional[str]:
    try:
        from ..config import settings
        base = settings.data_dir
    except Exception:
        base = os.environ.get("CHIRP_DATA_DIR") or None
    if not base:
        return None
    d = os.path.join(base, "cache", "birdnet_location")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return None
    return os.path.join(d, f"{key[0]:.2f}_{key[1]:.2f}.json")


def _location_lists(key: tuple) -> dict:
    """{"weeks": {week: [labels over LOCATION_THRESHOLD]}, "night": [labels]}
    for a rounded lat/lon: 48 meta-model runs, cached in memory and on disk
    (the file carries its thresholds, so changing them rebuilds it)."""
    global _species_list
    if key in _night_cache:
        return _night_cache[key]
    stamp = [LOCATION_THRESHOLD, OWL_LOCATION_MIN, NIGHT_LOCATION_MIN, NIGHT_CALLER_RE.pattern]
    path = _cache_path(key)
    if path and os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
            if data.get("stamp") == stamp:
                _night_cache[key] = data
                return data
        except Exception as e:
            logger.warning("Location list cache %s unreadable: %s", path, e)
    with _meta_lock:
        if key in _night_cache:
            return _night_cache[key]
        if _species_list is None:
            from birdnetlib.species import SpeciesList
            _species_list = SpeciesList()
        weeks, best = {}, {}
        for wk in range(1, 49):
            rows = _species_list.return_list(lat=key[0], lon=key[1], week_48=wk, threshold=0.0)
            weeks[str(wk)] = sorted(f"{s['scientific_name']}_{s['common_name']}"
                                    for s in rows if float(s["threshold"]) >= LOCATION_THRESHOLD)
            for s in rows:
                if NIGHT_CALLER_RE.search(s["common_name"]):
                    lbl = f"{s['scientific_name']}_{s['common_name']}"
                    best[lbl] = max(best.get(lbl, 0.0), float(s["threshold"]))
        night = sorted(lbl for lbl, v in best.items()
                       if v >= (OWL_LOCATION_MIN if _OWL_RE.search(lbl) else NIGHT_LOCATION_MIN))
        data = {"stamp": stamp, "weeks": weeks, "night": night}
        _night_cache[key] = data
    if path:
        try:
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f)
            os.replace(tmp, path)
        except OSError as e:
            logger.warning("Could not write location list cache %s: %s", path, e)
    return data


def allowed_labels(lat: float, lon: float, when) -> set:
    """Labels ('Scientific_Common') expected at lat/lon in when's week, plus
    night callers that reach OWL_LOCATION_MIN / NIGHT_LOCATION_MIN in any
    week of the year."""
    key = (round(float(lat), 2), round(float(lon), 2))
    week = _week_48(when)
    ck = key + (week,)
    if ck not in _day_cache:
        data = _location_lists(key)
        _day_cache[ck] = set(data["weeks"][str(week)]) | set(data["night"])
    return _day_cache[ck]


# Hoot detector settings (see scripts/owl-eval/README.md). min_edge_db: how
# far a hoot's level at its pitch must stand above the quieter of the
# stretches just before and after it. Hoots start and stop (median 15 dB,
# 90% over 4.3 dB on the clip set); a passing engine's harmonics measured
# 4.7 dB at most, and scored as Great Horned Owl without this.
HOOT = {
    "min_excess_db": 8.0,      # above that bin's median over the recording
    "min_contrast_db": 5.0,    # above the bins either side (tonal, not broadband)
    "min_dur_s": MIN_HOOT_S,
    "max_dur_s": MAX_HOOT_S,
    "max_jump_hz": 80.0,       # pitch change allowed between frames of one event
    "min_edge_db": 5.0,
    "edge_s": (0.05, 0.30),
    "edge_bw_hz": 40.0,
}


def tonal_frames(y: np.ndarray, sr: int, fmin: float = 150.0, fmax: float = 1500.0) -> Optional[dict]:
    """Per-frame strongest bin between fmin and fmax, its level above that
    bin's median over the recording (steady hum and insect bands cancel) and
    above the bins either side (tonal, not broadband)."""
    if y.ndim > 1:
        y = y.mean(axis=1)
    n_fft = int(2 ** round(np.log2(sr * 0.085)))
    hop = n_fft // 4
    if len(y) < n_fft * 2:
        return None
    from scipy.signal import stft
    f, _t, Z = stft(y.astype(np.float32), fs=sr, nperseg=n_fft, noverlap=n_fft - hop,
                    boundary=None, padded=False)
    band = (f >= fmin) & (f <= fmax)
    fb = f[band]
    D = 10 * np.log10(np.abs(Z[band]).astype(np.float32) ** 2 + 1e-14)
    E = D - np.median(D, axis=1, keepdims=True)
    E = (np.roll(E, 1, 0) + E + np.roll(E, -1, 0)) / 3.0
    pk = E.argmax(axis=0)
    pv = E[pk, np.arange(E.shape[1])]
    w = max(3, int(round(60.0 / (fb[1] - fb[0]))))
    offs = np.r_[np.arange(-3 * w, -w), np.arange(w, 3 * w)]
    idx = np.clip(pk[None, :] + offs[:, None], 0, len(fb) - 1)
    side = np.median(E[idx, np.arange(E.shape[1])[None, :]], axis=0)
    return {"fb": fb, "D": D, "pk": pk, "pv": pv, "side": side,
            "frame_s": hop / sr, "win_s": n_fft / sr}


def events_from_frames(fr: Optional[dict], **kw) -> list:
    """Hoot-like events from tonal_frames: runs of tonal frames with a steady
    pitch lasting min_dur_s to max_dur_s whose onset or offset stands
    min_edge_db above the neighbouring audio at that pitch.
    Returns [(start_s, end_s, pitch_hz)]."""
    if fr is None:
        return []
    p = {**HOOT, **kw}
    fb, D, pk, pv, side = fr["fb"], fr["D"], fr["pk"], fr["pv"], fr["side"]
    frame_s = fr["frame_s"]
    tonal = (pv >= p["min_excess_db"]) & (pv - side >= p["min_contrast_db"])
    runs, run = [], []
    for i in np.flatnonzero(tonal):
        if run and (i - run[-1] <= 2) and abs(fb[pk[i]] - fb[pk[run[-1]]]) <= p["max_jump_hz"]:
            run.append(i)
            continue
        if run:
            runs.append(run)
        run = [i]
    if run:
        runs.append(run)
    bw = max(1, int(round(p["edge_bw_hz"] / (fb[1] - fb[0]))))
    e0, e1 = (max(1, int(round(x / frame_s))) for x in p["edge_s"])
    n = D.shape[1]
    out = []
    for r in runs:
        dur = (r[-1] - r[0] + 1) * frame_s
        if not (p["min_dur_s"] <= dur <= p["max_dur_s"]):
            continue
        pitch_bin = int(np.median(pk[r]))
        rows = slice(max(0, pitch_bin - bw), pitch_bin + bw + 1)
        if p["min_edge_db"] > 0:
            inside = float(D[rows, r[0]:r[-1] + 1].max(axis=0).mean())
            flanks = []
            if r[0] - e1 >= 0:
                flanks.append(float(D[rows, r[0] - e1:r[0] - e0 + 1].max(axis=0).mean()))
            if r[-1] + e1 < n:
                flanks.append(float(D[rows, r[-1] + e0:r[-1] + e1 + 1].max(axis=0).mean()))
            if flanks and inside - min(flanks) < p["min_edge_db"]:
                continue
        out.append((r[0] * frame_s, (r[-1] + 1) * frame_s + fr["win_s"] - frame_s,
                    float(np.median(fb[pk[r]]))))
    return out


def tonal_events(y: np.ndarray, sr: int, fmin: float = 150.0, fmax: float = 1500.0, **kw) -> list:
    """Sustained narrowband sounds between fmin and fmax (owl hoots, coos):
    [(start_s, end_s, pitch_hz)]. See tonal_frames and events_from_frames."""
    return events_from_frames(tonal_frames(y, sr, fmin, fmax), **kw)


def _hoot_pitches(events: list, start: float, end: float) -> list:
    inside = [(max(a, start), min(b, end), p) for a, b, p in events if b > start and a < end]
    if sum(b - a for a, b, _ in inside) < MIN_HOOT_S:
        return []
    return [p for _a, _b, p in inside]


def band_limited(y: np.ndarray, sr: int) -> np.ndarray:
    """200-2000 Hz copy, quantized to 16-bit as the earlier temp-WAV
    round trip did, so owl scores are unchanged."""
    from scipy.signal import butter, sosfiltfilt
    lo, hi = LOW_BAND_HZ
    hi = min(hi, sr / 2 - 100)
    sos = butter(6, [lo, hi], btype="band", fs=sr, output="sos")
    out = np.clip(sosfiltfilt(sos, y.astype(np.float64)), -1.0, 1.0)
    # libsndfile writes floats to PCM16 as floor(x * 32768).
    return (np.clip(np.floor(out * 32768.0), -32768, 32767) / 32768.0).astype(np.float32)


def sun_altitude(lat: float, lon: float, when_utc) -> float:
    """Sun's altitude in degrees (NOAA approximation, within ~1 degree).
    when_utc: naive UTC datetime."""
    import math
    doy = when_utc.timetuple().tm_yday
    hour = when_utc.hour + when_utc.minute / 60 + when_utc.second / 3600
    g = 2 * math.pi / 365 * (doy - 1 + (hour - 12) / 24)
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                    - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    tst = hour * 60 + eqt + 4 * lon
    ha = math.radians(tst / 4 - 180)
    la = math.radians(lat)
    cz = math.sin(la) * math.sin(decl) + math.cos(la) * math.cos(decl) * math.cos(ha)
    return 90 - math.degrees(math.acos(max(-1.0, min(1.0, cz))))


def _split_label(lbl: str) -> tuple:
    sci, _, common = lbl.partition("_")
    return sci, common


def _det(lbl: str, conf: float, start: float) -> dict:
    sci, common = _split_label(lbl)
    return {"common_name": common, "scientific_name": sci, "label": lbl,
            "confidence": float(conf), "start_time": start, "end_time": start + CHUNK_S}


def _read_mono_48k(wav_path: str) -> np.ndarray:
    y, sr = sf.read(wav_path, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    if sr != SAMPLE_RATE:
        import librosa
        y = librosa.resample(y, orig_sr=sr, target_sr=SAMPLE_RATE, res_type="kaiser_fast")
    return y.astype(np.float32)


def run_birdnet(wav_path: str, *, lat: Optional[float] = None, lon: Optional[float] = None,
                when=None, min_conf: float = 0.05, sensitivity: float = 1.5,
                overlap: float = 2.5, prior: Optional[list] = None,
                diag: Optional[dict] = None, species_min_conf: Optional[dict] = None,
                night_mode: str = "night", night_species: Optional[dict] = None) -> list:
    """Analyze a 48 kHz mono WAV. Returns birdnetlib-style dicts
    (common_name, scientific_name, label, confidence, start_time, end_time).

    prior: detections from an earlier pass on better audio (see
    PRIOR_TOLERANCE). Each is kept, at its earlier score, when it still
    clears today's thresholds and the new pass scores it within tolerance.

    species_min_conf: per-species thresholds (common name -> score) that
    replace min_conf (or the night floor) for those species.

    night_mode / night_species: whether night callers get their own floor
    or min_conf (see uses_night_floor).

    diag: filled with "best" (species -> highest score in this pass, down to
    the analysis floor), "not_expected" (species the location filter
    removed), "owl_no_hoot" (owls scored in the full band where no hoot was
    heard, so the band-limited pass never ran), "floor", "windows",
    "band_windows" and "near_misses" (night callers that scored at least
    NEAR_MISS_FLOOR but weren't kept, best window each, with the reason)."""
    overrides = {k: float(v) for k, v in (species_min_conf or {}).items() if v is not None}
    floor = min([float(min_conf), NIGHT_SPECIES_MIN_CONF, OWL_MIN_CONF] + list(overrides.values()))

    def required(name):
        return species_required(name, min_conf, overrides, night_mode, night_species)

    prior = [p for p in (prior or [])
             if float(p.get("confidence", 0.0)) >= required(p.get("common_name"))]
    run_floor = floor
    if prior:
        run_floor = max(0.01, min([floor] + [float(p["confidence"]) - PRIOR_TOLERANCE for p in prior]))
    # birdnetlib's Recording clamps its minimum the same way and keeps
    # scores strictly above it.
    run_floor = max(0.01, min(run_floor, 0.99))

    t0 = time.monotonic()
    y = _read_mono_48k(wav_path)
    chunks, starts = split_chunks(y, overlap)
    labs = labels()
    allow = allowed_labels(lat, lon, when) if (lat and lon and when) else None

    full = to_confidence(logits(chunks), sensitivity) if len(chunks) else np.zeros((0, len(labs)))
    commons = [_split_label(lb)[1] for lb in labs]
    owl_cols = np.array([i for i, c in enumerate(commons)
                         if is_low_owl(c) and (allow is None or labs[i] in allow)], dtype=int)

    # Which windows need the band-limited pass (see the module docstring).
    events = tonal_events(y, SAMPLE_RATE) if len(owl_cols) else []
    band_rows = []
    if len(owl_cols) and len(starts):
        prior_owl_starts = {float(p.get("start_time", 0.0)) for p in prior
                            if is_low_owl(p.get("common_name", ""))}
        strong = full[:, owl_cols].max(axis=1) >= STRONG_OWL_CONF
        for i, s0 in enumerate(starts):
            if strong[i] or s0 in prior_owl_starts or _hoot_pitches(events, s0, s0 + CHUNK_S):
                band_rows.append(i)
    low = {}
    if band_rows:
        try:
            yb = band_limited(y, SAMPLE_RATE)
            bchunks, _bs = split_chunks(yb, overlap)
            conf_b = to_confidence(logits(bchunks[band_rows]), sensitivity)
            low = {i: conf_b[k] for k, i in enumerate(band_rows)}
        except Exception as e:
            logger.warning("Owl band pass failed for %s: %s", wav_path, e)

    def expected_lbl(lbl):
        return allow is None or lbl in allow

    out = []
    best: dict = {}
    not_expected = set()
    for i, s0 in enumerate(starts):
        row = full[i]
        for j in np.flatnonzero(row > run_floor):
            name = commons[j]
            c = float(row[j])
            if not is_low_owl(name):
                best[name] = max(best.get(name, 0.0), c)
            if not expected_lbl(labs[j]):
                not_expected.add(name)
                continue
            if is_low_owl(name):
                continue
            if c >= required(name):
                out.append(_det(labs[j], c, s0))

    # Owls: scored on the band-limited copy, window by window.
    owl_dets, kept_strong, owl_no_hoot = decide_owls(full, low, starts, owl_cols, commons,
                                                     labs, events, required, run_floor)
    per_window = {d["start_time"]: d for d in owl_dets if not d.get("_strong")}
    out.extend(d for d in owl_dets if d.get("_strong"))
    for i, lrow in low.items():
        for j in owl_cols:
            if lrow[j] > run_floor:
                best[commons[j]] = max(best.get(commons[j], 0.0), float(lrow[j]))
    out.extend(per_window.values())
    for d in out:
        d.pop("_strong", None)
    owl_best: dict = {}
    for d in out:
        if is_low_owl(d["common_name"]):
            owl_best[d["common_name"]] = max(owl_best.get(d["common_name"], 0.0), d["confidence"])
    keep_owls = set(consolidate_owl_species(owl_best))
    dropped_owls = set(owl_best) - keep_owls
    if dropped_owls:
        out = [d for d in out if d["common_name"] not in dropped_owls]

    kept_prior = 0
    if prior:
        found = {(d["common_name"], float(d["start_time"])): d for d in out}
        idx_of = {s0: i for i, s0 in enumerate(starts)}
        col_of = {lb: j for j, lb in enumerate(labs)}
        for p in prior:
            key = (p.get("common_name"), float(p.get("start_time", 0.0)))
            lbl = p.get("label")
            if allow is not None and lbl not in allow:
                continue
            i, j = idx_of.get(key[1]), col_of.get(lbl)
            if i is None or j is None:
                continue
            was = float(p["confidence"])
            if is_low_owl(key[0]):
                # An owl keeps its earlier score only with full-band support
                # on this audio too (HOOT_FULL_MIN, less the Opus allowance).
                if float(full[i, j]) < HOOT_FULL_MIN - PRIOR_TOLERANCE:
                    continue
                now = float(low[i][j]) if i in low else 0.0
            else:
                now = float(full[i, j])
            # Found again, or scored just under threshold: the earlier score
            # (from the original audio) stands. Either way it stays visible.
            if now <= run_floor or now < was - PRIOR_TOLERANCE:
                continue
            if key in found:
                if found[key]["confidence"] < was:
                    found[key]["confidence"] = was
                    kept_prior += 1
            else:
                d = _det(lbl, was, key[1])
                out.append(d)
                found[key] = d
                kept_prior += 1

    if diag is not None:
        diag["best"] = best
        diag["floor"] = run_floor
        diag["not_expected"] = not_expected
        diag["owl_no_hoot"] = owl_no_hoot
        diag["windows"] = len(starts)
        diag["band_windows"] = len(low)
        diag["near_misses"] = _near_misses(full, low, starts, labs, commons, allow, out,
                                           required, events)

    elapsed = time.monotonic() - t0
    logger.info("Server BirdNET: %d detection(s) in %d window(s) (%d owl window(s) from %d "
                "band-limited window(s), %d strong full-band, %d hoot event(s), %d kept from the "
                "earlier pass); location filter %s; %.1f s (%.0f ms/window)",
                len(out), len(starts), len(per_window), len(low), kept_strong, len(events),
                kept_prior, "on" if allow is not None else "off", elapsed,
                1000 * elapsed / max(1, len(starts) + len(low)))
    out.sort(key=lambda d: (float(d.get("start_time", 0.0)), -float(d.get("confidence", 0.0))))
    return out


def consolidate_owl_species(best: dict, ratio: Optional[float] = None,
                            min_abs: Optional[float] = None) -> list:
    """Owl species to keep from {species: best score}: the top one, plus any
    other reaching ratio x the top score or min_abs."""
    ratio = SECOND_OWL_RATIO if ratio is None else ratio
    min_abs = SECOND_OWL_MIN if min_abs is None else min_abs
    if not best:
        return []
    top = max(best.values())
    return [n for n, v in best.items() if v >= top or v >= ratio * top or v >= min_abs]


def decide_owls(full, low: dict, starts: list, owl_cols, commons: list, labs: list,
                events: list, required, run_floor: float) -> tuple:
    """Owl detections from full-band scores (full, windows x labels) and
    band-limited scores (low, window index -> label scores; windows without
    a band pass are missing). A window keeps a strong full-band owl the band
    copy agrees with, or else its best band-limited owl that clears its
    threshold with a hoot at that species' pitch. Returns (detections
    (strong ones flagged "_strong"), strong count, {owl: full-band score}
    for owls in windows that had no band pass)."""
    per_window: dict = {}
    strong_out = []
    owl_no_hoot: dict = {}
    for i, s0 in enumerate(starts):
        lrow = low.get(i)
        for j in owl_cols:
            name = commons[j]
            s_full = float(full[i, j])
            if lrow is None:
                if s_full > run_floor:
                    owl_no_hoot[name] = max(owl_no_hoot.get(name, 0.0), s_full)
                continue
            s_low = float(lrow[j])
            s_full_kept = s_full if s_full > run_floor else 0.0
            s_low_kept = s_low if s_low > run_floor else 0.0
            if s_full_kept >= STRONG_OWL_CONF and s_low_kept >= 0.5 * s_full_kept:
                d = _det(labs[j], max(s_full_kept, s_low_kept), s0)
                d["_strong"] = True
                strong_out.append(d)
                continue
            if s_low_kept < required(name) or s_full < HOOT_FULL_MIN:
                continue
            lo, hi = OWL_PITCH_HZ.get(name, GENERIC_OWL_PITCH)
            if not any(lo <= p <= hi for p in _hoot_pitches(events, s0, s0 + CHUNK_S)):
                continue
            cur = per_window.get(s0)
            if cur is None or s_low_kept > cur["confidence"]:
                per_window[s0] = _det(labs[j], s_low_kept, s0)
    return strong_out + list(per_window.values()), len(strong_out), owl_no_hoot


def _near_misses(full, low, starts, labs, commons, allow, out, required, events) -> list:
    """Best unkept window per night caller scoring NEAR_MISS_FLOOR or more,
    with why it wasn't kept."""
    kept = {(d["common_name"], float(d["start_time"])) for d in out}
    kept_names = {d["common_name"] for d in out}
    res = []
    for j, name in enumerate(commons):
        if not NIGHT_CALLER_RE.search(name) or (allow is not None and labs[j] not in allow):
            continue
        owl = is_low_owl(name)
        cand = None
        for i, s0 in enumerate(starts):
            if (name, s0) in kept:
                continue
            if owl and i in low:
                c, src = float(low[i][j]), "band"
            else:
                c, src = float(full[i, j]), "full"
            if c >= NEAR_MISS_FLOOR and (cand is None or c > cand[0]):
                cand = (c, s0, src, i)
        if cand is None:
            continue
        c, s0, src, i = cand
        need = required(name)
        if c < need:
            why = "below threshold"
        elif owl and src == "full":
            why = "no hoot"
        elif owl:
            lo, hi = OWL_PITCH_HZ.get(name, GENERIC_OWL_PITCH)
            if any(lo <= p <= hi for p in _hoot_pitches(events, s0, s0 + CHUNK_S)):
                why = "outscored by another owl"
            else:
                why = "no hoot at its pitch"
        else:
            why = "below threshold"
        sci, _ = _split_label(labs[j])
        res.append({"common_name": name, "scientific_name": sci, "label": labs[j],
                    "confidence": round(c, 4), "start_time": s0, "end_time": s0 + CHUNK_S,
                    "threshold": need, "reason": why, "pass": src,
                    "detected_elsewhere": name in kept_names})
    res.sort(key=lambda r: -r["confidence"])
    return res[:10]
