#!/usr/bin/env python3
"""Score the owl clip set with the server BirdNET pass and tune the owl rules.

    python3 scripts/owl-eval/owl_eval.py                  # current settings
    python3 scripts/owl-eval/owl_eval.py --grid           # search, best first
    python3 scripts/owl-eval/owl_eval.py --pitches        # hoot pitches heard per owl
    python3 scripts/owl-eval/owl_eval.py --extra-neg DIR  # add more owl-free WAVs

Each clip is scored once (BirdNET full band and the 200-2000 Hz copy for
every window, plus the hoot detector's frame data) and cached as .npz next
to the clips, so a grid of settings replays in seconds. Besides the clips
themselves, every owl clip is also mixed with each noise bed (a katydid
chorus, tree crickets) at 1.5x the owl clip's RMS, the masking case the
band-limited pass exists for.

Scoring per clip: an owl clip is a hit when its owl is reported in any
window; any other owl reported is a wrong owl. Any owl on an owl-free clip
is a false alarm. The grid ranks settings by hits - wrong - 2 x false alarms.
"""
import argparse
import importlib.util
import itertools
import json
import os
import warnings

import numpy as np

warnings.filterwarnings("ignore")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))


def load_pass(server: str):
    path = os.path.join(REPO, server, "app", "services", "birdnet_pass.py")
    spec = importlib.util.spec_from_file_location("birdnet_pass_eval", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def variants(man, clip_dir, extra_neg, extra_pos=None):
    """(name, owl label or None, loader) for every clip and noise mix."""
    import soundfile as sf
    beds = {}
    for b in man.get("noise_beds", []):
        p = os.path.join(clip_dir, f"XC{b}.wav")
        if os.path.exists(p):
            beds[b] = sf.read(p, dtype="float32")[0]
    out = []
    for c in man["clips"]:
        p = os.path.join(clip_dir, f"XC{c['xc']}.wav")
        if not os.path.exists(p):
            continue
        label = c["label"] if c["owl"] else None
        out.append((f"XC{c['xc']}", label, (lambda p=p: sf.read(p, dtype="float32")[0])))
        if not c["owl"]:
            continue
        for b, noise in beds.items():
            def mix(p=p, noise=noise):
                y = sf.read(p, dtype="float32")[0]
                n = np.resize(noise, len(y))
                g = 1.5 * np.sqrt(np.mean(y ** 2)) / max(1e-9, np.sqrt(np.mean(n ** 2)))
                m = y + g * n
                return (m / max(1.0, np.abs(m).max())).astype(np.float32)
            out.append((f"XC{c['xc']}+XC{b}", label, mix))
    for fn in sorted(os.listdir(extra_neg)) if extra_neg else []:
        if fn.lower().endswith(".wav"):
            p = os.path.join(extra_neg, fn)

            def load(p=p):
                import subprocess
                import tempfile
                fd, t = tempfile.mkstemp(suffix=".wav")
                os.close(fd)
                subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", p, "-ac", "1", "-ar",
                                "48000", "-sample_fmt", "s16", t], check=True)
                y = sf.read(t, dtype="float32")[0]
                os.unlink(t)
                return y
            out.append((f"extra:{fn}", None, load))
    for fn in sorted(os.listdir(extra_pos)) if extra_pos else []:
        if fn.lower().endswith(".wav") and "__" in fn:
            p = os.path.join(extra_pos, fn)
            out.append((f"pos:{fn}", fn.split("__")[0].replace("_", " "),
                        (lambda p=p: sf.read(p, dtype="float32")[0])))
    return out


def build_cache(bp, name, loader, cache_dir, overlap, sensitivity):
    path = os.path.join(cache_dir, f"{name.replace(':', '_')}.npz")
    if os.path.exists(path):
        z = np.load(path, allow_pickle=True)
        return {k: z[k] for k in z.files}
    y = loader()
    labs = bp.labels()
    owl_cols = np.array([i for i, lb in enumerate(labs) if bp.is_low_owl(lb.partition("_")[2])])
    ch, starts = bp.split_chunks(y, overlap)
    full = bp.to_confidence(bp.logits(ch), sensitivity)
    bch, _ = bp.split_chunks(bp.band_limited(y, bp.SAMPLE_RATE), overlap)
    low = bp.to_confidence(bp.logits(bch), sensitivity)
    fr = bp.tonal_frames(y, bp.SAMPLE_RATE)
    data = {"starts": np.array(starts), "owl_cols": owl_cols,
            "full": full[:, owl_cols].astype(np.float32), "low": low[:, owl_cols].astype(np.float32),
            "fr": np.array([fr], dtype=object)}
    np.savez_compressed(path, **data)
    return data


def predict(bp, d, allow_cols, params):
    """Owls reported for one cached clip under params."""
    labs = bp.labels()
    commons = [lb.partition("_")[2] for lb in labs]
    cols = d["owl_cols"]
    keep = np.array([k for k, j in enumerate(cols) if labs[j] in allow_cols])
    if not len(keep) or not len(d["starts"]):
        return set()
    # Re-index to a compact label space: column k -> label cols[k].
    sub_labs = [labs[cols[k]] for k in keep]
    sub_commons = [commons[cols[k]] for k in keep]
    full = d["full"][:, keep]
    low = {i: row for i, row in enumerate(d["low"][:, keep])}
    events = bp.events_from_frames(d["fr"][0], **params["hoot"])
    floor = params["owl_floor"]

    def required(_name):
        return floor

    dets, _n, _nh = bp.decide_owls(full, low, list(d["starts"]), np.arange(len(keep)),
                                   sub_commons, sub_labs, events, required,
                                   min(0.10, floor))
    best = {}
    for x in dets:
        best[x["common_name"]] = max(best.get(x["common_name"], 0.0), x["confidence"])
    return set(bp.consolidate_owl_species(best, params.get("second_ratio", 0.0),
                                          params.get("second_abs", 1.0)))


_EV_CACHE: dict = {}


def fast_predict(bp, name, d, allow_cols, params):
    """predict() vectorized: same rules, numpy over windows x owls."""
    labs = bp.labels()
    cols = d["owl_cols"]
    keep = np.array([k for k, j in enumerate(cols) if labs[j] in allow_cols])
    if not len(keep) or not len(d["starts"]):
        return set()
    names = [labs[cols[k]].partition("_")[2] for k in keep]
    full = d["full"][:, keep]
    low = d["low"][:, keep]
    hk = (name, tuple(sorted(params["hoot"].items())))
    if hk not in _EV_CACHE:
        _EV_CACHE[hk] = bp.events_from_frames(d["fr"][0], **params["hoot"])
    events = _EV_CACHE[hk]
    starts = d["starts"]
    floor = params["owl_floor"]
    run_floor = min(0.10, floor)
    fk = np.where(full > run_floor, full, 0.0)
    lk = np.where(low > run_floor, low, 0.0)
    strong = (fk >= params["strong"]) & (lk >= 0.5 * fk)
    rng = np.array([bp.OWL_PITCH_HZ.get(n, bp.GENERIC_OWL_PITCH) for n in names], dtype=float)
    pitch_ok = np.zeros(full.shape, dtype=bool)
    for w, s0 in enumerate(starts):
        ps = bp._hoot_pitches(events, float(s0), float(s0) + bp.CHUNK_S)
        if ps:
            p = np.array(ps)[:, None]
            pitch_ok[w] = ((p >= rng[:, 0]) & (p <= rng[:, 1])).any(axis=0)
    cand = np.where((~strong) & (lk >= floor) & pitch_ok & (full >= params.get("hoot_full", 0.0)), lk, 0.0)
    best = {}
    for w, k in zip(*np.nonzero(strong)):
        best[names[k]] = max(best.get(names[k], 0.0), max(fk[w, k], lk[w, k]))
    top = cand.argmax(axis=1)
    for w, k in enumerate(top):
        if cand[w, k] > 0:
            best[names[k]] = max(best.get(names[k], 0.0), cand[w, k])
    return set(bp.consolidate_owl_species(best, params.get("second_ratio", 0.0),
                                          params.get("second_abs", 1.0)))


def evaluate(bp, cached, allow_cols, params, fast=True):
    hits = wrong = fa = pos = neg = 0
    rows = []
    for name, label, d in cached:
        got = (fast_predict(bp, name, d, allow_cols, params) if fast
               else predict(bp, d, allow_cols, params))
        if label:
            pos += 1
            h = label in got
            w = len(got - {label})
            hits += h
            wrong += w
        else:
            neg += 1
            h, w = None, 0
            fa += bool(got)
        rows.append((name, label, sorted(got)))
    return {"hits": hits, "pos": pos, "wrong": wrong, "false_alarms": fa, "neg": neg,
            "score": hits - wrong - 2 * fa}, rows


_G = None


def _params(current, g):
    return {"strong": g["strong"], "owl_floor": g["owl_floor"], "hoot_full": g.get("hoot_full", 0.0),
            "second_ratio": g["second_ratio"], "second_abs": g["second_abs"],
            "hoot": {**current["hoot"], **{k: g[k] for k in
                     ("min_edge_db", "min_excess_db", "min_contrast_db", "min_dur_s", "max_dur_s")}}}


def _score(g):
    bp, cached, allow, current = _G
    params = _params(current, g)
    apply(bp, params)
    return evaluate(bp, cached, allow, params)[0]


def apply(bp, params):
    bp.STRONG_OWL_CONF = params["strong"]
    bp.HOOT_FULL_MIN = params.get("hoot_full", 0.0)
    bp.OWL_PITCH_HZ.update(params.get("pitch", {}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.expanduser("~/.cache/chirp-owl-eval"))
    ap.add_argument("--server", default="chirp-server-instances")
    ap.add_argument("--extra-neg", default=None)
    ap.add_argument("--extra-pos", default=None, help="owl WAVs named '<Owl species>__<id>.wav'")
    ap.add_argument("--focus", action="store_true", help="grid over the score rules only (hoot detector as is)")
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--pitches", action="store_true")
    ap.add_argument("--show", action="store_true", help="print each clip's result")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    args = ap.parse_args()

    bp = load_pass(args.server)
    man = json.load(open(os.path.join(HERE, "manifest.json")))
    import datetime
    allow = bp.allowed_labels(man["location"]["lat"], man["location"]["lon"],
                              datetime.date.fromisoformat(man["date"]))
    cache_dir = os.path.join(args.dir, "cache")
    os.makedirs(cache_dir, exist_ok=True)
    cached = []
    for name, label, loader in variants(man, args.dir, args.extra_neg, args.extra_pos):
        cached.append((name, label, build_cache(bp, name, loader, cache_dir, 2.5, 1.5)))

    current = {"strong": bp.STRONG_OWL_CONF, "owl_floor": bp.OWL_MIN_CONF, "hoot_full": bp.HOOT_FULL_MIN,
               "second_ratio": bp.SECOND_OWL_RATIO, "second_abs": bp.SECOND_OWL_MIN,
               "hoot": dict(bp.HOOT)}

    if args.pitches:
        labs = bp.labels()
        for owl in sorted({lb for _n, lb, _d in cached if lb}):
            ps = []
            for _n, lb, d in cached:
                if lb != owl or "+" in _n:
                    continue
                k = [i for i, j in enumerate(d["owl_cols"]) if labs[j].endswith("_" + owl)][0]
                ev = bp.events_from_frames(d["fr"][0], **current["hoot"])
                for i, s0 in enumerate(d["starts"]):
                    if d["low"][i, k] >= 0.2:
                        ps += [p for a, b, p in ev if b > s0 and a < s0 + 3]
            if ps:
                q = np.percentile(ps, [5, 25, 50, 75, 95])
                print(f"{owl:24s} n={len(ps):4d}  p5 {q[0]:.0f}  p25 {q[1]:.0f}  median {q[2]:.0f}  "
                      f"p75 {q[3]:.0f}  p95 {q[4]:.0f} Hz   (range now {bp.OWL_PITCH_HZ.get(owl)})")
        return

    if not args.grid:
        apply(bp, current)
        res, rows = evaluate(bp, cached, allow, current)
        slow, _ = evaluate(bp, cached, allow, current, fast=False)
        assert slow == res, (slow, res)   # the vectorized scorer matches the pass
        print(json.dumps(res))
        if args.show:
            for name, label, got in rows:
                ok = (label in got and len(got) == 1) if label else not got
                print(f"{'ok ' if ok else 'BAD'} {name:28s} {label or '-':24s} {', '.join(got)}")
        return

    grid = {
        "owl_floor": [0.10, 0.15, 0.20, 0.25, 0.30],
        "hoot_full": [0.0],
        "second_ratio": [0.0, 0.6, 0.8, 1.0],
        "second_abs": [0.7, 1.0],
        "strong": [0.4, 0.5, 0.6],
        "min_edge_db": [0.0, 3.0, 5.0, 8.0],
        "min_excess_db": [6.0, 8.0, 10.0],
        "min_contrast_db": [3.0, 5.0, 7.0],
        "min_dur_s": [0.1, 0.2, 0.3],
        "max_dur_s": [2.0, 4.0],
    }
    if args.focus:
        h = current["hoot"]
        grid = {"owl_floor": [0.15, 0.20, 0.25, 0.30, 0.35],
                "hoot_full": [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 1.01],
                "strong": [0.4, 0.45, 0.5, 0.6],
                "second_ratio": [current["second_ratio"]], "second_abs": [current["second_abs"]],
                "min_edge_db": [h["min_edge_db"]], "min_excess_db": [h["min_excess_db"]],
                "min_contrast_db": [h["min_contrast_db"]], "min_dur_s": [h["min_dur_s"]],
                "max_dur_s": [h["max_dur_s"]]}
    combos = [dict(zip(grid, c)) for c in itertools.product(*grid.values())]
    workers = max(1, min(args.jobs, len(combos)))
    global _G
    _G = (bp, cached, allow, current)
    if workers > 1:
        import multiprocessing as mp
        with mp.get_context("fork").Pool(workers) as pool:
            scored = pool.map(_score, combos, chunksize=64)
    else:
        scored = [_score(g) for g in combos]
    results = sorted(zip(scored, combos), key=lambda r: -r[0]["score"])
    out_path = os.path.join(args.dir, "grid_results.json")
    json.dump([{"res": r, "params": g} for r, g in results], open(out_path, "w"))
    apply(bp, current)
    base, _ = evaluate(bp, cached, allow, current)
    print("current:", json.dumps(base))
    print("all results:", out_path)
    # Halves by XC number (mixes follow their clip): a setting that only
    # wins on one half is fitting individual clips.
    def xc_half(name):
        return int(name.split("+")[0][2:]) % 2
    half = [[c for c in cached if c[0].startswith("XC") and xc_half(c[0]) == k] for k in (0, 1)]
    groups = {"xc": [c for c in cached if c[0].startswith("XC")],
              "field_pos": [c for c in cached if c[0].startswith("pos:")],
              "field_neg": [c for c in cached if c[0].startswith("extra:")]}

    def by_group(params):
        out = {}
        for k, part in groups.items():
            if part:
                r = evaluate(bp, part, allow, params)[0]
                out[k] = f"{r['hits']}/{r['pos']} hit, {r['wrong']} wrong, {r['false_alarms']}/{r['neg']} FA"
        return out
    print("current by group:", json.dumps(by_group(current)))
    for res, g in results[:25]:
        params = _params(current, g)
        apply(bp, params)
        h = [evaluate(bp, part, allow, params)[0]["score"] for part in half]
        print(res["score"], "halves", h, json.dumps(by_group(params)),
              json.dumps({k: g[k] for k in ("owl_floor", "hoot_full", "strong", "second_ratio", "second_abs")}))
    apply(bp, current)


if __name__ == "__main__":
    main()
