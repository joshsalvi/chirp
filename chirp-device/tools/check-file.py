#!/usr/bin/env python3
"""
Run a recording through this device's own detection steps and say where a
call would be lost. Use it on a clip another recorder caught (a HaikuBox
download, say) that this device missed.

    cd ~/chirp-device && venv/bin/python tools/check-file.py ~/owl.wav \
        --when "2026-10-02 00:12"

Steps, with the settings the service is running (config.yaml plus the
server's pushed settings, saved by device 1.3.2+ in state/effective_config.json):

  1. Energy gate: loudest 0.5 s in each 3 s window, band-passed, vs the
     gate. The clip was recorded by a different microphone at its own gain,
     so this level is only a guide; compare with the overnight "Window
     stats" lines from tools/night-check.sh.
  2. BirdNET on the configured backend (Coral or CPU), with the night-caller
     floor and the location filter for the date given.
  3. The same windows with no location filter, to show what it removes.

Read-only: nothing is uploaded and the running service is not touched.
"""
import argparse
import contextlib
import io
import json
import os
import sys
from datetime import datetime

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


def load_settings(config_path: str) -> tuple:
    from chirp.config import load_config
    base = load_config(config_path)
    eff = os.path.join(ROOT, "state", "effective_config.json")
    if os.path.exists(eff):
        try:
            with open(eff) as f:
                return json.load(f), f"server-applied settings ({eff}, {datetime.fromtimestamp(os.path.getmtime(eff)):%Y-%m-%d %H:%M})"
        except Exception as e:
            print(f"! {eff} unreadable ({e}); using {config_path}")
    return base, f"{config_path} only (no server-applied snapshot yet: device 1.3.2+ writes one when it applies the server's settings)"


def read_audio(path: str, sr: int) -> np.ndarray:
    import soundfile as sf
    try:
        y, file_sr = sf.read(path, dtype="float32", always_2d=True)
    except Exception:
        import librosa
        y, file_sr = librosa.load(path, sr=None, mono=False)
        y = np.atleast_2d(y).T.astype(np.float32)
    y = y.mean(axis=1)
    if file_sr != sr:
        from math import gcd
        from scipy.signal import resample_poly
        g = gcd(sr, file_sr)
        y = resample_poly(y, sr // g, file_sr // g).astype(np.float32)
    return y


def quiet():
    """birdnetlib prints progress to stdout; keep the table readable."""
    return contextlib.redirect_stdout(io.StringIO())


def make_backend(cfg: dict, name: str):
    if name == "coral":
        from chirp.birdnet_coral import BirdNetCoral, check_coral_available
        if check_coral_available():
            b = BirdNetCoral(cfg)
            with quiet():
                ok = b.load()
            if ok:
                return b, "coral"
        print("! Coral requested but not available or not loading: the service falls back to CPU too")
    from chirp.birdnet_cpu import BirdNetCPU
    b = BirdNetCPU(cfg)
    with quiet():
        ok = b.load()
    if not ok:
        sys.exit("BirdNET (CPU) failed to load")
    return b, "cpu"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wav")
    ap.add_argument("--config", default=os.path.join(ROOT, "config.yaml"))
    ap.add_argument("--when", help='local date/time the clip was recorded, e.g. "2026-10-02 00:12" (default: now)')
    ap.add_argument("--backend", choices=["cpu", "coral"], help="override the configured backend")
    ap.add_argument("--species", default="Barred Owl", help="species to look for (default: Barred Owl; \"Owl\" matches any owl)")
    args = ap.parse_args()

    import logging
    logging.basicConfig(level=logging.WARNING)
    cfg, source = load_settings(args.config)
    det, bn, audio = cfg["detection"], cfg["detection"]["birdnet"], cfg["audio"]
    ef = det["energy_filter"]
    sr = int(audio["sample_rate"])
    when = datetime.strptime(args.when, "%Y-%m-%d %H:%M") if args.when else datetime.now()
    backend_name = args.backend or bn.get("backend", "cpu")
    version = open(os.path.join(ROOT, "VERSION")).read().strip() if os.path.exists(os.path.join(ROOT, "VERSION")) else "?"

    print(f"Chirp device {version}  settings: {source}")
    print(f"backend {backend_name}  min_conf {bn.get('min_confidence')}  night floor "
          f"{bn.get('night_species_min_confidence', 0.10)}  sensitivity {bn.get('sensitivity')}  "
          f"overlap {bn.get('overlap_seconds')} s  lat {bn.get('latitude')} lon {bn.get('longitude')}")
    print(f"gate {ef.get('threshold_db')} dB over {ef.get('frequency_band_hz')} Hz  "
          f"(enabled: {ef.get('enabled')})  input gain {audio.get('input_gain_db', 0)} dB  date {when:%Y-%m-%d}")
    try:
        parts = [int(x) for x in version.split(".")[:3]]
        if parts < [1, 3, 1]:
            print("!! This device is older than 1.3.1: its location filter drops Barred Owl and other owls "
                  "in autumn. Update the device first.")
    except ValueError:
        pass

    y = read_audio(args.wav, sr)
    gain = float(audio.get("input_gain_db", 0) or 0)
    print(f"clip {len(y) / sr:.1f} s (device gain of {gain:+.0f} dB applied for the gate check only)\n")

    # Same filter and level as chirp/detector.py's energy gate (built here
    # so this runs without the audio stack).
    from chirp.utils import rms_db
    from scipy.signal import butter, sosfilt
    nyq = sr / 2
    lo, hi = ef["frequency_band_hz"]
    sos = butter(ef.get("filter_order", 4), [lo / nyq, min(hi, nyq * 0.99) / nyq], btype="band", output="sos")
    n_sub = int(float(ef.get("window_seconds", 0.5)) * sr)

    def gate_db(w):
        f = sosfilt(sos, (w * 10 ** (gain / 20)).astype(np.float64))
        n = min(n_sub, len(f))
        return max(rms_db(f[i:i + n]) for i in range(0, max(1, len(f) - n + 1), max(1, n // 2)))

    if bn.get("latitude") is not None and bn.get("longitude") is not None:
        from chirp.birdnet_cpu import allowed_labels
        with quiet():   # builds the location list once, before the backends' warm-up threads
            allowed_labels(bn["latitude"], bn["longitude"], when.date())
    backend, used = make_backend(cfg, backend_name)
    nofilter_cfg = json.loads(json.dumps(cfg))
    nofilter_cfg["detection"]["birdnet"]["latitude"] = None
    nofilter_cfg["detection"]["birdnet"]["longitude"] = None
    backend_nf, _ = make_backend(nofilter_cfg, used)

    win = 3 * sr
    hop = max(1, int((3 - float(bn.get("overlap_seconds", 0) or 0)) * sr))
    want = args.species.lower()
    kept_any = gated_any = False
    print(f"{'window':>11}  {'gate dB':>8}  {'kept by the device':<44}  removed by location filter")
    for start in range(0, max(1, len(y) - sr), hop):
        w = y[start:start + win]
        if len(w) < win:
            w = np.pad(w, (0, win - len(w)))
        db = gate_db(w)
        passed = (not ef.get("enabled", True)) or db >= float(ef["threshold_db"])
        with quiet():
            dets = backend.analyze(w, timestamp=when)
            raw = backend_nf.analyze(w, timestamp=when)
        kept = {d.common_name: d.confidence for d in dets}
        removed = {d.common_name: d.confidence for d in raw if d.common_name not in kept}
        show = lambda d: ", ".join(f"{k} {v:.2f}" for k, v in sorted(d.items(), key=lambda kv: -kv[1])[:3]) or "-"
        t = f"{start / sr:4.1f}-{(start + win) / sr:4.1f}s"
        print(f"{t:>11}  {db:8.1f}{'' if passed else ' (below gate)'}  {show(kept):<44}  {show(removed)}")
        hit = any(want in k.lower() for k in kept)
        kept_any |= hit and passed
        gated_any |= hit and not passed

    print()
    if kept_any:
        print(f"RESULT: the device would trigger on {args.species} in this clip. If it didn't last night, "
              "the call was fainter at the device's microphone (compare levels with night-check.sh), "
              "the service wasn't running, or the recording was removed after upload (Settings → Recordings auto-purge).")
    elif gated_any:
        print(f"RESULT: BirdNET finds {args.species}, but the energy gate would drop these windows. "
              "Lower detection.energy_filter.threshold_db (or the server's gate setting).")
    else:
        print(f"RESULT: no {args.species} kept. If the 'removed by location filter' column shows it, "
              "the location filter is the cause; otherwise BirdNET's score is under the floor above.")


if __name__ == "__main__":
    main()
