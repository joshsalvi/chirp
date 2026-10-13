"""
Location filter keeps owls: birdnetlib's own filter (week score >= 0.03)
dropped Barred Owl in eastern Massachusetts in autumn (0.016).

    cd chirp-device && python3 -m pytest -q tests/test_location_filter.py
"""
import datetime
import os
import sys

import pytest

pytest.importorskip("birdnetlib")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from chirp.birdnet_cpu import allowed_labels, _week_48  # noqa: E402

NATICK = (42.28, -71.35)


def test_owls_kept_year_round():
    for month in (1, 4, 7, 10):
        a = allowed_labels(*NATICK, datetime.date(2026, month, 1))
        assert "Strix varia_Barred Owl" in a
        assert "Bubo virginianus_Great Horned Owl" in a


def test_out_of_range_species_still_dropped():
    a = allowed_labels(*NATICK, datetime.date(2026, 10, 1))
    assert "Strix occidentalis_Spotted Owl" not in a
    assert "Cardinalis cardinalis_Northern Cardinal" in a


def test_week_48():
    assert _week_48(datetime.date(2026, 1, 1)) == 1
    assert _week_48(datetime.date(2026, 12, 31)) == 48
