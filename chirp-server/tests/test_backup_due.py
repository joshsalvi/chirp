from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.backup_service import is_due

NY = ZoneInfo("America/New_York")


def at(h, m=0, day=31):
    return datetime(2026, 10, day, h, m, tzinfo=NY)


def utc_naive(local):
    return local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def test_waits_for_the_hour():
    assert not is_due(at(0, 59), 1, None)


def test_runs_any_minute_after_the_hour_not_only_at_00():
    assert is_due(at(1, 7), 1, utc_naive(at(1, 0, day=30)))
    assert is_due(at(4, 30), 1, utc_naive(at(1, 0, day=26)))   # catches up after missed days


def test_once_per_day():
    assert not is_due(at(1, 5), 1, utc_naive(at(1, 2)))
    assert not is_due(at(23, 0), 1, utc_naive(at(1, 2)))


def test_manual_run_before_the_hour_does_not_skip_it():
    assert is_due(at(1, 1), 1, utc_naive(at(0, 30)))
