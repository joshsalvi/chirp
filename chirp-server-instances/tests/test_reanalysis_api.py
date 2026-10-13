"""
Re-analysis history and Undo, near misses, visible-detection counts, and
the SSH WebSocket's sign-in check, through the API with a throwaway data
directory.

    cd chirp-server && python3 -m pytest -q tests/test_reanalysis_api.py
"""
import os

import numpy as np
import pytest
import soundfile as sf

pytest.importorskip("birdnetlib")
HERE = os.path.dirname(os.path.abspath(__file__))


T = os.environ["CHIRP_DATA_DIR"]   # set by conftest.py


def test_visible_counts_and_top_species(client):
    d = client.get("/api/v1/recordings/rec-hidden").json()
    assert d["detections"] == [] and d["top_species"] is None and d["max_confidence"] == 0
    assert d["hidden_detections"][0]["common_name"] == "Blue Jay"
    c = client.get("/api/v1/settings/empty-recordings-count").json()
    # rec-hidden and rec-owl show nothing (rec-owl's Barred Owl is a 0.12
    # device row; only an owl the server kept at 0.20+ protects).
    assert c["no_detections"] == 2


def test_night_caller_protection(client):
    from app.api.recordings import _night_caller_protects
    assert _night_caller_protects("Barred Owl", 0.25, "server")          # owl kept by the owl rules
    assert not _night_caller_protects("Barred Owl", 0.15, "server")      # under OWL_MIN_CONF
    assert not _night_caller_protects("Common Nighthawk", 0.18, "server")
    assert not _night_caller_protects("Barred Owl", 0.60, "device")
    assert not _night_caller_protects("Blue Jay", 0.90, "server")


def test_auto_purge_sweep(client):
    import datetime as _dt
    from app.database import SessionLocal
    from app.models import AppSettings, Detection, Recording
    from app.api.app_settings import sweep_empty_recordings
    db = SessionLocal()
    old = _dt.datetime.utcnow() - _dt.timedelta(hours=1)
    wav = db.query(Recording).filter(Recording.id == "rec-a").first().wav_path
    import shutil

    def rec(rid, device="dev1", **kw):
        path = os.path.join(T, "recordings_dir", f"{rid}.wav")
        shutil.copy(wav, path)   # the purge deletes the file
        db.add(Recording(id=rid, filename=f"{rid}.wav", wav_path=path, trigger_timestamp=old, created_at=old,
                         duration_seconds=12, sample_rate=48000, channels=1, pre_roll_seconds=5,
                         device_count=1, processing_status="done", device_id=device, **kw))
    rec("sw-night"); rec("sw-owl"); rec("sw-manual", device=None); rec("sw-noted", notes="keep")
    db.add(Detection(recording_id="sw-night", common_name="Common Nighthawk", label="x_Common Nighthawk",
                     confidence=0.12, source="server"))  # under the 0.15 display threshold
    db.add(Detection(recording_id="sw-owl", common_name="Barred Owl", label="Strix varia_Barred Owl",
                     confidence=0.26, source="server"))
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    s.auto_purge_empty_recordings, s.auto_purge_all_device = True, True
    db.commit()
    try:
        sweep_empty_recordings(db)
        left = {r.id for r in db.query(Recording).filter(Recording.id.like("sw-%")).all()}
        assert left == {"sw-owl", "sw-manual", "sw-noted"}
        assert db.query(Recording).filter(Recording.id == "rec-a").first() is not None  # shows Blue Jay
    finally:
        s.auto_purge_empty_recordings = False
        for r in db.query(Recording).filter(Recording.id.like("sw-%")).all():
            db.delete(r)
        db.commit()
        db.close()


def test_batched_delete_and_file_cleanup(client):
    """Deletes go in small committed batches with files removed after each
    commit, so other writers get the lock in between (0.5.10.j)."""
    import datetime as _dt
    import shutil
    import threading
    import time
    from app.config import settings
    from app.database import SessionLocal
    from app.models import Detection, Recording
    from app.api import app_settings as aps
    db = SessionLocal()
    wav = db.query(Recording).filter(Recording.id == "rec-a").first().wav_path
    old = _dt.datetime.utcnow() - _dt.timedelta(hours=1)
    os.makedirs(settings.spectrograms_dir, exist_ok=True)
    ids = [f"bd-{i:02d}" for i in range(45)]
    for rid in ids:
        path = os.path.join(T, "recordings_dir", f"{rid}.wav")
        shutil.copy(wav, path)
        for suffix in ("0", "35_thumb2", "35_dark"):
            open(os.path.join(settings.spectrograms_dir, f"{rid}_spectrogram_{suffix}.png"), "wb").write(b"x")
        clip = os.path.join(T, f"{rid}_clip.wav")
        open(clip, "wb").write(b"x")
        db.add(Recording(id=rid, filename=f"{rid}.wav", wav_path=path, trigger_timestamp=old, created_at=old,
                         duration_seconds=12, sample_rate=48000, channels=1, pre_roll_seconds=5,
                         device_count=1, processing_status="done", device_id="dev1"))
        db.add(Detection(recording_id=rid, common_name="Blue Jay", label="x_Blue Jay", confidence=0.1,
                         source="server", clip_path=clip))
    # a neighbour whose id shares a prefix must keep its spectrogram
    keep = os.path.join(settings.spectrograms_dir, "bd-001_spectrogram_0.png")
    open(keep, "wb").write(b"x")
    db.commit()

    # Another writer during the delete: must not wait for the whole job.
    waits = []

    import app.services.file_cleanup as fc
    orig = fc.remove_files

    def slow_remove(job):
        time.sleep(0.2)   # files are slow; the lock must already be free
        return orig(job)

    fc.remove_files = slow_remove

    def writer():
        w = SessionLocal()
        t0 = time.time()
        r = w.query(Recording).filter(Recording.id == "rec-a").first()
        r.notes = "written during delete"
        w.commit()
        waits.append(time.time() - t0)
        w.close()
    try:
        targets = db.query(Recording).filter(Recording.id.in_(ids)).all()
        th = threading.Timer(0.1, writer)
        th.start()
        out = aps._delete_recordings(db, targets, batch_size=20)
        th.join()
        assert out["purged"] == 45
        assert out["removed_files"] >= 45 * 5
        assert db.query(Recording).filter(Recording.id.in_(ids)).count() == 0
        assert not any(os.path.exists(os.path.join(settings.spectrograms_dir, f"{r}_spectrogram_0.png")) for r in ids)
        assert os.path.exists(keep)
        assert waits and waits[0] < 0.6, waits
    finally:
        fc.remove_files = orig
        r = db.query(Recording).filter(Recording.id == "rec-a").first()
        r.notes = None
        db.commit()
        os.unlink(keep)
        db.close()


def test_delete_endpoint_returns_before_file_cleanup(client):
    import datetime as _dt
    import shutil
    import time
    from app.config import settings
    from app.database import SessionLocal
    from app.models import Recording
    db = SessionLocal()
    wav = db.query(Recording).filter(Recording.id == "rec-a").first().wav_path
    path = os.path.join(T, "recordings_dir", "del-1.wav")
    shutil.copy(wav, path)
    spec = os.path.join(settings.spectrograms_dir, "del-1_spectrogram_35.png")
    open(spec, "wb").write(b"x")
    old = _dt.datetime.utcnow() - _dt.timedelta(hours=1)
    db.add(Recording(id="del-1", filename="del-1.wav", wav_path=path, trigger_timestamp=old, created_at=old,
                     duration_seconds=12, sample_rate=48000, channels=1, pre_roll_seconds=5,
                     device_count=1, processing_status="done", device_id="dev1"))
    db.commit()
    db.close()
    r = client.delete("/api/v1/recordings/del-1?delete_files=true&hard_delete=true")
    assert r.status_code < 300, r.text
    assert client.get("/api/v1/recordings/del-1").status_code == 404
    for _ in range(50):
        if not os.path.exists(path) and not os.path.exists(spec):
            break
        time.sleep(0.05)
    assert not os.path.exists(path) and not os.path.exists(spec)


def test_list_hides_recordings_that_show_nothing(client):
    import datetime as _dt
    from app.database import SessionLocal
    from app.models import AppSettings, Detection, Recording
    db = SessionLocal()
    disp = float(db.query(AppSettings).filter(AppSettings.id == 1).first().min_confidence_display or 0)
    now = _dt.datetime.utcnow()

    def rec(rid, device="dev1", **kw):
        db.add(Recording(id=rid, filename=f"{rid}.wav", wav_path="/nonexistent.wav", trigger_timestamp=now, created_at=now,
                         duration_seconds=12, sample_rate=48000, channels=1, pre_roll_seconds=5, device_count=1,
                         processing_status=kw.pop("processing_status", "done"), device_id=device, **kw))
    rec("hd-owl"); rec("hd-empty"); rec("hd-manual", device=None); rec("hd-labeled", label="Mine")
    rec("hd-pending", processing_status="pending"); rec("hd-shown")
    db.add(Detection(recording_id="hd-owl", common_name="Great Horned Owl", label="Bubo_GHO",
                     confidence=max(0.0, disp - 0.05), source="server"))
    db.add(Detection(recording_id="hd-shown", common_name="Blue Jay", label="x_Blue Jay",
                     confidence=disp + 0.1, source="server"))
    db.commit()
    try:
        def ids(**params):
            r = client.get("/api/v1/recordings", params={"limit": 200, **params})
            assert r.status_code == 200, r.text
            return {x["id"] for x in r.json() if x["id"].startswith("hd-")}
        assert ids() == {"hd-manual", "hd-labeled", "hd-pending", "hd-shown"}
        assert ids(no_detections="true") == {"hd-owl", "hd-empty", "hd-manual", "hd-labeled", "hd-pending"}
        assert ids(no_detections="false") == {"hd-shown"}
    finally:
        for r in db.query(Recording).filter(Recording.id.like("hd-%")).all():
            db.delete(r)
        db.commit()
        db.close()


def test_reanalysis_history_and_undo(client):
    r = client.post("/api/v1/recordings/rec-a/reanalyze")
    assert r.status_code == 202 and r.json()["run_id"]
    runs = client.get("/api/v1/recordings/rec-a/reanalysis-history").json()["runs"]
    assert len(runs) == 1 and runs[0]["status"] in ("done", "error") and runs[0]["can_undo"]
    assert runs[0]["before_count"] == 1
    assert any(c["species"] == "Blue Jay" for c in runs[0]["changes"])
    u = client.post(f"/api/v1/recordings/rec-a/reanalysis/{runs[0]['id']}/undo")
    assert u.status_code == 200 and u.json()["restored"] == 1
    d = client.get("/api/v1/recordings/rec-a").json()
    assert [(x["id"], x["source"], x["confidence"]) for x in d["detections"]] == [("dev-a", "device", 0.62)]
    assert client.post(f"/api/v1/recordings/rec-a/reanalysis/{runs[0]['id']}/undo").status_code == 409


def test_near_miss_endpoints(client):
    assert client.get("/api/v1/near-misses/summary?days=3650").status_code == 200
    assert client.get("/api/v1/near-misses?days=3650").status_code == 200


def test_species_thresholds_setting(client):
    r = client.put("/api/v1/settings", json={"birdnet_species_thresholds": {"Barred Owl": 0.2, "x": 7, "": 0.3}})
    assert r.status_code == 200
    assert client.get("/api/v1/settings").json()["birdnet_species_thresholds"] == {"Barred Owl": 0.2}


def test_ssh_websocket_requires_sign_in(client):
    from app.database import SessionLocal
    from app.models import AppSettings
    db = SessionLocal()
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    s.auth_enabled = True
    db.commit()
    try:
        with client.websocket_connect("/api/v1/devices/nope/ssh") as ws:
            msg = ws.receive_json()
        assert msg["type"] == "error" and "sign" in msg["data"].lower()
    finally:
        s.auth_enabled = False
        db.commit()
        db.close()


def test_edit_recorded_time(client):
    r = client.patch("/api/v1/recordings/rec-hidden", json={"recorded_at": "2026-05-31T23:30:00-04:00"})
    assert r.status_code == 200 and r.json()["trigger_timestamp"].startswith("2026-06-01T03:30:00")
    # No offset: the server's timezone (America/New_York by default).
    r = client.patch("/api/v1/recordings/rec-hidden", json={"recorded_at": "2026-05-31T23:30:00"})
    assert r.json()["trigger_timestamp"].startswith("2026-06-01T03:30:00")
    assert client.patch("/api/v1/recordings/rec-hidden", json={"recorded_at": "2099-01-01T00:00:00Z"}).status_code == 400
    assert client.patch("/api/v1/recordings/rec-hidden", json={"label": "x"}).json()["trigger_timestamp"].startswith("2026-06-01T03:30")


def test_manual_upload_time_from_name_and_form(client):
    import io
    sr = 48000
    buf = io.BytesIO()
    sf.write(buf, np.zeros(sr, dtype=np.float32), sr, format="WAV", subtype="PCM_16")
    data = buf.getvalue()
    r = client.post("/api/v1/recordings/upload-manual",
                    files={"file": ("Barred_Owl_H_Oct_1_2026_121158_AM.wav", data, "audio/wav")})
    assert r.status_code == 201, r.text
    d = client.get(f"/api/v1/recordings/{r.json()['id']}").json()
    assert d["trigger_timestamp"].startswith("2026-10-01T04:11:58")
    r = client.post("/api/v1/recordings/upload-manual", data={"recorded_at": "2026-09-30T12:00:00Z"},
                    files={"file": ("Barred_Owl_H_Oct_1_2026_121158_AM.wav", data, "audio/wav")})
    d = client.get(f"/api/v1/recordings/{r.json()['id']}").json()
    assert d["trigger_timestamp"].startswith("2026-09-30T12:00:00")


def test_ai_recheck_runs_in_background(client, monkeypatch):
    import datetime as _dt
    from app.services import ai_providers, call_reanalysis
    monkeypatch.setattr(ai_providers, "get_feature_config", lambda key, db: ("anthropic", "k"))

    def fake(db, rec):
        rec.ai_reanalysis_note = "**Blue Jay** (likelihood 80%) ok"
        rec.ai_reanalysis_generated_at = _dt.datetime.utcnow()
        db.commit()
    monkeypatch.setattr(call_reanalysis, "reanalyze_call", fake)
    r = client.post("/api/v1/recordings/rec-a/ai-recheck")
    assert r.status_code == 202 and r.json()["status"] == "running"
    d = client.get("/api/v1/recordings/rec-a").json()
    assert d["ai_reanalysis_note"].startswith("**Blue Jay**") and d["ai_reanalysis_generated_at"]
    assert d["ai_reanalysis_running"] is False and d["ai_reanalysis_error"] is None

    def boom(db, rec):
        raise RuntimeError("provider timed out")
    monkeypatch.setattr(call_reanalysis, "reanalyze_call", boom)
    client.post("/api/v1/recordings/rec-a/ai-recheck")
    d = client.get("/api/v1/recordings/rec-a").json()
    assert d["ai_reanalysis_error"] == "provider timed out" and not d["ai_reanalysis_running"]


def test_ai_recheck_not_configured(client):
    r = client.post("/api/v1/recordings/rec-a/ai-recheck")
    assert r.status_code == 400 and "Settings" in r.json()["detail"]
