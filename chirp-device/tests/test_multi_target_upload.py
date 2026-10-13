#!/usr/bin/env python3
"""
test_multi_target_upload.py — real tests for uploader.py's multi-target
support, run with mocked HTTP so this works standalone without a real
server. Confirms:
  1. Legacy single-target config produces identical behavior to before
     the refactor — no `targets:` list needed for existing installs.
  2. A new-format multi-target config fans one recording out to every
     enabled target.
  3. Real failure isolation: a broken secondary target never blocks the
     primary's success or the resulting local file deletion — a
     structural property of the separate-queue design, tested directly
     rather than just asserted in the code's own comments.
  4. chirp-server's own lazy pair-once-then-cache flow: first upload
     triggers a pairing call, second upload reuses the cached device_id
     without pairing again.

Usage: python3 tests/test_multi_target_upload.py
"""
import json
import os
import queue
import shutil
import sys
import tempfile
import time
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chirp.uploader import FileUploader  # noqa: E402


def _make_recording(tmpdir, name="rec1", detections=None):
    wav_path = os.path.join(tmpdir, f"{name}.wav")
    json_path = os.path.join(tmpdir, f"{name}.json")
    with open(wav_path, "wb") as f:
        f.write(b"FAKE_WAV_BYTES")
    with open(json_path, "w") as f:
        json.dump({
            "duration_seconds": 3.0,
            "trigger_timestamp": "2026-08-06T10:00:00",
            "is_bat": False,
            "detections": detections or [{"common_name": "American Robin", "confidence": 0.9}],
        }, f)
    return wav_path, json_path


class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


def _wait_for(predicate, timeout=5.0):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_legacy_single_target_backward_compat():
    tmpdir = tempfile.mkdtemp()
    state_dir = tempfile.mkdtemp()
    try:
        config = {
            "upload": {
                "enabled": True, "state_dir": state_dir,
                "server_url": "https://old-style.example.com/api/v1/recordings/upload",
                "api_key": "old-style-key", "auth_header": "X-API-Key",
                "max_retries": 1, "retry_delay_seconds": 0.1,
                "delete_after_upload": True,
            }
        }
        wav_path, json_path = _make_recording(tmpdir)
        input_q = queue.Queue()

        pair_calls = []
        upload_calls = []
        def fake_post(url, **kwargs):
            if url.endswith("/devices/pair"):
                pair_calls.append((url, kwargs))
                return FakeResponse(201, {"device_id": "device-legacy-1"})
            upload_calls.append((url, kwargs))
            return FakeResponse(200)

        with mock.patch("requests.post", side_effect=fake_post):
            uploader = FileUploader(config, input_q)
            assert len(uploader.targets) == 1, "Legacy config should synthesize exactly one target"
            assert uploader.targets[0].type == "chirp-server"
            assert uploader.targets[0].server_url == "https://old-style.example.com/api/v1/recordings/upload"

            uploader.start()
            input_q.put({"wav_path": wav_path, "json_path": json_path, "event": None})
            _wait_for(lambda: len(upload_calls) >= 1)
            _wait_for(lambda: not os.path.exists(wav_path))
            uploader.stop()

        assert len(pair_calls) == 1, f"Should pair exactly once (lazy, on first upload) — paired {len(pair_calls)} times"
        assert len(upload_calls) == 1, f"Expected exactly 1 upload call, got {len(upload_calls)}"
        assert upload_calls[0][0] == "https://old-style.example.com/api/v1/recordings/upload"
        assert upload_calls[0][1]["headers"] == {"X-API-Key": "old-style-key"}
        assert not os.path.exists(wav_path), "File should be deleted after successful primary upload"
        print("PASS: legacy single-target config behaves identically to the pre-refactor uploader")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        shutil.rmtree(state_dir, ignore_errors=True)


def test_multi_target_fanout_and_real_failure_isolation():
    """The single most important test in this file: a broken SECOND
    target must never block or slow down the FIRST (primary) target's
    success, and must never prevent local file cleanup."""
    tmpdir = tempfile.mkdtemp()
    state_dir = tempfile.mkdtemp()
    try:
        config = {
            "upload": {
                "enabled": True, "state_dir": state_dir,
                "max_retries": 1, "retry_delay_seconds": 0.1, "delete_after_upload": True,
                "targets": [
                    {
                        "name": "primary-good", "type": "chirp-server", "enabled": True,
                        "server_url": "https://good.example.com/upload",
                        "api_key": "good-key", "auth_header": "X-API-Key",
                    },
                    {
                        "name": "secondary-broken", "type": "chirp-server", "enabled": True,
                        "server_url": "https://broken.example.com/upload",
                        "api_key": "broken-key", "auth_header": "X-API-Key",
                    },
                ],
            }
        }
        wav_path, json_path = _make_recording(tmpdir)
        input_q = queue.Queue()

        calls = []
        def fake_post(url, **kwargs):
            calls.append(url)
            if "broken" in url:
                raise ConnectionError("simulated: this server is unreachable")
            return FakeResponse(200)

        with mock.patch("requests.post", side_effect=fake_post):
            uploader = FileUploader(config, input_q)
            assert len(uploader.targets) == 2
            uploader.start()
            input_q.put({"wav_path": wav_path, "json_path": json_path, "event": None})

            # The PRIMARY target's success (and the resulting file
            # deletion) must happen even though the broken secondary is
            # still retrying in the background — waiting up to 3s, well
            # under the broken target's own multi-second retry backoff,
            # confirms the primary genuinely isn't waiting on it.
            deleted = _wait_for(lambda: not os.path.exists(wav_path), timeout=3.0)
            uploader.stop()

        assert deleted, "CRITICAL: local file was not deleted promptly — primary target may be blocked by the broken secondary"
        assert any("good" in c for c in calls), "Primary target was never called"
        assert any("broken" in c for c in calls), "Secondary target was never even attempted"
        print("PASS: a broken secondary target does not block the primary target's success or local file cleanup — real, structural failure isolation")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        shutil.rmtree(state_dir, ignore_errors=True)


def test_chirp_server_pairs_once_then_caches_device_id():
    """
    chirp-server's own lazy pairing (added after a real report — see
    uploader.py's own comment on _upload_chirp_server): pairing failure
    never blocks the upload itself, but a successful pairing's device_id
    should still be cached and reused, not re-requested on every upload.
    """
    tmpdir = tempfile.mkdtemp()
    state_dir = tempfile.mkdtemp()
    try:
        config = {
            "upload": {
                "enabled": True, "state_dir": state_dir,
                "max_retries": 1, "retry_delay_seconds": 0.1, "delete_after_upload": False,
                "targets": [
                    {
                        "name": "server-test", "type": "chirp-server", "enabled": True,
                        "server_url": "http://localhost:8800/api/v1/recordings/upload",
                        "api_key": "test_device_key",
                        "auth_header": "X-API-Key",
                    },
                ],
            }
        }
        input_q = queue.Queue()
        pair_calls = []
        upload_calls = []

        def fake_post(url, **kwargs):
            if url.endswith("/devices/pair"):
                pair_calls.append(kwargs.get("json"))
                return FakeResponse(201, {"device_id": "device-abc-123"})
            if url.endswith("/recordings/upload"):
                upload_calls.append({"headers": kwargs.get("headers"), "data": kwargs.get("data")})
                return FakeResponse(200)
            raise AssertionError(f"Unexpected URL: {url}")

        with mock.patch("requests.post", side_effect=fake_post):
            uploader = FileUploader(config, input_q)
            uploader.start()

            wav1, json1 = _make_recording(tmpdir, "rec1")
            input_q.put({"wav_path": wav1, "json_path": json1, "event": None})
            _wait_for(lambda: len(upload_calls) >= 1)

            wav2, json2 = _make_recording(tmpdir, "rec2")
            input_q.put({"wav_path": wav2, "json_path": json2, "event": None})
            _wait_for(lambda: len(upload_calls) >= 2)

            uploader.stop()

        assert len(pair_calls) == 1, f"Should pair exactly ONCE, not once per upload — paired {len(pair_calls)} times"
        assert pair_calls[0]["api_key"] == "test_device_key"
        assert len(upload_calls) == 2
        for call in upload_calls:
            assert call["headers"]["X-API-Key"] == "test_device_key", "Every upload authenticates via the header, not the device_id"

        # Confirm the device_id genuinely persisted to disk, not just held in memory
        state_files = os.listdir(state_dir)
        assert len(state_files) == 1
        with open(os.path.join(state_dir, state_files[0])) as f:
            cached = json.load(f)
        assert cached["device_id"] == "device-abc-123"

        print("PASS: chirp-server target pairs exactly once, caches the device_id to disk, and every subsequent upload authenticates via the header without re-pairing")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        shutil.rmtree(state_dir, ignore_errors=True)


if __name__ == "__main__":
    print("=== Multi-target upload tests ===\n")
    test_legacy_single_target_backward_compat()
    test_multi_target_fanout_and_real_failure_isolation()
    test_chirp_server_pairs_once_then_caches_device_id()
    print("\n=== ALL TESTS PASS ===")
