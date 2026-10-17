"""0.5.14: BirdNET v3 is the default model (2.4 selectable) with the owl
check; night calls list by date range, have their own page and a large
spectrogram."""
import datetime as dt
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LAT, LON = 40.7, -74.0
NIGHT = dt.datetime(2026, 10, 15, 3, 0)    # 11 pm EDT
DAY = dt.datetime(2026, 10, 15, 17, 0)     # 1 pm EDT


def _wav(tmp_path, hoot: bool) -> str:
    sr = 48000
    t = np.arange(int(sr * 9.0)) / sr
    y = 0.002 * np.random.default_rng(0).standard_normal(len(t))
    if hoot:
        for a in (0.5, 1.5, 2.3):                       # three 0.5 s hoots at 330 Hz
            m = (t >= a) & (t < a + 0.5)
            y[m] += 0.3 * np.sin(2 * np.pi * 330 * t[m])
    p = str(tmp_path / ("hoot.wav" if hoot else "quiet.wav"))
    sf.write(p, y.astype(np.float32), sr)
    return p


def _det(name, conf, sci="Bubo virginianus"):
    return {"common_name": name, "scientific_name": sci, "confidence": conf, "start_time": 0.0, "end_time": 3.0}


def test_sun_altitude_day_and_night():
    from app.services.birdnet_pass import sun_altitude
    assert sun_altitude(LAT, LON, DAY) > 20
    assert sun_altitude(LAT, LON, NIGHT) < -20


def test_owl_check(tmp_path):
    from app.services.birdnet3 import owl_check
    hoot, quiet = _wav(tmp_path, True), _wav(tmp_path, False)
    robin = _det("American Robin", 0.9, "Turdus migratorius")

    diag = {}
    out = owl_check([_det("Great Horned Owl", 0.6), robin], hoot, lat=LAT, lon=LON, start_utc=NIGHT, diag=diag)
    assert {d["common_name"] for d in out} == {"Great Horned Owl", "American Robin"}, diag

    diag = {}
    out = owl_check([_det("Great Horned Owl", 0.6), robin], hoot, lat=LAT, lon=LON, start_utc=DAY, diag=diag)
    assert [d["common_name"] for d in out] == ["American Robin"]
    assert diag["owls_dropped"]["Great Horned Owl"] == "daylight"

    out = owl_check([_det("Great Horned Owl", 0.9)], hoot, lat=LAT, lon=LON, start_utc=DAY)
    assert [d["common_name"] for d in out] == ["Great Horned Owl"]

    diag = {}
    out = owl_check([_det("Great Horned Owl", 0.9), robin], quiet, lat=LAT, lon=LON, start_utc=NIGHT, diag=diag)
    assert [d["common_name"] for d in out] == ["American Robin"]
    assert diag["owls_dropped"]["Great Horned Owl"] == "no hoot at its pitch"


def test_detection_model_setting():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import app_settings, recordings
    from app.database import SessionLocal, init_db
    from app.models import AppSettings
    init_db()
    db = SessionLocal()
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    assert recordings._bn3_main(s) == (getattr(s, "detection_model", None) in (None, "", "birdnet3"))
    assert recordings._bn3_main(type("S", (), {"detection_model": None})()) is True
    assert recordings._bn3_main(type("S", (), {"detection_model": "birdnet24"})()) is False
    db.close()
    app = FastAPI(); app.include_router(app_settings.router, prefix="/api/v1/settings")
    c = TestClient(app)
    r = c.put("/api/v1/settings", json={"detection_model": "birdnet9"})
    assert r.status_code == 422, r.text


def test_night_calls_range_detail_spectrogram(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import night_calls
    from app.database import SessionLocal, init_db
    from app.models import FlightCall
    init_db()
    db = SessionLocal()
    db.query(FlightCall).filter(FlightCall.id.like("nct-%")).delete(synchronize_session=False)
    clip = str(tmp_path / "c.wav")
    sr = 22050; t = np.arange(int(sr * 1.0)) / sr
    sf.write(clip, (0.2 * np.sin(2 * np.pi * 6000 * t)).astype(np.float32), sr)
    for i, night in enumerate(["2026-09-28", "2026-10-01", "2026-10-05"]):
        db.add(FlightCall(id=f"nct-{i}", detected_at=dt.datetime(2026, 10, 1, 4, i), night=night, level="family",
                          category="Parulidae", family="Parulidae", prob=0.8, duration=0.1, clip_path=clip))
    db.add(FlightCall(id="nct-o", detected_at=dt.datetime(2026, 10, 1, 5), night="2026-10-01", level="order",
                      category="Passeriformes", order="Passeriformes", prob=0.7))
    db.commit(); db.close()
    app = FastAPI(); app.include_router(night_calls.router, prefix="/api/v1/night-calls")
    c = TestClient(app)

    r = c.get("/api/v1/night-calls", params={"start": "2026-09-29", "end": "2026-10-05"}).json()
    ids = {x["id"] for x in r["calls"] if x["id"].startswith("nct-")}
    assert ids == {"nct-1", "nct-2"}
    assert r["unnarrowed"] >= 1
    r = c.get("/api/v1/night-calls", params={"start": "2026-09-01", "end": "2026-10-31", "include_unnarrowed": True}).json()
    assert {"nct-0", "nct-1", "nct-2", "nct-o"} <= {x["id"] for x in r["calls"]}

    one = c.get("/api/v1/night-calls/nct-1").json()
    assert one["night"] == "2026-10-01" and one["has_clip"] and one["level"] == "family"
    assert c.get("/api/v1/night-calls/nope").status_code == 404

    small = c.get("/api/v1/night-calls/nct-1/spectrogram")
    large = c.get("/api/v1/night-calls/nct-1/spectrogram", params={"large": True})
    assert small.status_code == large.status_code == 200
    assert large.content[:4] == b"\x89PNG" and len(large.content) > len(small.content)
    assert os.path.exists(str(tmp_path / "c_large.png"))

    db = SessionLocal()
    db.query(FlightCall).filter(FlightCall.id.like("nct-%")).delete(synchronize_session=False)
    db.commit(); db.close()


def test_second_opinion_overall_rating():
    from app.services.call_reanalysis import overall_rating, _apply_measured_check, _parse_verdict
    raw = ("CONSISTENT\n**Red-winged Blackbird:** the calls fit.\n\n"
           "**Overall:** The evidence strongly supports Red-winged Blackbird.")
    stored = _apply_measured_check(raw, "Red-winged Blackbird", None,
                                   ["no sound in its boxes stands out from the background noise (measured)"])
    v, note = _parse_verdict(stored)
    r = overall_rating(note, v, "Red-winged Blackbird")
    assert v == "uncertain" and r["level"] == "uncertain"
    assert "doesn't back it up" in r["summary"]
    assert r["checks"] == ["Nothing in its boxes is louder than the background noise."]
    assert overall_rating("**Blue Jay:** fits.", "consistent", "Blue Jay")["level"] == "likely"
    faint = "x\n\n**Audio check for Blue Jay:** The call is faint, only 6 dB louder than the background."
    assert overall_rating(faint, "consistent")["level"] == "probably"
    assert overall_rating("x", "inconsistent", "Blue Jay")["label"] == "Likely wrong"
    assert overall_rating("x", None) is None


def test_empty_v3_pass_drops_station_detections():
    """Station (BirdNET 2.4) found a 38% Mourning Dove; v3 found nothing at
    its 50% minimum: the station's detection goes. With 2.4 it stays."""
    import datetime as dt
    from app.api.recordings import _drop_superseded_device_detections
    from app.database import SessionLocal, init_db
    from app.models import AppSettings, Detection, Recording
    init_db()
    db = SessionLocal()
    s = db.query(AppSettings).filter(AppSettings.id == 1).first() or AppSettings(id=1)
    s.server_reanalyze_delete_device = True
    db.merge(s); db.commit()
    for rid in ("v3e-a", "v3e-b"):
        db.query(Detection).filter(Detection.recording_id == rid).delete()
        db.query(Recording).filter(Recording.id == rid).delete()
        db.add(Recording(id=rid, filename=rid, wav_path="", trigger_timestamp=dt.datetime(2026, 10, 17, 12, 47), duration_seconds=35))
        db.add(Detection(recording_id=rid, common_name="Mourning Dove", scientific_name="Zenaida macroura",
                         label="Zenaida macroura_Mourning Dove", confidence=0.379, start_time=0, end_time=3, source="device"))
    db.commit()
    _drop_superseded_device_detections(db, "v3e-a", [], v3=True)
    _drop_superseded_device_detections(db, "v3e-b", [], v3=False)
    left = {r for (r,) in db.query(Detection.recording_id).filter(Detection.recording_id.in_(["v3e-a", "v3e-b"]))}
    assert left == {"v3e-b"}
    # a night caller the station heard isn't kept either, when v3 found something else
    db.add(Detection(recording_id="v3e-a", common_name="Common Nighthawk", scientific_name="Chordeiles minor",
                     label="Chordeiles minor_Common Nighthawk", confidence=0.35, start_time=0, end_time=3, source="device"))
    db.commit()
    _drop_superseded_device_detections(db, "v3e-a", [{"common_name": "Common Grackle"}], v3=True)
    assert db.query(Detection).filter(Detection.recording_id == "v3e-a").count() == 0
    for rid in ("v3e-a", "v3e-b"):
        db.query(Detection).filter(Detection.recording_id == rid).delete()
        db.query(Recording).filter(Recording.id == rid).delete()
    db.commit(); db.close()


def test_short_calls_measured(tmp_path):
    """Short faint chips (25 ms at 7 kHz) in hiss register as a band, and a
    stretch without them doesn't."""
    from app.services.audio_processor import measure_detection_bands
    sr = 48000
    rng = np.random.default_rng(5)
    y = 0.01 * rng.standard_normal(sr * 20)
    t = np.arange(int(sr * 0.025)) / sr
    chip = 0.02 * np.sin(2 * np.pi * 7000 * t) * np.hanning(len(t))
    for s in np.arange(1.0, 9.0, 0.7):
        i = int(s * sr); y[i:i + len(chip)] += chip
    p = str(tmp_path / "chips.wav"); sf.write(p, y.astype(np.float32), sr)
    calls, quiet = measure_detection_bands(p, [(0, 10), (12, 18)])
    assert calls and 6500 <= calls["peak_hz"] <= 7500 and calls["excess_db"] >= 8
    assert quiet is None
