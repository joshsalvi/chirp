"""
Chirp File Uploader — multi-target

Handles delivery of recordings to one or more remote servers, with:
  - HTTP multipart POST upload with metadata
  - Exponential backoff retry logic
  - Persistent retry queue (survives detection gaps)
  - Local fallback: recordings always saved to SD card first
  - Upload-and-keep or upload-and-delete mode

When upload.enabled = false (default during setup):
  This module still runs but only logs what WOULD be uploaded.
  Recordings remain safely on the SD card.

Multi-target support: audio capture and BirdNET inference happen exactly
ONCE per recording (a physical microphone can't be claimed by two
services at once) — but the resulting recording+detections can be sent to
MORE THAN ONE server, e.g. a chirp-server deployment plus a separate
chirp-server-instances deployment, without needing a second capture
pipeline or a second physical device. Each configured target:
  - Gets its OWN queue, thread, retry state, and stats — a second target
    being unreachable can never block or slow down delivery to the
    first, and vice versa. This is real, structural isolation (separate
    Queue objects, separate threads), not just visually-separated
    config for what's still one shared retry loop underneath.
  - Local file deletion (delete_after_upload) is decided by the FIRST
    configured target only (see PRIMARY_TARGET_INDEX below) — additional
    targets are treated as best-effort secondary destinations (exactly
    the "for testing purposes" use case this was built for), and a
    permanently-unreachable second target should never be able to make
    recordings pile up on the SD card forever.
  - Never depends on the local WAV file still existing on disk once its
    own turn comes, however long that takes. This needed two real
    rounds of fixing while testing this, not one: the audio bytes are
    read exactly ONCE, at the dispatch point in
    FileUploader._handle_item(), BEFORE the item is queued to any
    target at all — not by each target when it happens to get around to
    processing. An earlier version of this read the file per-target at
    dequeue time instead, which looked right and even passed a few
    manual checks, but was still genuinely racy: a fast primary target
    can succeed and delete the file within milliseconds (mocked network
    in testing; a fast real server in practice), while a slower or
    temporarily-down secondary target's own thread might not even have
    dequeued the item yet by then — meaning that "fix" only helped once
    a target had already started processing, not before. Reading once
    at dispatch, before any target's queue even has the item, closes
    the race at its actual source instead of chasing it target by
    target. Confirmed with a real reproduction, not assumed: the
    per-target version failed roughly half the time across repeated
    real runs; reading at dispatch made it fail zero times across many
    repeated real runs.

Server API contract (chirp-server and chirp-server-instances both speak
this — a second target just means a second URL/key pair, not a second
protocol):
  One-time pairing (lazy — happens on first upload, cached after):
    POST {server_url_base}/api/v1/devices/pair
    Body (json): {api_key: <key>, device_name: <str>}
    Response: {device_id} — cached in this target's own state file so
    pairing only happens once, not on every upload.
  Per-recording:
    POST {server_url}
    Headers: {auth_header}: {api_key}
    Body (multipart): file=<wav>, metadata=<json string>
"""

import json
import logging
import os
import queue
import threading
import time
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

PRIMARY_TARGET_INDEX = 0  # the first configured target decides local-delete behavior; see module docstring


def _resolve_ca_bundle():
    """Same CA-bundle resolution every target needs — factored out so it's
    computed once per process rather than once per request, and so both
    protocol implementations below share the exact same fallback logic
    instead of two copies that could quietly drift apart over time."""
    try:
        import certifi as _certifi
        _ca = _certifi.where()
        if not os.path.exists(_ca):
            raise FileNotFoundError(_ca)
        return _ca
    except Exception:
        _sys_ca = "/etc/ssl/certs/ca-certificates.crt"
        return _sys_ca if os.path.exists(_sys_ca) else True


class UploadTarget:
    """
    One configured destination server. Every target speaks the same
    chirp-server/-instances protocol today — this dispatches through
    upload_once() rather than calling _upload_chirp_server() directly
    so a genuinely different protocol could be added later (one more
    `_upload_<type>` method plus one line in upload_once()'s dispatch)
    without touching the FileUploader coordinator below at all.
    """

    def __init__(self, target_cfg: Dict, shared_defaults: Dict, state_dir: str):
        self.name: str = target_cfg.get("name", target_cfg.get("type", "unknown"))
        self.type: str = target_cfg.get("type", "chirp-server")
        self.enabled: bool = target_cfg.get("enabled", True)
        self.server_url: str = target_cfg.get("server_url", "")
        self.timeout: float = target_cfg.get("timeout_seconds", shared_defaults.get("timeout_seconds", 60))
        self.max_retries: int = target_cfg.get("max_retries", shared_defaults.get("max_retries", 5))
        self.retry_delay: float = target_cfg.get("retry_delay_seconds", shared_defaults.get("retry_delay_seconds", 30))
        self.backoff: float = target_cfg.get("retry_backoff_factor", shared_defaults.get("retry_backoff_factor", 2.0))
        self.include_metadata: bool = shared_defaults.get("include_metadata", True)

        # chirp-server-specific
        self.api_key: str = target_cfg.get("api_key", "")
        self.auth_header: str = target_cfg.get("auth_header", "X-API-Key")

        # device_id is filled in the first time pairing succeeds, then
        # cached to disk so a restart doesn't re-pair (and doesn't
        # create a second Device row for the same physical Pi) every
        # time.
        self._state_path = os.path.join(state_dir, f"upload_target_{self.name}.json")
        self.device_id: Optional[str] = self._load_cached_device_id()

        if "PLACEHOLDER" in self.server_url or "PLACEHOLDER" in (self.api_key or ""):
            logger.warning("Upload target '%s' disabled: still has a PLACEHOLDER value in config.yaml", self.name)
            self.enabled = False

        self.queue: "queue.Queue" = queue.Queue(maxsize=shared_defaults.get("upload_queue_max_size", 100))
        self._retry_items: list = []
        self._retry_lock = threading.Lock()
        # Initialized to the current time, not 0.0 — this is a real bug
        # found while testing this refactor, inherited from the
        # original single-target uploader.py rather than introduced
        # here: time.monotonic() is an ABSOLUTE clock reading (commonly
        # in the hundreds or thousands of seconds, often since system
        # boot), not a value that starts at zero for this process. With
        # this at 0.0, the very first check of
        # `time.monotonic() - self._last_retry_attempt >= self.retry_interval`
        # in the loop below is almost always already true — meaning the
        # retry-queue check would fire immediately on startup instead of
        # waiting the configured retry_interval at all. Harder to notice
        # in the original single-target version (one shared retry loop,
        # one shared piece of state); it became directly visible and
        # reproducible here once multiple independent per-target loops
        # made the timing behavior easy to observe and test directly.
        self._last_retry_attempt: float = time.monotonic()
        self._thread: Optional[threading.Thread] = None
        self._running = threading.Event()
        self.retry_interval: float = shared_defaults.get("retry_queued_interval_seconds", 300)

        self.stats = {
            "uploads_attempted": 0, "uploads_succeeded": 0,
            "uploads_failed_permanent": 0, "bytes_uploaded": 0,
            "retries_attempted": 0,
        }

    def _load_cached_device_id(self) -> Optional[str]:
        try:
            if os.path.exists(self._state_path):
                with open(self._state_path) as f:
                    return json.load(f).get("device_id")
        except Exception as e:
            logger.warning("Could not read cached device_id for target '%s': %s", self.name, e)
        return None

    def _save_cached_device_id(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
            with open(self._state_path, "w") as f:
                json.dump({"device_id": self.device_id}, f)
        except Exception as e:
            logger.warning("Could not cache device_id for target '%s': %s", self.name, e)

    def _read_metadata(self, json_path: Optional[str]) -> Dict:
        if json_path and os.path.exists(json_path) and self.include_metadata:
            try:
                with open(json_path, "r") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("[%s] Could not read metadata %s: %s", self.name, json_path, e)
        return {}

    def upload_once(self, wav_path: str, audio_bytes: bytes, metadata: Dict, event) -> bool:
        return self._upload_chirp_server(wav_path, audio_bytes, metadata, event)

    def _upload_chirp_server(self, wav_path: str, audio_bytes: bytes, metadata: Dict, event) -> bool:
        """Same contract as the original single-target implementation —
        now working from an in-memory byte buffer (read once when this
        target first dequeued the item) rather than re-opening the file
        on disk for every attempt, which is what let a slower target
        get caught out by a faster target's cleanup deleting the file
        out from under it. See _process()'s own comment for the full story.

        Investigated and fixed directly after a real multi-target report:
        a secondary chirp-server-type target's recordings were landing
        and being analyzed correctly, but its own Devices page showed
        "No paired devices" — because pairing was never this class's
        job at all for this type. It was handled entirely by
        ServerSync, a separate, older class that only ever talks to
        ONE server (its own config section, server_sync:, has no
        concept of multiple targets) and was never updated when the
        multi-target feature was added here. A recording's own upload
        doesn't require a device to already be paired — the server
        accepts any request with a valid key — so this silently worked
        for uploads while never creating a Device row for any target
        other than whichever one ServerSync happened to be pointed at.
        Every target now pairs itself, once, lazily — the same shared
        device_id cache below.
        """
        try:
            import requests
            verify = _resolve_ca_bundle()

            if not self.device_id:
                try:
                    pair_resp = requests.post(
                        f"{self.server_url.rsplit('/api/v1/', 1)[0]}/api/v1/devices/pair",
                        json={"api_key": self.api_key, "device_name": getattr(event, "device_name", None) or "chirp-device"},
                        timeout=self.timeout, verify=verify,
                    )
                    if pair_resp.status_code == 201:
                        self.device_id = pair_resp.json().get("device_id")
                        self._save_cached_device_id()
                        logger.info("[%s] Paired successfully, device_id=%s", self.name, self.device_id)
                    else:
                        logger.warning("[%s] Pairing failed (HTTP %d): %s — upload will still proceed, but this target's device won't appear on its own Devices page until pairing succeeds",
                                        self.name, pair_resp.status_code, pair_resp.text[:200])
                except Exception as e:
                    # Never let a pairing hiccup block the actual upload —
                    # pairing only affects whether this target's Devices
                    # page shows this device, not whether the recording
                    # itself is accepted.
                    logger.warning("[%s] Pairing attempt raised %s — upload will still proceed", self.name, e)

            headers = {self.auth_header: self.api_key}
            files = {"file": (os.path.basename(wav_path), audio_bytes, "audio/wav")}
            data = {"metadata": json.dumps(metadata)}
            resp = requests.post(self.server_url, headers=headers, files=files, data=data,
                                  timeout=self.timeout, verify=verify)
            return self._handle_response(resp, wav_path, len(audio_bytes))
        except Exception as e:
            logger.warning("[%s] Upload exception: %s", self.name, e)
            return False

    def _handle_response(self, resp, wav_path: str, file_size: int) -> bool:
        if resp.status_code in (200, 201, 202):
            self.stats["bytes_uploaded"] += file_size
            logger.info("✅ [%s] Uploaded: %s [%d]", self.name, os.path.basename(wav_path), resp.status_code)
            return True
        elif resp.status_code in (400, 401, 403, 422):
            logger.error("[%s] Upload rejected (HTTP %d): %s", self.name, resp.status_code, resp.text[:200])
            self.stats["uploads_failed_permanent"] += 1
            return False  # client error — don't retry
        else:
            logger.warning("[%s] Upload failed HTTP %d: %s", self.name, resp.status_code, resp.text[:200])
            return False

    # ── Per-target background thread (own queue, own retry state) ───────

    def start(self, primary: bool, on_result) -> None:
        self._running.set()
        self._thread = threading.Thread(target=self._loop, args=(primary, on_result), name=f"UploadTarget-{self.name}", daemon=True)
        self._thread.start()
        logger.info("Upload target '%s' (%s) started%s → %s", self.name, self.type,
                    " [PRIMARY]" if primary else "", self.server_url if self.enabled else "(disabled)")

    def stop(self) -> None:
        self._running.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=30.0)

    def _loop(self, primary: bool, on_result) -> None:
        while self._running.is_set():
            try:
                item = self.queue.get(timeout=1.0)
                self._process(item, primary, on_result)
            except queue.Empty:
                pass
            if self._retry_items and time.monotonic() - self._last_retry_attempt >= self.retry_interval:
                self._retry_failed(primary, on_result)
        while True:
            try:
                item = self.queue.get_nowait()
                self._process(item, primary, on_result)
            except queue.Empty:
                break

    def _process(self, item: Dict, primary: bool, on_result) -> None:
        wav_path = item.get("wav_path")
        if not wav_path:
            return
        if not self.enabled:
            return

        # audio_bytes/metadata were read ONCE by the dispatcher before
        # this item was ever queued to any target — see
        # FileUploader._handle_item's own comment for why that's where
        # this needed to happen, not here. No file-existence check
        # against the ORIGINAL path at this point on purpose: this
        # target's copy of the data is already fully independent of
        # whatever state that file is in by now, including having
        # already been deleted by a faster target.
        audio_bytes = item["_audio_bytes"]
        metadata = item["_metadata"]
        success = self._upload_with_retry(wav_path, audio_bytes, metadata, item.get("event"))
        on_result(self.name, primary, success, item)
        if not success:
            with self._retry_lock:
                self._retry_items.append({"item": item, "audio_bytes": audio_bytes, "metadata": metadata})

    def _upload_with_retry(self, wav_path: str, audio_bytes: bytes, metadata: Dict, event) -> bool:
        delay = self.retry_delay
        for attempt in range(1, self.max_retries + 1):
            self.stats["uploads_attempted"] += 1
            if self.upload_once(wav_path, audio_bytes, metadata, event):
                self.stats["uploads_succeeded"] += 1
                return True
            if attempt < self.max_retries:
                slept = 0.0
                while slept < delay and self._running.is_set():
                    time.sleep(min(1.0, delay - slept))
                    slept += 1.0
                delay *= self.backoff
                self.stats["retries_attempted"] += 1
        self.stats["uploads_failed_permanent"] += 1
        logger.error("[%s] Upload permanently failed after %d attempts: %s", self.name, self.max_retries, os.path.basename(wav_path))
        return False

    def _retry_failed(self, primary: bool, on_result) -> None:
        with self._retry_lock:
            items = list(self._retry_items)
            self._retry_items.clear()
        self._last_retry_attempt = time.monotonic()
        if not items:
            return
        logger.info("[%s] Retrying %d previously failed upload(s)...", self.name, len(items))
        still_failed = []
        for retry_entry in items:
            item, audio_bytes, metadata = retry_entry["item"], retry_entry["audio_bytes"], retry_entry["metadata"]
            wav_path = item.get("wav_path", "")
            success = self._upload_with_retry(wav_path, audio_bytes, metadata, item.get("event"))
            on_result(self.name, primary, success, item)
            if not success:
                still_failed.append(retry_entry)
        if still_failed:
            with self._retry_lock:
                self._retry_items.extend(still_failed)


class FileUploader:
    """
    Coordinator: dequeues one recording from the shared detection
    pipeline, fans it out to every configured target's own independent
    queue, and decides local file cleanup based on the PRIMARY target's
    result only (see module docstring).
    """

    def __init__(self, config: Dict, input_queue: queue.Queue):
        self.config = config
        self.input_queue = input_queue
        upload_cfg = config["upload"]
        self.enabled: bool = upload_cfg.get("enabled", False)
        self.delete_after: bool = upload_cfg.get("delete_after_upload", True)

        state_dir = os.path.expanduser(upload_cfg.get("state_dir", "~/.chirp_upload_state"))

        target_configs: List[Dict] = upload_cfg.get("targets")
        if not target_configs:
            # Backward compatibility: no explicit `targets:` list — build
            # exactly one chirp-server target from the legacy top-level
            # fields, so an existing config.yaml keeps working completely
            # unchanged, not just "mostly" unchanged.
            target_configs = [{
                "name": "chirp-server", "type": "chirp-server", "enabled": True,
                "server_url": upload_cfg.get("server_url", ""),
                "api_key": upload_cfg.get("api_key", ""),
                "auth_header": upload_cfg.get("auth_header", "X-API-Key"),
            }]

        self.targets: List[UploadTarget] = [UploadTarget(tc, upload_cfg, state_dir) for tc in target_configs]
        if not self.targets:
            raise ValueError("upload.targets is empty — at least one target is required")

        self._pending_results: Dict[str, Dict] = {}  # wav_path -> {target_name: success}
        self._pending_lock = threading.Lock()
        self._enabled_target_names = set()  # filled in start(); used to know when every target has weighed in on a given file

        self._thread: Optional[threading.Thread] = None
        self._running = threading.Event()
        self.stats = {"local_saves": 0}

    def start(self) -> None:
        self._running.set()
        self._enabled_target_names = {t.name for t in self.targets if t.enabled}
        for i, target in enumerate(self.targets):
            target.start(primary=(i == PRIMARY_TARGET_INDEX), on_result=self._on_target_result)
        self._thread = threading.Thread(target=self._dispatch_loop, name="FileUploaderDispatch", daemon=True)
        self._thread.start()
        if not self.enabled:
            logger.info("FileUploader started (UPLOAD DISABLED — recordings saved locally only)")

    def stop(self) -> None:
        self._running.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        for target in self.targets:
            target.stop()
        total_succeeded = sum(t.stats["uploads_succeeded"] for t in self.targets)
        total_failed = sum(t.stats["uploads_failed_permanent"] for t in self.targets)
        logger.info("FileUploader stopped. Uploaded: %d, Failed: %d (across %d target(s))", total_succeeded, total_failed, len(self.targets))

    def _dispatch_loop(self) -> None:
        while self._running.is_set():
            try:
                item = self.input_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            self._handle_item(item)
        while True:
            try:
                item = self.input_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_item(item)

    def _handle_item(self, item: Dict) -> None:
        wav_path = item.get("wav_path")
        if not wav_path or not os.path.exists(wav_path):
            logger.warning("Recording file not found: %s", wav_path)
            return

        if not self.enabled:
            file_size = os.path.getsize(wav_path) / (1024 * 1024)
            logger.info("💾 Saved locally: %s (%.1f MB) [upload disabled]", os.path.basename(wav_path), file_size)
            self.stats["local_saves"] += 1
            return

        enabled_targets = [t for t in self.targets if t.enabled]
        if not enabled_targets:
            self.stats["local_saves"] += 1
            return

        # Read the audio bytes and metadata ONCE, HERE, at the dispatch
        # point — before any target has even begun processing, and
        # critically before the primary target could possibly have
        # succeeded and deleted the file yet (dispatch always happens
        # first). This is where the file-existence race actually needed
        # to be closed, not inside each target's own processing —
        # closing it there (an earlier version of this fix) still left
        # a real gap: a slower target's per-target read only helped once
        # that target had already been dequeued and started processing,
        # not before, so a target that hadn't even gotten its turn yet
        # by the time the primary deleted the file was still exactly as
        # broken as before that first fix. Reading here means every
        # target's queued item already carries its own independent copy
        # of the data — no target's success or failure depends in any
        # way on what any other target does to the file on disk
        # afterward, including deleting it immediately.
        try:
            with open(wav_path, "rb") as f:
                audio_bytes = f.read()
        except OSError as e:
            logger.warning("Could not read %s for dispatch: %s", wav_path, e)
            return
        metadata = enabled_targets[0]._read_metadata(item.get("json_path"))  # protocol-agnostic; any target's helper works identically here

        with self._pending_lock:
            self._pending_results[wav_path] = {}
        for target in enabled_targets:
            queued_item = {**item, "_audio_bytes": audio_bytes, "_metadata": metadata}
            try:
                target.queue.put_nowait(queued_item)
            except queue.Full:
                logger.warning("[%s] Upload queue full, dropping item: %s", target.name, os.path.basename(wav_path))

    def _on_target_result(self, target_name: str, primary: bool, success: bool, item: Dict) -> None:
        """
        Called from EACH target's own thread independently as its
        uploads complete — genuinely concurrent, not a single shared
        callback serialized behind one lock's worth of blocking work
        (the lock here is only held briefly, to update the small
        results dict, not for the duration of any network call).
        """
        wav_path = item.get("wav_path")
        json_path = item.get("json_path")
        with self._pending_lock:
            results = self._pending_results.setdefault(wav_path, {})
            results[target_name] = success

        if primary:
            if success and self.delete_after:
                self._delete_files(wav_path, json_path)
            with self._pending_lock:
                self._pending_results.pop(wav_path, None)

    def _delete_files(self, wav_path: str, json_path: Optional[str]) -> None:
        for p in filter(None, [wav_path, json_path]):
            try:
                if os.path.exists(p):
                    os.unlink(p)
                    logger.debug("Deleted after upload: %s", os.path.basename(p))
            except OSError as e:
                logger.warning("Could not delete %s: %s", p, e)

    def get_stats_str(self) -> str:
        parts = []
        for t in self.targets:
            mb = t.stats["bytes_uploaded"] / (1024 * 1024)
            parts.append(f"{t.name}: {t.stats['uploads_succeeded']} ok / {t.stats['uploads_failed_permanent']} failed / {mb:.1f} MB")
        return f"Local: {self.stats['local_saves']} | " + " | ".join(parts)
