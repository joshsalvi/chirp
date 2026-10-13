"""Owl noise rules (0.5.12.m): a hooted owl on the band-limited copy needs
full-band support, and device owls stay only when the server pass found
that owl too."""
import uuid
from datetime import datetime

import numpy as np

import tests.test_notifications_inbox  # noqa: F401  (pywebpush stub on bare machines)
from app.services import birdnet_pass as bp


def _decide(full_score, low_score, pitch=300.0):
    names = ["Great Horned Owl"]
    labs = ["Bubo virginianus_Great Horned Owl"]
    full = np.array([[full_score]])
    low = {0: np.array([low_score])}
    events = [(0.2, 1.0, pitch)]
    dets, _strong, _nh = bp.decide_owls(full, low, [0.0], np.array([0]), names, labs, events,
                                        lambda _n: bp.OWL_MIN_CONF, 0.05)
    return dets


def test_hooted_owl_needs_full_band_support():
    assert not _decide(0.10, 0.55), "band-only owl with a weak full band is noise"
    assert _decide(bp.HOOT_FULL_MIN, 0.55), "full-band support keeps a hooted owl"
    assert not _decide(0.40, 0.55, pitch=900.0), "hoot outside the owl's pitch"


def test_strong_owl_threshold():
    assert _decide(bp.STRONG_OWL_CONF, bp.STRONG_OWL_CONF * 0.6, pitch=5000.0)
    assert not _decide(bp.STRONG_OWL_CONF - 0.02, 0.1, pitch=5000.0)


def _rec_with(db, dets):
    from app.models import Detection, Recording
    r = Recording(id=str(uuid.uuid4()), filename="x.wav", wav_path="/x.wav",
                  trigger_timestamp=datetime(2026, 10, 10, 15, 0), duration_seconds=30,
                  sample_rate=48000, channels=1, processing_status="done")
    db.add(r)
    db.flush()
    for name, src, conf in dets:
        db.add(Detection(recording_id=r.id, common_name=name, scientific_name="x", label=f"x_{name}",
                         confidence=conf, start_time=0, end_time=3, source=src))
    db.commit()
    return r.id


def test_device_owls_need_server_confirmation():
    from app.api.recordings import _drop_superseded_device_detections
    from app.database import SessionLocal, init_db
    from app.models import AppSettings, Detection
    init_db()
    db = SessionLocal()
    try:
        s = db.query(AppSettings).filter(AppSettings.id == 1).first() or AppSettings(id=1)
        s.server_reanalyze_delete_device = True
        db.add(s)
        db.commit()

        def left(rid):
            return sorted((d.common_name, d.source) for d in
                          db.query(Detection).filter(Detection.recording_id == rid).all())

        # Server found nothing: device owl goes, device songbird stays.
        rid = _rec_with(db, [("Northern Saw-whet Owl", "device", 0.45), ("Blue Jay", "device", 0.6)])
        _drop_superseded_device_detections(db, rid, [])
        assert left(rid) == [("Blue Jay", "device")]

        # Server found a Blue Jay only: device owl goes (unconfirmed), device
        # nightjar it didn't reproduce stays, device Blue Jay is superseded.
        rid = _rec_with(db, [("Great Horned Owl", "device", 0.5), ("Eastern Whip-poor-will", "device", 0.5),
                             ("Blue Jay", "device", 0.6)])
        _drop_superseded_device_detections(db, rid, [{"common_name": "Blue Jay"}])
        assert left(rid) == [("Eastern Whip-poor-will", "device")]

        # Setting off: nothing is touched.
        s.server_reanalyze_delete_device = False
        db.commit()
        rid = _rec_with(db, [("Barred Owl", "device", 0.5)])
        _drop_superseded_device_detections(db, rid, [])
        assert left(rid) == [("Barred Owl", "device")]
    finally:
        db.close()
