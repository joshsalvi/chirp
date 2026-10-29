"""BirdWeather sync: soundscapes are downloaded, converted and analysed once."""
import io
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _flac():
    buf = io.BytesIO()
    t = np.arange(3 * 32000) / 32000
    sf.write(buf, (0.1 * np.sin(2 * np.pi * 3000 * t)).astype(np.float32), 32000, format="FLAC")
    return buf.getvalue()


class _Resp:
    def __init__(self, status=200, json=None, content=b""):
        self.status_code, self._json, self.content = status, json, content

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError("x", request=None, response=self)


def _fake_client(pages, audio, calls):
    class C:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

        def get(self, url, params=None):
            calls.append((url, dict(params or {})))
            if "/soundscapes" in url:
                if "bad" in url:
                    return _Resp(401, {})
                return _Resp(200, {"success": True, "soundscapes": pages.pop(0) if pages else []})
            return _Resp(200, content=audio)
    return C


def test_parse_time_and_key():
    from app.services.birdweather_sync import parse_time, station_key
    assert str(parse_time("2026-10-28T07:12:03.000-04:00")) == "2026-10-28 11:12:03"
    assert str(parse_time("2026-10-28T11:12:03Z")) == "2026-10-28 11:12:03"
    assert parse_time("nope") is None
    assert station_key("abc") == station_key(" abc ") and "abc" not in station_key("abc")


def test_sync_imports_each_soundscape_once(client, monkeypatch):
    from app.database import SessionLocal
    from app.models import AppSettings, Device, Recording
    from app.services import birdweather_sync as bw
    import app.api.recordings as recs

    analysed = []
    monkeypatch.setattr(recs, "_process_manual_upload", lambda rid, *a: analysed.append(rid))
    soundscapes = [{"id": 901, "timestamp": "2026-10-28T07:00:00-04:00", "duration": 3, "url": "https://media.example/901.flac"},
                   {"id": 902, "timestamp": "2026-10-28T07:05:00-04:00", "duration": 3, "url": "https://media.example/902.flac"}]
    calls = []
    monkeypatch.setattr(bw.httpx, "Client", _fake_client([list(reversed(soundscapes))], _flac(), calls))

    db = SessionLocal()
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    s.birdweather_enabled, s.birdweather_token = True, "tok-123"
    from datetime import datetime
    s.birdweather_cursor_at = datetime(2026, 10, 28, 10, 0)
    db.commit(); db.close()
    try:
        svc = bw.BirdWeatherSyncService()
        assert svc.run_sync() == 2
        assert calls[0][0].endswith("/stations/tok-123/soundscapes") and calls[0][1]["limit"] == 100
        db = SessionLocal()
        rows = db.query(Recording).filter(Recording.birdweather_soundscape_id.in_(["901", "902"])).all()
        assert len(rows) == 2 and set(analysed) == {r.id for r in rows}
        r = rows[0]
        assert r.wav_path.endswith(".wav") and os.path.exists(r.wav_path)
        info = sf.info(r.wav_path)
        assert info.samplerate == 48000 and info.channels == 1 and abs(info.duration - 3) < 0.1
        dev = db.query(Device).filter(Device.id == r.device_id).first()
        assert dev.platform == "BirdWeather" and "tok-123" not in (dev.hostname or "")
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        assert str(s.birdweather_cursor_at) == "2026-10-28 11:05:00" and not s.birdweather_last_sync_error
        db.close()

        # Next sync asks only for newer sound; the same ids again aren't re-imported.
        calls.clear()
        monkeypatch.setattr(bw.httpx, "Client", _fake_client([soundscapes], _flac(), calls))
        assert svc.run_sync() == 0
        assert calls[0][1]["from"].startswith("2026-10-28T11:05:00")

        # A bad token is reported, not raised.
        db = SessionLocal(); s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        s.birdweather_token = "bad"; db.commit(); db.close()
        assert svc.run_sync() == 0
        db = SessionLocal(); s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        assert "token" in (s.birdweather_last_sync_error or "")
        db.close()
    finally:
        db = SessionLocal(); s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        s.birdweather_enabled, s.birdweather_token, s.birdweather_cursor_at = False, None, None
        s.birdweather_last_sync_error = None
        for r in db.query(Recording).filter(Recording.birdweather_soundscape_id.isnot(None)).all():
            db.delete(r)
        db.commit(); db.close()


def test_settings_mask_token(client):
    from app.database import SessionLocal
    from app.models import AppSettings
    db = SessionLocal(); s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    s.birdweather_token = "abcdefghijklmnop"; db.commit(); db.close()
    try:
        out = client.get("/api/v1/settings").json()
        assert out["birdweather_token"] == "abcd****mnop"
        # Sending the masked value back leaves the token alone.
        assert client.put("/api/v1/settings", json={"birdweather_token": "abcd****mnop"}).status_code == 200
        db = SessionLocal(); assert db.query(AppSettings).first().birdweather_token == "abcdefghijklmnop"; db.close()
    finally:
        db = SessionLocal(); s = db.query(AppSettings).filter(AppSettings.id == 1).first(); s.birdweather_token = None; db.commit(); db.close()
