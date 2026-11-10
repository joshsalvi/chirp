"""Usage per location for Global Admin: counts, members, stations, storage."""
import os
import sys
import time
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_usage(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker
    from app.api import admin_panel
    from app.instance_registry import get_engine_for_instance, provision_instance_database
    from app.models import AppSettings, Detection, Device, Recording
    from app.registry_db import RegistrySessionLocal, init_registry_db
    from app.registry_models import GlobalUser, Instance, Membership
    from app.services import usage

    init_registry_db()
    tag = uuid.uuid4().hex[:8]
    fname = f"usage-{tag}.db"
    provision_instance_database(fname)
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x" * 1000)
    spec = tmp_path / "a.png"
    spec.write_bytes(b"y" * 500)

    now = datetime.utcnow()
    db = sessionmaker(bind=get_engine_for_instance(fname))()
    s = db.query(AppSettings).first() or AppSettings(id=1)
    s.timezone, s.min_confidence_display = "UTC", 0.2
    db.add(s)
    for i, (age, conf, name) in enumerate([(0, 0.8, "Blue Jay"), (3, 0.7, "Northern Cardinal"),
                                           (20, 0.9, "Barred Owl"), (60, 0.9, "Wood Duck"), (1, 0.05, "Ghost Bird")]):
        rid = f"r{i}-{tag}"
        db.add(Recording(id=rid, filename=f"{rid}.wav", wav_path=str(wav) if i == 0 else str(tmp_path / f"missing{i}.wav"),
                         spectrogram_path=str(spec) if i == 0 else None,
                         trigger_timestamp=now - timedelta(days=age, minutes=1), duration_seconds=12,
                         sample_rate=48000, channels=1, pre_roll_seconds=5, device_count=1))
        db.add(Detection(id=f"d{i}-{tag}", recording_id=rid, common_name=name, label=name, confidence=conf))
    db.add(Device(id=f"dev-{tag}", name="Backyard Pi", last_seen=now - timedelta(minutes=5)))
    db.commit()
    db.close()

    reg = RegistrySessionLocal()
    inst = Instance(id=f"inst-{tag}", name=f"Usage {tag}", db_filename=fname, invite_code=f"U{tag}")
    u1 = GlobalUser(id=f"u1-{tag}", username=f"ada{tag}", hashed_pw="x", last_login=now - timedelta(hours=2))
    u2 = GlobalUser(id=f"u2-{tag}", username=f"bo{tag}", hashed_pw="x")
    reg.add_all([inst, u1, u2])
    reg.flush()
    reg.add_all([Membership(id=f"m1-{tag}", user_id=u1.id, instance_id=inst.id, role="admin"),
                 Membership(id=f"m2-{tag}", user_id=u2.id, instance_id=inst.id, role="viewer")])
    reg.commit()
    inst_id, names = inst.id, [u1.username, u2.username]
    reg.close()

    app = FastAPI()
    app.include_router(admin_panel.router, prefix="/api/v1/admin")
    app.dependency_overrides[admin_panel.get_current_global_admin] = lambda: GlobalUser(id="a", username="boss", hashed_pw="x", is_global_admin=True)
    c = TestClient(app)

    usage._storage.clear()
    row = [r for r in c.get("/api/v1/admin/usage").json() if r["id"] == inst_id][0]
    assert row["recordings"] == {"today": 1, "d7": 3, "d30": 4, "total": 5}
    assert row["detections_7d"] == 2                       # the 0.05 one is below the display threshold
    assert row["species_30d"] == 3
    assert row["last_recording"] and row["last_recording"].endswith("Z")
    assert row["stations"][0]["name"] == "Backyard Pi" and row["stations"][0]["last_seen"]
    assert [m["username"] for m in row["members"]] == names   # most recent sign-in first
    assert row["last_sign_in"] == row["members"][0]["last_login"]
    assert row["storage"]["bytes"] is None                 # first request starts the measurement

    for _ in range(50):
        if inst_id in usage._storage:
            break
        time.sleep(0.05)
    row = [r for r in c.get("/api/v1/admin/usage").json() if r["id"] == inst_id][0]
    assert row["storage"]["files"] == 2
    assert row["storage"]["bytes"] >= 1500 + 1               # files plus the database
    assert row["storage"]["measured_at"].endswith("Z")
