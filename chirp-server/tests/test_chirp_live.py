"""0.5.16.t: Chirp Live, the Live Detect app. Its sign-in reaches the station
list and audio; station clips it relays are credited to the station; and the
place it was made shows on the recording."""
import datetime
import io
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_live_sign_in_paths():
    from app.main import watch_may_use as ok
    assert ok("/api/v1/tv/stations") and ok("/api/v1/tv/listen/d-1")
    for p in ["/api/v1/tv/recent", "/api/v1/tv/pair/approve", "/api/v1/tv/listen/../x", "/api/v1/devices"]:
        assert not ok(p), p


def test_clean_place():
    from app.api.live_detect import _clean_place
    assert _clean_place("  Broadmoor \n Wildlife  Sanctuary ") == "Broadmoor Wildlife Sanctuary"
    assert _clean_place("") is None and _clean_place(None) is None
    assert len(_clean_place("x" * 500)) == 120


def _wav(seconds=3):
    sr = 48000
    y = (0.01 * np.random.default_rng(1).standard_normal(seconds * sr)).astype(np.float32)
    b = io.BytesIO(); sf.write(b, y, sr, format="WAV", subtype="PCM_16"); return b.getvalue()


def test_relayed_station_clip_needs_a_known_station(client):
    files = {"file": ("live.wav", _wav(), "audio/wav")}
    r = client.post("/api/v1/live-detect/analyze", data={"source": "device"}, files=files)
    assert r.status_code == 400
    r = client.post("/api/v1/live-detect/analyze", data={"source": "device", "device_id": "no-such"},
                    files={"file": ("live.wav", _wav(), "audio/wav")})
    assert r.status_code == 404


def test_session_keeps_the_place(client):
    from app.database import SessionLocal
    from app.models import Detection, Recording
    db = SessionLocal()
    start = datetime.datetime.utcnow().replace(microsecond=0)
    wav = os.path.join(os.environ["CHIRP_RECORDINGS_DIR"], "live-place.wav")
    os.makedirs(os.path.dirname(wav), exist_ok=True)
    with open(wav, "wb") as f:
        f.write(_wav())
    db.add(Recording(id="live-clip-1", filename="live-place.wav", wav_path=wav, trigger_timestamp=start,
                     duration_seconds=3, sample_rate=48000, channels=1, pre_roll_seconds=0, device_count=1,
                     processing_status="done", is_live_detect_clip=True, latitude=42.2731, longitude=-71.3502,
                     place_name="Broadmoor"))
    db.add(Detection(id="live-det-1", recording_id="live-clip-1", common_name="Blue Jay",
                     label="Cyanocitta cristata_Blue Jay", confidence=0.8, start_time=0, end_time=3, source="server"))
    db.commit(); db.close()
    r = client.post("/api/v1/live-detect/save-session",
                    data={"recording_ids": '["live-clip-1"]', "session_start": start.isoformat() + "Z",
                          "latitude": "42.2731", "longitude": "-71.3502"},
                    files={"file": ("session.wav", _wav(5), "audio/wav")})
    assert r.status_code == 200, r.text
    rid = r.json()["recording_id"]
    rec = client.get(f"/api/v1/recordings/{rid}").json()
    assert rec["place_name"] == "Broadmoor"
    assert abs(rec["latitude"] - 42.2731) < 1e-6

    # Sent again (the phone missed the reply): the same recording, no duplicate.
    again = client.post("/api/v1/live-detect/save-session",
                        data={"recording_ids": '["live-clip-1"]', "session_start": start.isoformat() + "Z"},
                        files={"file": ("session.wav", _wav(5), "audio/wav")})
    assert again.status_code == 200 and again.json()["recording_id"] == rid and again.json()["already_saved"]


def test_scoped_sign_ins_are_limited_even_without_site_sign_in(client):
    # The test server has sign-in off, like a multi-site server's own check.
    from app.api.auth import create_access_token
    watch = create_access_token({"sub": "josh", "scope": "watch"})
    tv = create_access_token({"sub": "josh", "scope": "tv"})
    h = lambda t: {"Authorization": "Bearer " + t}
    assert client.get("/api/v1/settings", headers=h(watch)).status_code == 403
    assert client.get("/api/v1/devices", headers=h(watch)).status_code == 403
    assert client.get("/api/v1/tv/stations", headers=h(watch)).status_code == 200
    assert client.get("/api/v1/settings", headers=h(tv)).status_code == 403
    assert client.get("/api/v1/tv/stations", headers=h(tv)).status_code == 200
    assert client.get("/api/v1/settings").status_code == 200
