"""1.4.0: night audio for Nighthawk — window, chunking, upload, backlog."""
import os
import sys
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
pytest.importorskip("soxr")
pytest.importorskip("soundfile")
from chirp import night_audio  # noqa: E402
from chirp.night_audio import NightAudio, in_window  # noqa: E402


def test_in_window_wraps_midnight():
    at = lambda h, m: datetime(2026, 9, 20, h, m)
    assert in_window(at(22, 0), "21:00", "05:00")
    assert in_window(at(3, 59), "21:00", "05:00")
    assert not in_window(at(5, 0), "21:00", "05:00")
    assert not in_window(at(12, 0), "21:00", "05:00")
    assert in_window(at(1, 0), "00:30", "04:00") and not in_window(at(4, 0), "00:30", "04:00")
    assert not in_window(at(1, 0), "02:00", "02:00")


class _Resp:
    def __init__(self, code, body=None):
        self.status_code, self._b, self.text = code, body or {}, str(body)

    def json(self):
        return self._b


def _target(name):
    return SimpleNamespace(name=name, enabled=True, server_url=f"https://{name}/api/v1/recordings/upload",
                           api_key=f"key-{name}", auth_header="X-API-Key")


def _run(tmp_path, monkeypatch, answers):
    """answers: target -> (accepting?, upload status)."""
    import requests
    import soundfile as sf
    utc_now = datetime.utcnow()      # window in the server's timezone: UTC here
    window = {"start": (utc_now - timedelta(minutes=5)).strftime("%H:%M"),
              "end": (utc_now + timedelta(minutes=30)).strftime("%H:%M"),
              "timezone": "UTC", "chunk_minutes": 0.1}
    posts = []

    def fake_get(url, headers=None, timeout=None):
        host = url.split("/")[2]
        return _Resp(200, dict(window, enabled=answers[host][0]))

    def fake_post(url, headers=None, data=None, files=None, timeout=None):
        host = url.split("/")[2]
        f = files["file"][1]
        y, sr = sf.read(f)
        posts.append((host, data, sr, len(y)))
        return _Resp(answers[host][1])

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "post", fake_post)
    na = NightAudio({"night_audio": {"dir": str(tmp_path)}}, [_target(h) for h in answers], 48000)
    na._probe()
    assert na._active_now() == any(a for a, _ in answers.values())
    na.start()
    # 8 s of audio in 0.1 s chunks
    t_end = time.time() + 20
    for _ in range(80):
        na.feed((np.random.default_rng(1).standard_normal(4800) * 0.01).astype(np.float32))
        time.sleep(0.02)
        if na._file is None and time.time() < t_end:
            time.sleep(0.2)
    deadline = time.time() + 40
    while time.time() < deadline and (na.stats["chunks_written"] == 0 or na._pending()):
        time.sleep(0.5)
    na.stop()
    return na, posts


def test_chunks_upload_to_accepting_servers_then_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(night_audio, "PROBE_INTERVAL", 3600)
    na, posts = _run(tmp_path, monkeypatch, {"a": (True, 202), "b": (False, 202)})
    assert na.stats["chunks_written"] >= 1
    assert posts and {p[0] for p in posts} == {"a"}               # b didn't ask for audio
    host, data, sr, n = posts[0]
    assert sr == 22050 and n >= 22050 * 5.5
    assert data["sample_rate"] == "22050" and data["started_at"].endswith("Z")
    assert not [f for f in os.listdir(tmp_path) if f.endswith(".flac")]   # deleted once uploaded


def test_server_that_turned_it_off_drops_the_chunk(tmp_path, monkeypatch):
    monkeypatch.setattr(night_audio, "PROBE_INTERVAL", 3600)
    na, posts = _run(tmp_path, monkeypatch, {"a": (True, 410)})
    assert posts and not [f for f in os.listdir(tmp_path) if f.endswith(".flac")]


def test_backlog_limit_drops_oldest(tmp_path):
    na = NightAudio({"night_audio": {"dir": str(tmp_path), "max_backlog_gb": 0.0000015}}, [_target("a")], 48000)
    for i in range(3):
        p = tmp_path / f"night_2026092{i}T000000Z.flac"
        p.write_bytes(b"x" * 1000)
        (tmp_path / (p.name + ".json")).write_text("{}")
    na._enforce_backlog()
    left = sorted(f for f in os.listdir(tmp_path) if f.endswith(".flac"))
    assert left == ["night_20260922T000000Z.flac"] and na.stats["chunks_dropped"] == 2


def test_no_targets_means_no_recording(tmp_path):
    na = NightAudio({"night_audio": {"dir": str(tmp_path)}}, [], 48000)
    na.start()
    na.feed(np.zeros(4800, np.float32))
    assert na._file is None and not na._threads
