"""The public demo: a scrubbed copy of a real location, dates that roll
forward, a passwordless read-only sign-in, and no joins."""
import json
import os
import sys
import uuid
from datetime import datetime, timedelta

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _wav(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sf.write(path, np.zeros(480000, dtype=np.float32), 48000)    # 10 s
    return path


@pytest.fixture(scope="module")
def source():
    """A location with a secret-laden setup, recent and old recordings, a
    voice recording and a station."""
    from sqlalchemy.orm import sessionmaker
    from app.config import settings
    from app.instance_registry import get_engine_for_instance, new_db_filename, provision_instance_database
    from app.models import AppSettings, BirdProfile, Detection, Device, Recording
    from app.registry_db import RegistrySessionLocal, init_registry_db
    from app.registry_models import Instance
    init_registry_db()
    name = f"Source {uuid.uuid4().hex[:6]}"
    fname = new_db_filename("srcsrcsr")
    reg = RegistrySessionLocal()
    reg.add(Instance(name=name, location_name="Natick, MA", db_filename=fname))
    reg.commit()
    reg.close()
    provision_instance_database(fname)
    db = sessionmaker(bind=get_engine_for_instance(fname))()
    s = db.query(AppSettings).first()
    s.location_name, s.latitude, s.longitude, s.timezone = "Natick, MA", 42.28, -71.35, "America/New_York"
    s.min_confidence_display = 0.2
    s.smtp_password, s.anthropic_api_key, s.haikubox_serial, s.ebird_api_key = "pw", "sk-x", "HB1", "ebird"
    s.daily_summary_text = "A busy morning in Natick."
    db.add(Device(id="dev1", name="Yard", ip_address="192.168.1.50", ssh_username="pi", ssh_password="secret",
                  hostname="chirp-yard", tailscale_ip="100.1.2.3", platform="pi5", mic_count=2))
    now = datetime.utcnow()
    audio = os.path.join(settings.recordings_dir, "src")
    rows = [("r-new", now - timedelta(days=2), "Blue Jay", 0.9),
            ("r-new2", now - timedelta(days=3, hours=4), "Northern Cardinal", 0.8),
            ("r-voice", now - timedelta(days=1), "Human_Human", 0.9),
            ("r-old", now - timedelta(days=200), "Blue Jay", 0.7),
            ("r-old2", now - timedelta(days=150), "Barred Owl", 0.6),
            ("r-weak", now - timedelta(days=1, hours=2), "Blue Jay", 0.05)]
    for rid, ts, sp, conf in rows:
        db.add(Recording(id=rid, filename=f"{rid}.wav", wav_path=_wav(os.path.join(audio, f"{rid}.wav")),
                         trigger_timestamp=ts, created_at=ts, duration_seconds=12, device_id="dev1", latitude=42.28, longitude=-71.35,
                         place_name="12 Elm St", notes="private note", processing_status="done"))
        db.add(Detection(id=f"d-{rid}", recording_id=rid, common_name=sp, label=f"x_{sp}", confidence=conf,
                         start_time=0, end_time=3, source="device"))
    db.add(Detection(id="d-r-new-hum", recording_id="r-new2", common_name="Human", label="Human_Human",
                     confidence=0.1, source="device"))
    db.add(BirdProfile(common_name="Blue Jay", label="x_Blue Jay", notes="seen by the shed"))
    db.commit()
    db.close()
    return name


@pytest.fixture(scope="module")
def demo(source):
    from app.services import demo as D
    return D.build(source)


def _demo_db(iid):
    from sqlalchemy.orm import sessionmaker
    from app.instance_registry import get_engine_for_instance
    from app.registry_db import RegistrySessionLocal
    from app.registry_models import Instance
    reg = RegistrySessionLocal()
    f = reg.get(Instance, iid).db_filename
    reg.close()
    return sessionmaker(bind=get_engine_for_instance(f))()


def test_build_copies_birds_and_scrubs_the_rest(demo):
    from app.models import AppSettings, BirdProfile, Device, Recording, User
    from app.registry_db import RegistrySessionLocal
    from app.registry_models import Instance, Membership
    from app.services import demo as D
    reg = RegistrySessionLocal()
    inst = reg.get(Instance, demo)
    assert inst.is_demo and inst.location_name == D.DEMO_PLACE
    assert [m.role for m in reg.query(Membership).filter(Membership.instance_id == demo)] == ["viewer"]
    reg.close()

    db = _demo_db(demo)
    ids = {r.id for r in db.query(Recording)}
    # Recent birds; each species' first recording; no voices, no weak-only.
    assert ids == {"r-new", "r-old", "r-old2"}
    for r in db.query(Recording):
        assert r.wav_path.startswith(os.path.join(D._demo_dir(demo), "audio")) and os.path.exists(r.wav_path)
        assert r.notes is None and r.place_name is None and (r.latitude, r.longitude) == (D.DEMO_LAT, D.DEMO_LON)
    s = db.query(AppSettings).first()
    assert (s.smtp_password, s.anthropic_api_key, s.haikubox_serial) == (None, None, None)
    assert s.ebird_api_key == "ebird" and s.location_name == D.DEMO_PLACE and s.latitude == D.DEMO_LAT
    assert not s.notifications_enabled and not s.auto_backup_enabled
    assert "Natick" not in (s.daily_summary_text or "") and "Concord" in s.daily_summary_text
    d = db.query(Device).one()
    assert (d.ip_address, d.ssh_password, d.ssh_username, d.hostname, d.tailscale_ip) == (None,) * 5
    assert d.name == "Yard" and d.mic_count == 2 and d.status == "online"
    assert db.query(BirdProfile).filter(BirdProfile.common_name == "Blue Jay").one().notes is None
    u = db.query(User).filter(User.username == D.DEMO_USER).one()
    assert u.role == "viewer" and u.ui_mode == "pro" and u.dashboard_mode == "standard"
    db.close()


def test_roll_keeps_recent_inside_the_window(demo):
    from app.models import Recording
    from app.services import demo as D
    db = _demo_db(demo)
    before = {r.id: r.trigger_timestamp for r in db.query(Recording)}
    db.close()
    # A week later every recent recording has moved forward; history hasn't.
    later = datetime.utcnow() + timedelta(days=7, hours=3)
    D.roll_instance(demo, now=later)
    db = _demo_db(demo)
    after = {r.id: r.trigger_timestamp for r in db.query(Recording)}
    db.close()
    assert after["r-old"] == before["r-old"] and after["r-old2"] == before["r-old2"]
    assert later - timedelta(days=D.WINDOW_DAYS) < after["r-new"] <= later
    assert (after["r-new"] - before["r-new"]).days % D.WINDOW_DAYS == 0          # whole windows, same time of day
    # Rolling again at the same moment changes nothing.
    assert D.roll_instance(demo, now=later)["moved"] == 0
    state = json.load(open(D._state_path(demo)))
    assert datetime.fromisoformat(state["history_before"]) < after["r-new"]


def test_demo_scope_is_read_only():
    from app.main import demo_may_use
    assert demo_may_use("GET", "/api/v1/recordings")
    assert demo_may_use("POST", "/api/v1/live-detect/analyze")
    assert demo_may_use("PUT", "/api/v1/auth/me/profile")
    for m, p in [("POST", "/api/v1/live-detect/save-session"), ("DELETE", "/api/v1/recordings/x"),
                 ("POST", "/api/v1/recordings/x/comments"), ("POST", "/api/v1/instances/join"),
                 ("POST", "/api/v1/auth/watch-token"), ("PUT", "/api/v1/settings"),
                 ("GET", "/api/v1/admin/usage"), ("POST", "/api/v1/recordings/upload")]:
        assert not demo_may_use(m, p), (m, p)


def test_demo_sign_in_and_profile(demo):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import auth
    from app.services import demo as D
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1/auth")
    c = TestClient(app)
    assert c.get("/api/v1/auth/demo").json() == {"available": True}
    r = c.post("/api/v1/auth/demo").json()
    claims = auth.verify_token(r["access_token"])
    assert claims["scope"] == "demo" and claims["active_instance_id"] == demo and claims["sub"] == D.DEMO_USER
    assert r["role"] == "viewer"
    # The shared visitor can't change its account.
    from app.database import get_db
    app.dependency_overrides[get_db] = lambda: _demo_db(demo)
    h = {"Authorization": "Bearer " + r["access_token"]}
    assert c.put("/api/v1/auth/me/profile", json={"display_name": "x"}, headers=h).status_code == 403
    assert c.put("/api/v1/auth/me/profile", json={"dashboard_mode": "advanced"}, headers=h).json()["ok"]
    db = _demo_db(demo)
    from app.models import User
    assert db.query(User).filter(User.username == D.DEMO_USER).one().dashboard_mode == "standard"   # not kept
    db.close()
    # A demo sign-in can't mint a longer-lived watch one.
    assert c.post("/api/v1/auth/watch-token", headers=h).status_code in (401, 403)
    # Rate limit per address.
    auth._demo_by_ip.clear()
    codes = [c.post("/api/v1/auth/demo").status_code for _ in range(auth.DEMO_IP_MAX + 1)]
    assert codes[-1] == 429 and codes[0] == 200
    auth._demo_by_ip.clear()


def test_nobody_joins_the_demo(demo):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import instances
    from app.registry_db import RegistrySessionLocal
    from app.registry_models import GlobalUser, Instance
    reg = RegistrySessionLocal()
    code = reg.get(Instance, demo).invite_code
    u = GlobalUser(id=f"j-{uuid.uuid4().hex[:6]}", username=f"joiner{uuid.uuid4().hex[:6]}", hashed_pw="x")
    reg.add(u)
    reg.commit()
    reg.refresh(u)
    reg.expunge(u)
    reg.close()
    app = FastAPI()
    app.include_router(instances.router, prefix="/api/v1/instances")
    app.dependency_overrides[instances.get_current_global_user] = lambda: u
    r = TestClient(app).post("/api/v1/instances/join", json={"invite_code": code})
    assert r.status_code == 404


def test_background_jobs_skip_the_demo(demo):
    from app.instance_registry import iter_instance_sessions
    seen = {i.id for i, db in iter_instance_sessions()}
    assert demo not in seen
    assert demo in {i.id for i, db in iter_instance_sessions(include_demo=True)}


def test_demo_live_detect_is_rate_limited():
    from app.main import _demo_analyze, demo_analyze_ok
    _demo_analyze.clear()
    assert all(demo_analyze_ok("1.2.3.4", now=1000 + i * 0.1) for i in range(60))
    assert not demo_analyze_ok("1.2.3.4", now=1006.5)
    assert demo_analyze_ok("5.6.7.8", now=1006.5)
    assert demo_analyze_ok("1.2.3.4", now=1070)
    _demo_analyze.clear()


def test_demo_cant_post_to_media_paths():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.auth import create_access_token
    from app.main import AuthMiddleware
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.post("/api/v1/recordings/upload")
    def upload():
        return {"ok": True}

    c = TestClient(app)
    demo = create_access_token({"sub": "chirp-demo", "scope": "demo"}, expires_minutes=5)
    other = create_access_token({"sub": "someone"}, expires_minutes=5)
    assert c.post("/api/v1/recordings/upload", headers={"Authorization": "Bearer " + demo}).status_code == 403
    assert c.post("/api/v1/recordings/upload", headers={"Authorization": "Bearer " + other}).status_code == 200


def test_demo_shows_its_journal(demo):
    from app.instance_registry import _current_instance_db_filename
    from app.registry_db import RegistrySessionLocal
    from app.registry_models import Instance
    from app.services import demo as D
    from app.api.recordings import get_daily_journal
    reg = RegistrySessionLocal()
    f = reg.get(Instance, demo).db_filename
    reg.close()
    D._demo_files["at"] = 0
    tok = _current_instance_db_filename.set(f)
    try:
        assert D.is_demo_db()
        db = _demo_db(demo)
        j = get_daily_journal(db)
        db.close()
        assert j["enabled"] and "Concord" in j["text"]
    finally:
        _current_instance_db_filename.reset(tok)
    assert not D.is_demo_db()


def test_demo_station_replays_a_recording(demo):
    import io
    import soundfile as sf
    from app.instance_registry import _current_instance_db_filename
    from app.registry_db import RegistrySessionLocal
    from app.registry_models import Instance
    from app.services import demo as D
    reg = RegistrySessionLocal()
    f = reg.get(Instance, demo).db_filename
    reg.close()
    D._demo_files["at"] = 0
    D.set_loop("r-new")                              # 10 s, Blue Jay at 0–3 s
    tok = _current_instance_db_filename.set(f)
    try:
        db = _demo_db(demo)
        x, sr = sf.read(io.BytesIO(D.demo_listen_clip(db, now=1005.0)))
        assert sr == 48000 and abs(len(x) / sr - D.LISTEN_SECONDS) < 0.01
        heard = D.demo_station_heard(db, 0.2, now=1005.0)          # loop time 1–5 s
        assert heard["detected"] and [d["common_name"] for d in heard["detections"]] == ["Blue Jay"]
        assert not D.demo_station_heard(db, 0.2, now=1009.5)["detected"]   # 5.5–9.5 s
        assert D.demo_station_heard(db, 0.2, now=1001.0)["detected"]       # wraps: 7–10 and 0–1 s
        assert not D.demo_station_heard(db, 0.95, now=1005.0)["detected"]  # the slider still applies
        db.close()
    finally:
        _current_instance_db_filename.reset(tok)
    D.touch_devices()
    db = _demo_db(demo)
    from app.models import Device
    assert db.query(Device).one().is_online()
    db.close()


def test_demo_account_cant_be_deleted(demo):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import auth
    from app.main import demo_may_use
    from app.services import demo as D
    assert not demo_may_use("POST", "/api/v1/auth/me/delete")
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1/auth")
    c = TestClient(app)
    auth._demo_by_ip.clear()
    t = c.post("/api/v1/auth/demo").json()["access_token"]
    # Even reaching the endpoint (or a plain sign-in as the demo user) is refused.
    for tok in (t, auth.create_access_token({"sub": D.DEMO_USER}, expires_minutes=5)):
        r = c.post("/api/v1/auth/me/delete", json={"password": "x"}, headers={"Authorization": "Bearer " + tok})
        assert r.status_code == 403
    from app.registry_db import RegistrySessionLocal
    from app.registry_models import GlobalUser
    reg = RegistrySessionLocal()
    assert reg.query(GlobalUser).filter(GlobalUser.username == D.DEMO_USER).count() == 1
    reg.close()
    auth._demo_by_ip.clear()
