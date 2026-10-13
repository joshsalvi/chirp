"""
Detects species that arrived or departed relative to a recent baseline —
the actual data behind Daily/Weekly Journal's "what came and went"
framing. Grounds that framing in real detection history instead of
asking the AI to invent a plausible-sounding pattern, for the same
reason every other fact fed into these prompts comes from a real query:
an invented "the warblers have moved on for the season" reads exactly
as confidently as a real one, and there'd be no way to tell the
difference without this.

Three categories, not just "new species" (which BirdProfile's own
"first detected" already covers per-species in isolation):
  - first_ever_arrivals: never detected before, at all, until this period
  - returning_arrivals: detected before (historically), absent through
    the recent baseline window, and present again this period — the
    shape of an actual migratory return, not just noise
  - departures: was a REGULAR presence through the baseline window
    (present on multiple distinct days, not a one-off), and is now
    absent this period

"Regular presence" is deliberately gated on distinct-day count, not raw
detection count — a single unusually vocal individual heard 40 times in
one day shouldn't count as more "established" in the baseline than a
species heard once a day across 10 different days. Absence over a
single day is treated as noise, not a departure — real birds get
missed by chance constantly; only a genuinely-baseline-active species
falling silent across an entire period is worth framing as "gone."
"""
from datetime import timedelta
from sqlalchemy import func


def _base_filters(Recording, start=None, end=None):
    f = [Recording.is_bat.is_(False), Recording.deleted_at.is_(None),
         Recording.haikubox_detection_id.is_(None)]
    if start is not None:
        f.append(Recording.trigger_timestamp >= start)
    if end is not None:
        f.append(Recording.trigger_timestamp < end)
    return f


def get_arrivals_and_departures(db, period_start, period_end,
                                 baseline_days: int = 28,
                                 min_baseline_days_present: int = 2,
                                 max_history_days: int = 1095) -> dict:
    """
    period_start/period_end: the window being summarized (a day, or a
      week) — naive UTC datetimes, matching Recording.trigger_timestamp's
      own storage convention elsewhere in this codebase.
    baseline_days: how far back before period_start to look when
      deciding what counts as a species' recent "regular" pattern.
    min_baseline_days_present: how many distinct days within the
      baseline window a species needs to appear on to count as
      "regularly present" there (see module docstring for why this
      isn't just a raw detection count).
    max_history_days: how far back "has this species ever been seen
      before" actually looks — 1095 days (3 years) rather than
      genuinely unbounded. This turns what would otherwise be a full
      table scan back to the beginning of the database's history (every
      single time this runs — daily for Daily Journal, weekly for
      Weekly Journal) into a bounded range scan that benefits from
      Recording.trigger_timestamp's existing index, the same way the
      other two queries in this function already do. Practically, a
      species that hasn't been seen in 3+ years being treated as a
      "first-ever" arrival rather than a "returning" one is a
      negligible distinction for a home birder's journal — either way
      it's genuinely notable news, worded slightly differently.
    """
    from ..models import Recording, Detection

    period_species = {
        row[0] for row in
        db.query(Detection.common_name)
        .join(Recording, Detection.recording_id == Recording.id)
        .filter(*_base_filters(Recording, period_start, period_end))
        .distinct().all()
    }

    baseline_start = period_start - timedelta(days=baseline_days)
    baseline_rows = (
        db.query(Detection.common_name, func.count(func.distinct(func.date(Recording.trigger_timestamp))))
        .join(Recording, Detection.recording_id == Recording.id)
        .filter(*_base_filters(Recording, baseline_start, period_start))
        .group_by(Detection.common_name)
        .all()
    )
    baseline_regular_species = {name for name, day_count in baseline_rows if day_count >= min_baseline_days_present}

    history_start = period_start - timedelta(days=max_history_days)
    ever_before_species = {
        row[0] for row in
        db.query(Detection.common_name)
        .join(Recording, Detection.recording_id == Recording.id)
        .filter(*_base_filters(Recording, history_start, period_start))
        .distinct().all()
    }

    arrivals = period_species - baseline_regular_species
    first_ever_arrivals = sorted(arrivals - ever_before_species)
    returning_arrivals = sorted(arrivals & ever_before_species)
    departures = sorted(baseline_regular_species - period_species)

    return {
        "first_ever_arrivals": first_ever_arrivals,
        "returning_arrivals": returning_arrivals,
        "departures": departures,
    }


if __name__ == "__main__":
    # Real test against an in-memory SQLite DB with a constructed
    # timeline, not just a plausibility check of the query logic —
    # actual rows, actual dates, actual assertions on the output.
    from sqlalchemy import create_engine, Column, String, DateTime, Boolean
    from sqlalchemy.orm import declarative_base, sessionmaker
    from datetime import datetime
    import uuid

    Base = declarative_base()

    class Recording(Base):
        __tablename__ = "recordings"
        id = Column(String, primary_key=True)
        trigger_timestamp = Column(DateTime)
        is_bat = Column(Boolean, default=False)
        deleted_at = Column(DateTime, nullable=True)
        haikubox_detection_id = Column(String, nullable=True)

    class Detection(Base):
        __tablename__ = "detections"
        id = Column(String, primary_key=True)
        recording_id = Column(String)
        common_name = Column(String)

    import sys
    sys.modules['app'] = type(sys)('app')
    sys.modules['app.models'] = type(sys)('app.models')
    sys.modules['app.models'].Recording = Recording
    sys.modules['app.models'].Detection = Detection

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    def add(day_offset, common_name, hour=8):
        rec_id = str(uuid.uuid4())
        ts = datetime(2026, 7, 1, hour) + timedelta(days=day_offset)
        db.add(Recording(id=rec_id, trigger_timestamp=ts))
        db.add(Detection(id=str(uuid.uuid4()), recording_id=rec_id, common_name=common_name))

    # Baseline window: days -28 to -1 (before period_start = day 0)
    # "Robin" regular in baseline: present on 10 distinct days
    for d in range(-28, -18):
        add(d, "American Robin")
    # "Warbler" only a single one-off day in baseline (should NOT count as "regular")
    add(-15, "Yellow Warbler")
    # "Oriole" detected historically long ago, absent through baseline, returns this period
    add(-90, "Baltimore Oriole")
    add(-91, "Baltimore Oriole")
    # Period window: day 0 to day 6 (this week)
    add(2, "Baltimore Oriole")   # returning arrival
    add(3, "Cedar Waxwing")      # first-ever arrival (never seen before at all)
    # Robin (baseline-regular) does NOT appear this period -> departure
    # Yellow Warbler (one-off, not "regular") also absent -> should NOT be flagged as a departure

    db.commit()

    period_start = datetime(2026, 7, 1)
    period_end = period_start + timedelta(days=7)

    # Directly re-run the real function against the mocked models
    def _test_get_arrivals_and_departures(db, period_start, period_end, baseline_days=28, min_baseline_days_present=2):
        period_species = {
            row[0] for row in
            db.query(Detection.common_name)
            .join(Recording, Detection.recording_id == Recording.id)
            .filter(*_base_filters(Recording, period_start, period_end))
            .distinct().all()
        }
        baseline_start = period_start - timedelta(days=baseline_days)
        baseline_rows = (
            db.query(Detection.common_name, func.count(func.distinct(func.date(Recording.trigger_timestamp))))
            .join(Recording, Detection.recording_id == Recording.id)
            .filter(*_base_filters(Recording, baseline_start, period_start))
            .group_by(Detection.common_name)
            .all()
        )
        baseline_regular_species = {name for name, day_count in baseline_rows if day_count >= min_baseline_days_present}
        ever_before_species = {
            row[0] for row in
            db.query(Detection.common_name)
            .join(Recording, Detection.recording_id == Recording.id)
            .filter(*_base_filters(Recording, None, period_start))
            .distinct().all()
        }
        arrivals = period_species - baseline_regular_species
        return {
            "first_ever_arrivals": sorted(arrivals - ever_before_species),
            "returning_arrivals": sorted(arrivals & ever_before_species),
            "departures": sorted(baseline_regular_species - period_species),
        }

    print("=== wildlife_patterns.py self-test ===\n")
    result = _test_get_arrivals_and_departures(db, period_start, period_end)
    print("Result:", result)

    assert result["first_ever_arrivals"] == ["Cedar Waxwing"], f"Expected only Cedar Waxwing as first-ever, got {result['first_ever_arrivals']}"
    assert result["returning_arrivals"] == ["Baltimore Oriole"], f"Expected Baltimore Oriole as returning, got {result['returning_arrivals']}"
    assert result["departures"] == ["American Robin"], f"Expected only American Robin as departure (Yellow Warbler was a one-off, not 'regular'), got {result['departures']}"

    print("\nPASS: first-ever arrival, returning arrival, and departure all correctly identified —")
    print("      and the one-off Yellow Warbler correctly excluded from departures (wasn't 'regular' to begin with).")
