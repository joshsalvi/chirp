"""
Shared API test setup: a throwaway data directory and database, set before
any test imports app.config (settings and the engine are read once per
process), and one TestClient for the session.
"""
import datetime
import os
import sys

import numpy as np
import pytest
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))

# Set at import (collection), before any test loads app.config: settings
# and the database engine are read once per process.
import tempfile  # noqa: E402
T = tempfile.mkdtemp(prefix="chirp-test-")
for _k in ["recordings_dir", "media_dir", "spectrograms_dir", "clips_dir", "enhanced_dir",
           "bat_clips_dir", "ai_models_dir"]:
    os.environ["CHIRP_" + _k.upper()] = os.path.join(T, _k)
os.environ["CHIRP_DATA_DIR"] = T
os.environ["CHIRP_DB_URL"] = f"sqlite:///{T}/chirp.db"


@pytest.fixture(scope="session")
def client():
    pytest.importorskip("birdnetlib")
    sys.path.insert(0, os.path.dirname(HERE))
    from fastapi.testclient import TestClient
    import app.main as m
    from app.database import SessionLocal, init_db
    from app.models import AppSettings, Detection, Recording
    init_db()
    sr = 48000
    t = np.arange(12 * sr) / sr
    y = (0.003 * np.random.default_rng(0).standard_normal(len(t))
         + 0.1 * np.sin(2 * np.pi * 3000 * t) * (np.sin(2 * np.pi * 2 * t) > 0.6)).astype(np.float32)
    os.makedirs(os.path.join(T, "recordings_dir"), exist_ok=True)
    wav = os.path.join(T, "recordings_dir", "a.wav")
    sf.write(wav, y, sr, subtype="PCM_16")
    db = SessionLocal()
    s = db.query(AppSettings).filter(AppSettings.id == 1).first() or AppSettings(id=1)
    s.latitude, s.longitude, s.auth_enabled = 42.28, -71.35, False
    s.birdnet_min_confidence, s.min_confidence_display = 0.3, 0.15
    db.add(s)
    ts = datetime.datetime(2026, 6, 1, 6, 0)
    for rid, conf in (("rec-a", 0.62), ("rec-hidden", 0.08), ("rec-owl", 0.12)):
        db.add(Recording(id=rid, filename=f"{rid}.wav", wav_path=wav, trigger_timestamp=ts,
                         duration_seconds=12, sample_rate=sr, channels=1, pre_roll_seconds=5,
                         device_count=1, processing_status="done"))
    db.add(Detection(id="dev-a", recording_id="rec-a", common_name="Blue Jay", label="Cyanocitta cristata_Blue Jay",
                     scientific_name="Cyanocitta cristata", confidence=0.62, start_time=0, end_time=3, source="device"))
    db.add(Detection(id="dev-h", recording_id="rec-hidden", common_name="Blue Jay", label="x_Blue Jay",
                     confidence=0.08, source="device"))
    db.add(Detection(id="dev-o", recording_id="rec-owl", common_name="Barred Owl", label="Strix varia_Barred Owl",
                     confidence=0.12, source="device"))
    db.commit()
    db.close()
    return TestClient(m.app)
