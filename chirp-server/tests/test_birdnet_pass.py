"""
Server BirdNET pass: parity with birdnetlib, hoot detector, owl rules, and
(when the clip set is present) the owl regression numbers.

    cd chirp-server-instances && python3 -m pytest -q tests/test_birdnet_pass.py

The owl regression test needs the clips from scripts/owl-eval/fetch.py
(default ~/.cache/chirp-owl-eval, or CHIRP_OWL_EVAL_DIR) and is skipped
without them.
"""
import datetime
import json
import os
import sys

import numpy as np
import pytest
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from app.services import birdnet_pass as bp  # noqa: E402

SR = 48000
REPO = os.path.dirname(os.path.dirname(HERE))


def tone(freq, dur, amp=0.2):
    t = np.arange(int(dur * SR)) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def noise(dur, amp=0.005, seed=0):
    return (amp * np.random.default_rng(seed).standard_normal(int(dur * SR))).astype(np.float32)


def test_split_chunks_matches_birdnetlib():
    pytest.importorskip("birdnetlib")
    from birdnetlib.main import RecordingBase

    class R(RecordingBase):
        def __init__(self, y, overlap):
            super().__init__(None, overlap=overlap)
            self.ndarray = y

    for dur, ov in [(10.0, 2.5), (7.3, 1.5), (4.4, 0.0), (1.2, 2.0), (35.1, 2.1)]:
        y = noise(dur)
        rec = R(y, ov)
        rec.process_audio_data(SR)
        chunks, starts = bp.split_chunks(y, ov)
        assert len(chunks) == len(rec.chunks)
        for a, b in zip(chunks, rec.chunks):
            assert np.array_equal(a, np.asarray(b, dtype=np.float32))
        s = 0.0
        for st in starts:
            assert st == s
            s += 3.0 - ov


def test_scores_match_birdnetlib(tmp_path):
    pytest.importorskip("birdnetlib")
    from birdnetlib import Recording
    from birdnetlib.analyzer import Analyzer
    y = np.concatenate([noise(2.0), tone(2500, 1.0), noise(3.0)])
    p = tmp_path / "t.wav"
    sf.write(p, y, SR, subtype="PCM_16")
    an = Analyzer()
    rec = Recording(an, str(p), min_conf=0.01, sensitivity=1.25, overlap=1.5)
    rec.analyze()
    y16, _ = sf.read(p, dtype="float32")
    ch, starts = bp.split_chunks(y16, 1.5)
    conf = bp.to_confidence(bp.logits(ch), 1.25)
    labs = bp.labels()
    for d in rec.detections:
        i = starts.index(d["start_time"])
        j = labs.index(d["label"])
        assert abs(conf[i, j] - d["confidence"]) < 2e-3


def test_engine_drone_is_not_a_hoot():
    # A 6 s drone with slow wobble, then three 0.5 s hoots with gaps.
    t = np.arange(int(6 * SR)) / SR
    drone = (0.1 * np.sin(2 * np.pi * (360 + 8 * np.sin(2 * np.pi * 0.7 * t)) * t)).astype(np.float32)
    hoots = np.concatenate([np.concatenate([tone(420, 0.5, 0.15), np.zeros(int(0.4 * SR), np.float32)])
                            for _ in range(3)])
    y = np.concatenate([noise(3), drone + noise(6, seed=1), noise(3, seed=2), hoots + noise(len(hoots) / SR, seed=3), noise(3, seed=4)])
    ev = bp.tonal_events(y, SR, min_edge_db=6.0)
    assert ev, "hoots should be found"
    assert all(a >= 11.5 for a, _b, _p in ev), f"drone reported as hoot: {ev}"
    assert all(380 <= p <= 460 for _a, _b, p in ev)


def test_consolidate_owl_species():
    assert bp.consolidate_owl_species({}) == []
    got = set(bp.consolidate_owl_species({"Barred Owl": 0.6, "Northern Saw-whet Owl": 0.2}, 0.8, 0.7))
    assert got == {"Barred Owl"}
    got = set(bp.consolidate_owl_species({"Barred Owl": 0.6, "Great Horned Owl": 0.55}, 0.8, 0.7))
    assert got == {"Barred Owl", "Great Horned Owl"}
    got = set(bp.consolidate_owl_species({"Barred Owl": 0.9, "Great Horned Owl": 0.72}, 0.9, 0.7))
    assert got == {"Barred Owl", "Great Horned Owl"}


def test_run_birdnet_noise_no_owls(tmp_path):
    pytest.importorskip("birdnetlib")
    p = tmp_path / "quiet.wav"
    sf.write(p, noise(9.0, 0.001), SR, subtype="PCM_16")
    d = {}
    out = bp.run_birdnet(str(p), lat=42.28, lon=-71.35, when=datetime.date(2026, 6, 1),
                         min_conf=0.3, diag=d)
    assert not [x for x in out if bp.is_low_owl(x["common_name"])]
    assert d["windows"] == 16 and d["band_windows"] == 0
    assert isinstance(d["near_misses"], list)


def _owl_eval_dir():
    d = os.environ.get("CHIRP_OWL_EVAL_DIR", os.path.expanduser("~/.cache/chirp-owl-eval"))
    man = os.path.join(REPO, "scripts", "owl-eval", "manifest.json")
    if not os.path.exists(man):
        return None
    clips = json.load(open(man))["clips"]
    if not all(os.path.exists(os.path.join(d, f"XC{c['xc']}.wav")) for c in clips):
        return None
    return d


@pytest.mark.skipif(_owl_eval_dir() is None, reason="owl clip set not fetched")
def test_owl_regression():
    """Floors a little under what the tuned settings score (see
    scripts/owl-eval/README.md), so a change that makes owls worse fails."""
    sys.path.insert(0, os.path.join(REPO, "scripts", "owl-eval"))
    import owl_eval as oe
    man = json.load(open(os.path.join(REPO, "scripts", "owl-eval", "manifest.json")))
    d = _owl_eval_dir()
    cache = os.path.join(d, "cache")
    os.makedirs(cache, exist_ok=True)
    cached = [(n, lb, oe.build_cache(bp, n, ld, cache, 2.5, 1.5)) for n, lb, ld in oe.variants(man, d, None)]
    allow = bp.allowed_labels(man["location"]["lat"], man["location"]["lon"],
                              datetime.date.fromisoformat(man["date"]))
    params = {"strong": bp.STRONG_OWL_CONF, "owl_floor": bp.OWL_MIN_CONF, "hoot_full": bp.HOOT_FULL_MIN,
              "second_ratio": bp.SECOND_OWL_RATIO, "second_abs": bp.SECOND_OWL_MIN, "hoot": dict(bp.HOOT)}
    res, _ = oe.evaluate(bp, cached, allow, params)
    exp = man["expected"]
    assert res["hits"] >= exp["min_hits"], res
    assert res["wrong"] <= exp["max_wrong"], res
    assert res["false_alarms"] <= exp["max_false_alarms"], res
