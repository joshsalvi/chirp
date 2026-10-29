"""Streak dates from the hour-bucket query match the per-row conversion,
including detections near local midnight and across DST changes."""
import datetime as dt
import os
import sys
import tempfile
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _per_row(rows, tz):
    out = {}
    for name, ts in rows:
        out.setdefault(name, set()).add(ts.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz).date())
    return out


def test_hour_buckets_match_per_row_dates():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base, Detection, Recording
    from app.api.recordings import _species_local_dates

    eng = create_engine(f"sqlite:///{tempfile.mkdtemp()}/t.db")
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    tz = ZoneInfo("America/New_York")
    stamps = [dt.datetime(2026, 3, 8, h, m) for h in (3, 4, 6, 7) for m in (0, 59)]      # DST starts
    stamps += [dt.datetime(2026, 11, 1, h, m) for h in (4, 5, 6) for m in (0, 30, 59)]   # DST ends
    stamps += [dt.datetime(2026, 6, d, 3, 59) for d in range(1, 20)]                     # 11:59 pm local
    stamps += [dt.datetime(2026, 6, d, 4, 0) for d in range(1, 20)]                      # midnight local
    rows = []
    for i, ts in enumerate(stamps):
        name = ("Blue Jay", "Barred Owl", "Downy Woodpecker")[i % 3]
        db.add(Recording(id=f"r{i}", filename=f"r{i}.wav", wav_path="/x", trigger_timestamp=ts, duration_seconds=3.0, is_bat=False))
        db.add(Detection(recording_id=f"r{i}", common_name=name, scientific_name=name, label=name, confidence=0.9))
        rows.append((name, ts))
    db.commit()
    base = [Recording.is_bat.is_(False), Recording.deleted_at.is_(None)]
    assert _species_local_dates(db, base, 0.0, tz) == _per_row(rows, tz)
    since = dt.datetime(2026, 6, 10)
    assert _species_local_dates(db, base, 0.0, tz, since=since) == _per_row([r for r in rows if r[1] >= since], tz)
    # A half-hour zone takes the per-row path and still matches.
    kol = ZoneInfo("Asia/Kolkata")
    assert _species_local_dates(db, base, 0.0, kol) == _per_row(rows, kol)
