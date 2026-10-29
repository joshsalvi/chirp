"""The Dashboard's latest recording skips clips that can vanish or show nothing."""
import datetime as dt
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_latest_recording_shows_a_bird():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import AppSettings, Base, Detection, Recording
    from app.api import recordings as R
    from app.cache import statistics_cache

    eng = create_engine(f"sqlite:///{tempfile.mkdtemp()}/t.db")
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    db.add(AppSettings(id=1, min_confidence_display=0.3))
    now = dt.datetime.utcnow()

    def rec(rid, minutes_ago, conf=None, **kw):
        db.add(Recording(id=rid, filename=rid, wav_path="/x", duration_seconds=3.0,
                         trigger_timestamp=now - dt.timedelta(minutes=minutes_ago),
                         processing_status=kw.pop("status", "done"), **kw))
        if conf is not None:
            db.add(Detection(recording_id=rid, common_name="Blue Jay", scientific_name="Cyanocitta cristata",
                             label="Blue Jay", confidence=conf))

    rec("bird", 10, 0.9)
    rec("live-clip", 1, 0.9, is_live_detect_clip=True)
    rec("faint", 2, 0.1)
    rec("empty", 3)
    rec("processing", 4, 0.9, status="processing")
    db.commit()
    statistics_cache.clear()
    out = R.recording_stats(period="24h", db=db)
    assert out["latest_recording_id"] == "bird"
