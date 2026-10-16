"""
BirdNET v3 (developer preview 3.1) on the server: Settings → Detection.

AppSettings:
  detection_model      "birdnet3" (default): BirdNET v3 makes the server's
                       detections (uploads, Re-analyze, Live Detect), with
                       owl_check below in place of BirdNET 2.4's owl rules;
                       exp_birdnet3_min_conf is the threshold. "birdnet24":
                       BirdNET 2.4 with its owl rules (birdnet_pass.py).
  exp_birdnet3_shadow  with 2.4 only: BirdNET v3 also scores each recording
                       for comparison (shadow_detections, shown on the
                       recording page); nothing else changes.
  exp_birdnet3_main    from 0.5.13; no longer read.

Model: ONNX, 5 s of 32 kHz mono in, 11,560 scores out (birds, frogs,
insects, mammals). Downloaded on first use to ai_models_dir/birdnet3 and
checked against the repository's SHA256SUMS. CC BY-SA 4.0; the model's
terms bar poaching and military use (TERMS_OF_USE.txt is saved with it).

Names: every BirdNET v3 label is mapped to the BirdNET 2.4 label Chirp
already uses (data/birdnet3_labels_to_v24.tsv: by scientific name, then
common name, then eBird's current names). "Grey Catbird" stays "Gray
Catbird", so profiles and the life list don't split. Labels with no
BirdNET 2.4 match (non-birds, a few island species) are dropped, which
also limits results to birds.

Location: the same list as the BirdNET 2.4 pass (birdnet_pass.allowed_labels,
including its night-caller allowance), so both models are filtered alike.

Evaluation (docs/model-evaluation-2026-10.md): on 9.3 h of labeled
soundscapes it found about twice as many species as BirdNET 2.4 at the
same precision, with far fewer false alarms on noise.
"""
import hashlib
import logging
import os
import threading
import time
import urllib.request
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("chirp.birdnet3")

REPO = "https://huggingface.co/tphakala/BirdNET-v3.0-Models/resolve/main"
FILES = {
    "model": "full/birdnet-v3.0-preview3.1-fp32-b1.onnx",
    "labels": "full/birdnet-v3.0-preview3.1-labels-b1.txt",
    "terms": "TERMS_OF_USE.txt",
}
SR = 32000
WINDOW = 5.0
HOP = 2.5                 # half-window overlap: a call on a boundary is whole in the next window
DEFAULT_MIN_CONF = 0.5    # ~90% precision on the evaluation soundscapes
MAP_FILE = Path(__file__).parent / "data" / "birdnet3_labels_to_v24.tsv"

_lock = threading.Lock()
_state = {"state": "idle", "error": None, "bytes": 0, "total": 0}
_session = None
_index = None             # (indices into the output, BirdNET 2.4 labels)


def model_dir() -> Path:
    from ..config import settings
    return Path(settings.ai_models_dir) / "birdnet3"


def _path(key: str) -> Path:
    return model_dir() / os.path.basename(FILES[key])


def installed() -> bool:
    return all(_path(k).exists() for k in ("model", "labels"))


def status() -> dict:
    s = dict(_state)
    if installed() and s["state"] != "downloading":
        s["state"] = "ready"
        s["size_mb"] = round(_path("model").stat().st_size / 1e6)
    elif s["state"] == "idle":
        s["state"] = "missing"
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        s.update(state="error", error="onnxruntime is not installed on this server")
    return s


def _expected_sha() -> dict:
    with urllib.request.urlopen(f"{REPO}/SHA256SUMS", timeout=30) as r:
        out = {}
        for line in r.read().decode().splitlines():
            parts = line.split()
            if len(parts) == 2:
                out[parts[1].lstrip("*./")] = parts[0]
        return out


def _download():
    try:
        d = model_dir(); d.mkdir(parents=True, exist_ok=True)
        try:
            sums = _expected_sha()
        except Exception as e:
            logger.warning("BirdNET v3: couldn't read SHA256SUMS (%s); downloading without the check", e)
            sums = {}
        for key, rel in FILES.items():
            dest = _path(key)
            if dest.exists():
                continue
            tmp = dest.with_suffix(dest.suffix + ".part")
            h = hashlib.sha256()
            with urllib.request.urlopen(f"{REPO}/{rel}", timeout=60) as r, open(tmp, "wb") as f:
                _state["total"] = int(r.headers.get("Content-Length") or 0) if key == "model" else _state["total"]
                _state["bytes"] = 0
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b); h.update(b)
                    if key == "model":
                        _state["bytes"] += len(b)
            want = sums.get(rel)
            if want and h.hexdigest() != want:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f"{os.path.basename(rel)} failed its checksum")
            tmp.rename(dest)
        _state.update(state="ready", error=None)
        logger.info("BirdNET v3 model ready in %s", d)
    except Exception as e:
        _state.update(state="error", error=str(e))
        logger.error("BirdNET v3 download failed: %s", e)


def ensure_downloaded() -> dict:
    """Start the download in the background if the model isn't here yet."""
    with _lock:
        if not installed() and _state["state"] != "downloading":
            _state.update(state="downloading", error=None, bytes=0, total=0)
            threading.Thread(target=_download, name="birdnet3-download", daemon=True).start()
    return status()


def _load():
    global _session, _index
    with _lock:
        if _session is not None:
            return
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.intra_op_num_threads = min(8, os.cpu_count() or 2)
        sess = ort.InferenceSession(str(_path("model")), so, providers=["CPUExecutionProvider"])
        labels3 = [l.strip() for l in _path("labels").read_text(encoding="utf-8").splitlines() if l.strip()]
        mapping = {}
        for line in MAP_FILE.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#") and "\t" in line:
                a, b = line.split("\t", 1)
                mapping[a] = b
        from .birdnet_pass import labels as v24_labels
        known = set(v24_labels())
        idx, labs = [], []
        for i, l in enumerate(labels3):
            t = mapping.get(l)
            if t and t in known:
                idx.append(i); labs.append(t)
        _index = (np.array(idx), labs)
        _session = sess
        logger.info("BirdNET v3 loaded: %d of %d labels map to Chirp species", len(idx), len(labels3))


def _audio(wav_path: str) -> np.ndarray:
    import librosa
    y, _ = librosa.load(wav_path, sr=SR, mono=True)
    return y.astype(np.float32)


def scores(y: np.ndarray) -> tuple:
    """Window starts (s) and scores [windows, mapped labels] for 32 kHz audio."""
    _load()
    n, hop = int(WINDOW * SR), int(HOP * SR)
    starts, rows = [], []
    iname = _session.get_inputs()[0].name
    oname = _session.get_outputs()[0].name
    last = max(0, len(y) - n)
    pos = list(range(0, last + 1, hop))
    if not pos or pos[-1] < last:
        pos.append(last)          # the tail is scored too, not dropped
    for p in pos:
        w = y[p:p + n]
        if len(w) < n:
            w = np.pad(w, (0, n - len(w)))
        out = _session.run([oname], {iname: w[None, :]})[0][0]
        rows.append(out[_index[0]])
        starts.append(p / SR)
    return np.array(starts), np.array(rows, dtype=np.float32)


def analyze(wav_path: str, *, lat: Optional[float] = None, lon: Optional[float] = None,
            when=None, min_conf: float = DEFAULT_MIN_CONF, start_utc=None,
            owls: bool = True, diag: Optional[dict] = None) -> list:
    """BirdNET-2.4-style detection dicts (label, common_name, scientific_name,
    confidence, start_time, end_time), Chirp names, location-filtered.
    owls: apply owl_check (start_utc, the recording's start, enables the
    daylight rule)."""
    if not installed():
        raise RuntimeError("BirdNET v3 model isn't downloaded yet")
    t0 = time.time()
    y = _audio(wav_path)
    if len(y) < SR * 0.5:
        return []
    starts, S = scores(y)
    labs = _index[1]
    allowed = None
    if lat is not None and lon is not None:
        from .birdnet_pass import allowed_labels
        allowed = allowed_labels(lat, lon, when)
    dur = len(y) / SR
    out = []
    for j, lbl in enumerate(labs):
        if allowed is not None and lbl not in allowed:
            continue
        col = S[:, j]
        for i in np.where(col >= min_conf)[0]:
            sci, com = lbl.split("_", 1)
            out.append({"label": lbl, "common_name": com, "scientific_name": sci,
                        "confidence": float(col[i]), "start_time": float(starts[i]),
                        "end_time": float(min(dur, starts[i] + WINDOW))})
    out.sort(key=lambda d: (d["start_time"], -d["confidence"]))
    if owls:
        out = owl_check(out, wav_path, lat=lat, lon=lon, start_utc=start_utc, diag=diag)
    logger.info("BirdNET v3: %d detection(s) in %.1f s of audio (%.1f s)", len(out), dur, time.time() - t0)
    return out


# Owl checks for BirdNET v3 (birdnet_pass's rules are tuned to 2.4's scores).
# An owl window needs a hoot at that owl's pitch (birdnet_pass.tonal_events),
# and in daylight a score of at least DAY_OWL_MIN; then one owl species per
# recording unless a second is about as strong (consolidate_owl_species).
# Natick, 15 Oct 2026: a Great Horned Owl hooting at 328 Hz from 7:13 to
# 7:19 pm kept 33 of 35 windows; a 0.61 "Great Horned Owl" at 4:59 pm
# (daylight, coo-like notes) was dropped.
DAY_OWL_MIN = 0.80


def owl_check(dets: list, wav_path: str, *, lat=None, lon=None, start_utc=None,
              diag: Optional[dict] = None) -> list:
    from . import birdnet_pass as bp
    owls = [d for d in dets if bp.is_low_owl(d["common_name"])]
    if not owls:
        return dets
    y48 = bp._read_mono_48k(wav_path)
    events = bp.tonal_events(y48, bp.SAMPLE_RATE)
    daylight = False
    if start_utc is not None and lat is not None and lon is not None:
        try:
            daylight = bp.sun_altitude(lat, lon, start_utc) > 0
        except Exception:
            daylight = False
    dropped = {}
    kept = []
    for d in owls:
        lo, hi = bp.OWL_PITCH_HZ.get(d["common_name"], bp.GENERIC_OWL_PITCH)
        hooted = any(lo <= p <= hi for p in bp._hoot_pitches(events, d["start_time"], d["end_time"]))
        if not hooted:
            dropped[d["common_name"]] = "no hoot at its pitch"
        elif daylight and d["confidence"] < DAY_OWL_MIN:
            dropped[d["common_name"]] = "daylight"
        else:
            kept.append(d)
    best = {}
    for d in kept:
        best[d["common_name"]] = max(best.get(d["common_name"], 0.0), d["confidence"])
    keep_names = set(bp.consolidate_owl_species(best))
    for n in set(best) - keep_names:
        dropped[n] = "outscored by another owl"
    out = [d for d in dets if not bp.is_low_owl(d["common_name"])] + \
          [d for d in kept if d["common_name"] in keep_names]
    out.sort(key=lambda d: (d["start_time"], -d["confidence"]))
    if diag is not None:
        diag["owls_dropped"] = dropped
    if dropped:
        logger.info("BirdNET v3 owl check dropped %s", ", ".join(f"{k} ({v})" for k, v in dropped.items()))
    return out


def summarize(dets: list) -> dict:
    """Best score and window count per species."""
    best = {}
    for d in dets:
        b = best.setdefault(d["common_name"], {"common_name": d["common_name"],
                                                "scientific_name": d["scientific_name"],
                                                "confidence": 0.0, "windows": 0})
        b["confidence"] = max(b["confidence"], d["confidence"]); b["windows"] += 1
    return best
