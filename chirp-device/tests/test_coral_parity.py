"""
Coral backend scores and filters like the CPU backend: birdnetlib's
sensitivity mapping, the night-caller floor and the location filter.

    cd chirp-device && python3 -m pytest -q tests/test_coral_parity.py
"""
import datetime
import os
import sys

import numpy as np
import pytest

pytest.importorskip("birdnetlib")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from chirp.birdnet_coral import BirdNetCoral  # noqa: E402

LABELS = ["Strix varia_Barred Owl", "Cyanocitta cristata_Blue Jay",
          "Strix occidentalis_Spotted Owl", "Turdus migratorius_American Robin"]


class _Interp:
    def __init__(self, logits):
        self.logits = np.array([logits], dtype=np.float32)

    def set_tensor(self, *a):
        pass

    def invoke(self):
        pass

    def get_tensor(self, idx):
        return self.logits


def _coral(logits, **bn):
    cfg = {"detection": {"birdnet": {"min_confidence": 0.25, "sensitivity": 1.5,
                                     "latitude": 42.28, "longitude": -71.35, **bn}},
           "audio": {"sample_rate": 48000}}
    c = BirdNetCoral(cfg)
    c._interpreter = _Interp(logits)
    c._input_details = [{"shape": [1, 144000], "index": 0}]
    c._output_details = [{"index": 0}]
    c._labels = LABELS
    c._ready = True
    return c


def _names(c, when=datetime.datetime(2026, 10, 1, 0, 12)):
    return {d.common_name: round(d.confidence, 3) for d in c.analyze(np.zeros(144000, np.float32), when)}


def test_sensitivity_matches_birdnetlib():
    # logit -2 at sensitivity 1.5 -> slope 0.5 -> 0.269 (was 0.047 with slope 1.5)
    out = _names(_coral([-2.0, -2.0, -9, -9], latitude=None, longitude=None, min_confidence=0.2))
    assert out == {"Barred Owl": 0.269, "Blue Jay": 0.269}


def test_owl_floor_and_location_filter():
    # Barred Owl at 0.15 passes on the night floor; Blue Jay at 0.15 doesn't;
    # Spotted Owl isn't expected in Massachusetts; Robin passes min_conf.
    lg = float(np.log(0.15 / 0.85) / 0.5)
    hi = float(np.log(0.6 / 0.4) / 0.5)
    out = _names(_coral([lg, lg, hi, hi]))
    assert set(out) == {"Barred Owl", "American Robin"}
