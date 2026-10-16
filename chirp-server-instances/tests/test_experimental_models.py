"""0.5.13.a: experimental models — BirdNET v3 (shadow / main) and Nighthawk
night flight calls. Real-model checks run only when the model files are
present (CHIRP_TEST_BN3_DIR, CHIRP_TEST_NFC_WAV); the rest use stand-ins."""
import datetime
import os
import sys
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))


def _db():
    from app.database import SessionLocal, init_db
    init_db()
    return SessionLocal()


def test_birdnet3_label_map_keeps_chirp_names():
    pytest.importorskip("birdnetlib")
    from app.services import birdnet3
    from app.services.birdnet_pass import labels
    known = set(labels())
    m = dict(l.split("\t", 1) for l in birdnet3.MAP_FILE.read_text().splitlines() if "\t" in l and not l.startswith("#"))
    assert m["Dumetella carolinensis_Grey Catbird"] == "Dumetella carolinensis_Gray Catbird"
    assert m["Astur cooperii_Cooper's Hawk"] == "Accipiter cooperii_Cooper's Hawk"
    assert m["Astur atricapillus_American Goshawk"] == "Accipiter gentilis_Northern Goshawk"
    assert m["Troglodytes aedon_Northern House Wren"] == "Troglodytes aedon_House Wren"
    assert all(v in known for v in m.values())
    assert len(m) > 6400
    assert not any(k.startswith(("Engine", "Dog", "Human")) for k in m)


@pytest.mark.skipif(not os.environ.get("CHIRP_TEST_BN3_DIR"), reason="BirdNET v3 model not available")
def test_birdnet3_real_model(tmp_path, monkeypatch):
    from app.config import settings
    from app.services import birdnet3
    monkeypatch.setattr(settings, "ai_models_dir", os.environ["CHIRP_TEST_BN3_DIR"])
    assert birdnet3.installed()
    wav = os.environ.get("CHIRP_TEST_BIRD_WAV")
    if not wav:
        pytest.skip("no test recording")
    dets = birdnet3.analyze(wav, lat=42.48, lon=-76.45, when=datetime.date(2017, 5, 13), min_conf=0.5)
    names = {d["common_name"] for d in dets}
    assert names and all("Grey" not in n for n in names)
    for d in dets:
        assert d["label"] == f"{d['scientific_name']}_{d['common_name']}"
        assert 0 <= d["start_time"] < d["end_time"]


def test_night_of_belongs_to_evening():
    from zoneinfo import ZoneInfo
    from app.services.nighthawk_service import night_of
    tz = ZoneInfo("America/New_York")
    assert night_of(datetime.datetime(2026, 9, 20, 6, 0), tz) == "2026-09-19"    # 2 am EDT
    assert night_of(datetime.datetime(2026, 9, 20, 1, 30), tz) == "2026-09-19"   # 9:30 pm EDT
    assert night_of(datetime.datetime(2026, 9, 20, 23, 0), tz) == "2026-09-20"   # 7 pm EDT next evening


def _fake_dets():
    return [
        {"start_sec": 2.0, "end_sec": 2.4, "order": "Passeriformes", "prob_order": 0.99, "family": "Parulidae",
         "prob_family": 0.97, "group": None, "prob_group": float("nan"), "species": "amered", "prob_species": 0.91,
         "predicted_category": "amered", "prob": 0.91},
        {"start_sec": 5.0, "end_sec": 5.3, "order": "Passeriformes", "prob_order": 0.98, "family": "Parulidae",
         "prob_family": 0.95, "group": "ZEEP", "prob_group": 0.88, "species": float("nan"), "prob_species": float("nan"),
         "predicted_category": "ZEEP", "prob": 0.88},
        {"start_sec": 7.0, "end_sec": 7.2, "order": "Passeriformes", "prob_order": 0.93, "family": float("nan"),
         "prob_family": float("nan"), "group": float("nan"), "prob_group": float("nan"), "species": float("nan"),
         "prob_species": float("nan"), "predicted_category": "Passeriformes", "prob": 0.93},
    ]


def test_night_upload_and_listing(tmp_path, monkeypatch):
    pytest.importorskip("pandas")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import night_calls
    from app.config import settings
    from app.models import AppSettings, FlightCall, NightChunk
    from app.services import nighthawk_service as nh
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(nh, "available", lambda: None)
    monkeypatch.setattr(nh, "detect", lambda path, threshold=80: _fake_dets())
    monkeypatch.setattr(nh, "taxonomy", lambda: {"species": {"amered": ("American Redstart", "Setophaga ruticilla", "Parulidae")},
                                                 "groups": {"ZEEP": ["Blackpoll Warbler", "Bay-breasted Warbler"]},
                                                 "families": {"Parulidae": "New World Warblers"}})
    db = _db()
    s = db.query(AppSettings).filter(AppSettings.id == 1).first() or AppSettings(id=1)
    s.device_api_keys = [{"id": "k1", "key": "night-key"}]
    s.timezone = "America/New_York"
    s.exp_nighthawk_enabled = False
    db.merge(s); db.commit()
    app = FastAPI()
    app.include_router(night_calls.router, prefix="/api/v1/night-calls")
    c = TestClient(app)
    wav = tmp_path / "chunk.flac"
    sf.write(str(wav), (np.random.default_rng(0).standard_normal(22050 * 10) * 0.01).astype(np.float32), 22050, format="FLAC")
    form = {"started_at": "2026-09-20T06:00:00Z", "duration_seconds": "10", "sample_rate": "22050", "device_serial": "pi"}
    files = lambda: {"file": ("c.flac", wav.read_bytes(), "audio/flac")}
    assert c.get("/api/v1/night-calls/accepting").status_code == 401
    acc = c.get("/api/v1/night-calls/accepting", headers={"X-API-Key": "night-key"}).json()
    assert acc["enabled"] is False and acc["timezone"] == "America/New_York" and acc["start"] == "21:00"
    assert c.post("/api/v1/night-calls/upload", data=form, files=files()).status_code == 401
    assert c.post("/api/v1/night-calls/upload", data=form, files=files(), headers={"X-API-Key": "night-key"}).status_code == 410
    s = db.query(AppSettings).filter(AppSettings.id == 1).first(); s.exp_nighthawk_enabled = True; db.commit()
    assert c.get("/api/v1/night-calls/accepting", headers={"X-API-Key": "night-key"}).json()["enabled"] is True
    r = c.post("/api/v1/night-calls/upload", data=form, files=files(), headers={"X-API-Key": "night-key"})
    assert r.status_code == 202, r.text
    cid = r.json()["chunk_id"]
    db.expire_all()
    ch = db.query(NightChunk).filter(NightChunk.id == cid).first()
    assert ch.status == "done" and ch.calls == 3 and ch.path is None
    assert not list((tmp_path / "night_audio").iterdir())           # chunk audio deleted
    listing = c.get("/api/v1/night-calls", params={"night": "2026-09-19"}).json()
    calls = listing["calls"]
    assert listing["unnarrowed"] == 1 and {x["level"] for x in calls} == {"species", "group"}   # "Songbird" hidden
    every = c.get("/api/v1/night-calls", params={"night": "2026-09-19", "include_unnarrowed": True}).json()["calls"]
    assert {x["name"] for x in every if x["level"] == "order"} == {"Songbird"}
    by = {x["level"]: x for x in calls}
    assert by["species"]["name"] == "American Redstart" and by["species"]["family_name"] == "New World Warblers"
    assert by["group"]["name"] == "Blackpoll or Bay-breasted Warbler" and by["group"]["level_label"] == "Sound-alike group"
    assert by["group"]["group_members"] == ["Blackpoll Warbler", "Bay-breasted Warbler"]
    import glob
    assert len(glob.glob(str(tmp_path / "night_calls" / "*.png"))) == 3                  # spectrograms made up front
    assert by["species"]["detected_at"].startswith("2026-09-20T06:00:02")
    nights = c.get("/api/v1/night-calls/nights").json()["nights"]
    assert nights[0]["night"] == "2026-09-19" and nights[0]["calls"] == 3
    assert nights[0]["by_level"] == {"species": 1, "group": 1, "order": 1}
    assert "Songbird" not in {t["name"] for t in nights[0]["top"]}
    a = c.get(f"/api/v1/night-calls/{by['species']['id']}/audio")
    assert a.status_code == 200 and a.headers["content-type"] == "audio/wav" and a.content[:4] == b"RIFF"
    assert c.get(f"/api/v1/night-calls/{by['species']['id']}/spectrogram").headers["content-type"] == "image/png"
    st = c.get("/api/v1/night-calls/status").json()
    assert st["nighthawk"]["enabled"] and st["nighthawk"]["calls"] >= 2
    assert c.delete(f"/api/v1/night-calls/{by['group']['id']}").json() == {"ok": True}
    db.query(FlightCall).delete(); db.query(NightChunk).delete(); db.commit(); db.close()


@pytest.mark.skipif(not os.environ.get("CHIRP_TEST_NFC_WAV"), reason="no flight-call recording")
def test_nighthawk_real_model():
    pytest.importorskip("nighthawk")
    from app.services import nighthawk_service as nh
    dets = nh.detect(os.environ["CHIRP_TEST_NFC_WAV"], 80)
    assert len(dets) > 10
    assert {"start_sec", "end_sec", "predicted_category", "prob"} <= set(dets[0])
    assert nh.taxonomy()["species"]["amered"][0] == "American Redstart"


def test_shadow_endpoint_compares_models():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import recordings
    from app.models import Detection, Recording, ShadowDetection
    db = _db()
    rid = "rec-shadow-test"
    db.query(ShadowDetection).filter(ShadowDetection.recording_id == rid).delete()
    db.query(Detection).filter(Detection.recording_id == rid).delete()
    db.query(Recording).filter(Recording.id == rid).delete(); db.commit()
    db.add(Recording(id=rid, filename="x.wav", wav_path="/nonexistent.wav", trigger_timestamp=datetime.datetime(2026, 6, 1),
                     duration_seconds=10, sample_rate=48000, channels=1, pre_roll_seconds=0, device_count=1,
                     processing_status="done"))
    db.add(Detection(recording_id=rid, common_name="Blue Jay", label="Cyanocitta cristata_Blue Jay", confidence=0.4,
                     source="server"))
    db.add(Detection(recording_id=rid, common_name="Barred Owl", label="Strix varia_Barred Owl", confidence=0.3,
                     source="server"))
    db.commit()
    app = FastAPI(); app.include_router(recordings.router, prefix="/api/v1/recordings")
    c = TestClient(app)
    r = c.get(f"/api/v1/recordings/{rid}/shadow").json()
    assert r["ran"] is False and r["species"] == []
    for st, conf in ((0, 0.81), (2.5, 0.92)):
        db.add(ShadowDetection(recording_id=rid, common_name="Blue Jay", scientific_name="Cyanocitta cristata",
                               confidence=conf, start_time=st, end_time=st + 5))
    db.add(ShadowDetection(recording_id=rid, common_name="Tufted Titmouse", confidence=0.66, start_time=5, end_time=10))
    db.commit()
    r = c.get(f"/api/v1/recordings/{rid}/shadow").json()
    assert r["ran"] is True
    assert [(x["common_name"], x["in_main"], x["windows"]) for x in r["species"]] == \
        [("Blue Jay", True, 2), ("Tufted Titmouse", False, 1)]
    assert r["species"][0]["confidence"] == pytest.approx(0.92)
    assert r["main_only"] == ["Barred Owl"]
    # deleting the recording removes its shadow rows
    rec = db.query(Recording).filter(Recording.id == rid).first()
    db.delete(rec); db.commit()
    assert db.query(ShadowDetection).filter(ShadowDetection.recording_id == rid).count() == 0
    db.close()


def test_experimental_settings_validation():
    from app.api.app_settings import SettingsIn, _MIGRATION_DEFAULTS
    names = dict(_MIGRATION_DEFAULTS)
    assert names["exp_birdnet3_min_conf"] == 0.5 and names["exp_nighthawk_start"] == "21:00"
    assert "detection_model" in SettingsIn.model_fields


@pytest.mark.skipif(not (os.environ.get("CHIRP_TEST_BN3_DIR") and os.environ.get("CHIRP_TEST_BIRD_WAV")),
                    reason="BirdNET v3 model or test recording not available")
def test_server_pass_shadow_then_main(monkeypatch, tmp_path):
    pytest.importorskip("birdnetlib")
    from app.config import settings
    from app.api.recordings import _run_server_birdnet
    from app.models import AppSettings, Detection, Recording, ShadowDetection
    monkeypatch.setattr(settings, "ai_models_dir", os.environ["CHIRP_TEST_BN3_DIR"])
    db = _db()
    rid = "rec-bn3-pass"
    db.query(ShadowDetection).filter(ShadowDetection.recording_id == rid).delete()
    db.query(Detection).filter(Detection.recording_id == rid).delete()
    db.query(Recording).filter(Recording.id == rid).delete(); db.commit()
    import shutil
    wav = str(tmp_path / "b.wav")          # a copy: recording cleanup deletes its file
    shutil.copy(os.environ["CHIRP_TEST_BIRD_WAV"], wav)
    db.add(Recording(id=rid, filename="b.wav", wav_path=wav,
                     trigger_timestamp=datetime.datetime(2017, 5, 13, 12), latitude=42.48, longitude=-76.45,
                     duration_seconds=60, sample_rate=32000, channels=1, pre_roll_seconds=0, device_count=1,
                     processing_status="done"))
    s = db.query(AppSettings).filter(AppSettings.id == 1).first() or AppSettings(id=1)
    s.exp_birdnet3_shadow, s.detection_model, s.exp_birdnet3_min_conf = True, "birdnet24", 0.5
    db.merge(s); db.commit()
    n24 = _run_server_birdnet(rid, db)
    db.expire_all()
    shadow = db.query(ShadowDetection).filter(ShadowDetection.recording_id == rid).all()
    rec = db.query(Recording).filter(Recording.id == rid).first()
    assert rec.shadow_checked_at is not None and shadow
    main_names = {d.common_name for d in rec.detections}
    assert n24 == len(rec.detections)
    # main mode: the detections now come from BirdNET v3, in Chirp's names
    s = db.query(AppSettings).filter(AppSettings.id == 1).first(); s.detection_model = "birdnet3"; db.commit()
    n3 = _run_server_birdnet(rid, db)
    db.expire_all()
    rec = db.query(Recording).filter(Recording.id == rid).first()
    assert n3 == len(rec.detections) and n3 == len(shadow)
    assert {d.common_name for d in rec.detections} == {x.common_name for x in shadow}
    assert all(d.confidence >= 0.5 and d.source == "server" for d in rec.detections)
    print("BirdNET 2.4:", sorted(main_names), "| BirdNET v3:", sorted({d.common_name for d in rec.detections}))
    s = db.query(AppSettings).filter(AppSettings.id == 1).first(); s.detection_model, s.exp_birdnet3_shadow = "birdnet3", False
    db.delete(db.query(Recording).filter(Recording.id == rid).first())   # other tests count old recordings
    db.commit(); db.close()



@pytest.mark.skipif(not os.environ.get("CHIRP_TEST_BN3_DIR") or not os.environ.get("CHIRP_TEST_BIRD_WAV"),
                    reason="BirdNET v3 model not available")
def test_reanalyze_uses_birdnet3(monkeypatch, tmp_path):
    """Reanalyze (_process_manual_upload) runs the comparison pass, and
    BirdNET v3 itself in main mode."""
    pytest.importorskip("birdnetlib")
    import shutil
    from app.config import settings
    from app.api.recordings import _process_manual_upload
    from app.models import AppSettings, Detection, ReanalysisRun, Recording, ShadowDetection
    monkeypatch.setattr(settings, "ai_models_dir", os.environ["CHIRP_TEST_BN3_DIR"])
    db = _db()
    rid = "rec-bn3-reanalyze"
    for M in (ShadowDetection, Detection, ReanalysisRun):
        db.query(M).filter(M.recording_id == rid).delete()
    db.query(Recording).filter(Recording.id == rid).delete(); db.commit()
    wav = str(tmp_path / "r.wav")
    shutil.copy(os.environ["CHIRP_TEST_BIRD_WAV"], wav)
    db.add(Recording(id=rid, filename="r.wav", wav_path=wav,
                     trigger_timestamp=datetime.datetime(2017, 5, 13, 12), latitude=42.48, longitude=-76.45,
                     duration_seconds=60, sample_rate=32000, channels=1, pre_roll_seconds=0, device_count=1,
                     processing_status="pending"))
    s = db.query(AppSettings).filter(AppSettings.id == 1).first() or AppSettings(id=1)
    s.exp_birdnet3_shadow, s.detection_model, s.exp_birdnet3_min_conf = True, "birdnet24", 0.5
    db.merge(s); db.commit()

    _process_manual_upload(rid)                                     # compare mode
    db.expire_all()
    rec = db.query(Recording).filter(Recording.id == rid).first()
    shadow = db.query(ShadowDetection).filter(ShadowDetection.recording_id == rid).all()
    assert rec.shadow_checked_at is not None and shadow
    n24 = len(rec.detections)

    s = db.query(AppSettings).filter(AppSettings.id == 1).first(); s.detection_model = "birdnet3"; db.commit()
    run = ReanalysisRun(recording_id=rid, before=[]); db.add(run); db.commit()
    db.query(Detection).filter(Detection.recording_id == rid, Detection.source == "server").delete(); db.commit()
    _process_manual_upload(rid, run_id=run.id)                      # main mode
    db.expire_all()
    rec = db.query(Recording).filter(Recording.id == rid).first()
    names = {d.common_name for d in rec.detections if d.source == "server"}
    assert names == {x.common_name for x in shadow}
    assert all(d.confidence >= 0.5 for d in rec.detections if d.source == "server")
    assert "BirdNET v3" in (db.query(ReanalysisRun).filter(ReanalysisRun.id == run.id).first().summary or "")
    print("reanalyze BirdNET 2.4:", n24, "| BirdNET v3:", sorted(names))
    s = db.query(AppSettings).filter(AppSettings.id == 1).first(); s.detection_model, s.exp_birdnet3_shadow = "birdnet3", False
    db.delete(db.query(Recording).filter(Recording.id == rid).first())
    db.commit(); db.close()

def test_nighthawk_display_names():
    nh = pytest.importorskip("app.services.nighthawk_service")
    try:
        nh.taxonomy()
    except Exception:
        pytest.skip("nighthawk not installed")
    assert nh.display_name("family", "Parulidae", family="Parulidae") == "New World Warblers"
    assert nh.display_name("group", "ZEEP") == "Warbler, one of 13"
    assert nh.display_name("group", "SWLI") == "Swamp or Lincoln's Sparrow"
    assert nh.display_name("group", "GCBI") == "Gray-cheeked or Bicknell's Thrush"
    assert nh.display_name("species", "swathr", "Swainson's Thrush") == "Swainson's Thrush"
    assert nh.display_name("order", "Passeriformes", order="Passeriformes") == "Songbird"
