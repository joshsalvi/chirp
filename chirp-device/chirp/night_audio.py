"""
Night audio for Nighthawk (server Settings → Experimental → Night flight calls).

Every 15 minutes each upload target is asked whether it wants night audio
(GET /api/v1/night-calls/accepting) and for which hours. Between those
hours the recording mix (the same audio as recordings) is resampled to
22.05 kHz, Nighthawk's rate, and written as 10-minute FLAC chunks to
~/chirp/night_audio. Each finished chunk is uploaded to every target that
accepts it, then deleted. A server that turns the feature off answers 410
and the chunk is dropped for it.

Upload failures are retried with backoff; if the backlog passes
max_backlog_gb the oldest chunks are dropped, so a long outage can't fill
the SD card. Nothing is recorded when no target accepts.

Cost: about 60-90 MB per hour of night (lossless FLAC at 22.05 kHz).
"""
import json
import logging
import os
import queue
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

PROBE_INTERVAL = 900          # seconds between "do you want night audio?" checks
OUT_RATE = 22050


def in_window(now_local: datetime, start: str, end: str) -> bool:
    """HH:MM window in local time; wraps midnight when start > end."""
    sh, sm = map(int, start.split(":")); eh, em = map(int, end.split(":"))
    t = now_local.hour * 60 + now_local.minute
    a, b = sh * 60 + sm, eh * 60 + em
    if a == b:
        return False
    return a <= t < b if a < b else (t >= a or t < b)


def _base_url(server_url: str) -> str:
    return server_url.split("/api/v1/", 1)[0].rstrip("/")


class NightAudio:
    def __init__(self, config: Dict, targets: List, in_rate: int):
        na = config.get("night_audio", {}) or {}
        self.enabled = bool(na.get("enabled", True))            # local kill switch
        self.dir = os.path.expanduser(na.get("dir", "~/chirp/night_audio"))
        self.max_backlog_bytes = float(na.get("max_backlog_gb", 3.0)) * 1e9
        self.targets = [t for t in targets if getattr(t, "enabled", False) and t.server_url and t.api_key]
        self.in_rate = int(in_rate)
        self._q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=400)
        self._running = threading.Event()
        self._accepting: Dict[str, Dict] = {}        # target name -> server answer
        self._last_probe = 0.0
        self._file = None
        self._file_path: Optional[str] = None
        self._file_start: Optional[datetime] = None
        self._file_samples = 0
        self._resampler = None
        self._threads: List[threading.Thread] = []
        self.stats = {"chunks_written": 0, "chunks_uploaded": 0, "chunks_dropped": 0, "frames_dropped": 0}

    # ── Feed from AudioCapture's merger thread (must never block) ──────────
    def feed(self, chunk: np.ndarray) -> None:
        if self._file is None:
            return
        try:
            self._q.put_nowait(chunk)
        except queue.Full:
            self.stats["frames_dropped"] += 1

    def start(self) -> None:
        if not self.enabled or not self.targets:
            return
        os.makedirs(self.dir, exist_ok=True)
        self._running.set()
        for name, fn in (("NightAudioWriter", self._writer_loop), ("NightAudioUploader", self._upload_loop)):
            th = threading.Thread(target=fn, name=name, daemon=True)
            th.start(); self._threads.append(th)
        logger.info("Night audio: watching %d server(s) for night flight-call requests", len(self.targets))

    def stop(self) -> None:
        self._running.clear()
        self._close_file()

    # ── Which servers want audio, and when ──────────────────────────────────
    def _probe(self) -> None:
        import requests
        out = {}
        for t in self.targets:
            try:
                r = requests.get(f"{_base_url(t.server_url)}/api/v1/night-calls/accepting",
                                 headers={t.auth_header: t.api_key}, timeout=15)
                if r.status_code == 200 and r.json().get("enabled"):
                    out[t.name] = r.json()
            except Exception as e:
                logger.debug("Night audio probe failed for %s: %s", t.name, e)
        if set(out) != set(self._accepting):
            logger.info("Night audio requested by: %s", ", ".join(out) or "no server")
        self._accepting = out
        self._last_probe = time.monotonic()

    def _active_now(self) -> bool:
        from zoneinfo import ZoneInfo
        for cfg in self._accepting.values():
            try:
                now = datetime.now(ZoneInfo(cfg.get("timezone") or "UTC"))
                if in_window(now, cfg.get("start", "21:00"), cfg.get("end", "05:00")):
                    return True
            except Exception:
                continue
        return False

    def _chunk_seconds(self) -> float:
        mins = [float(c.get("chunk_minutes", 10)) for c in self._accepting.values()] or [10.0]
        return min(mins) * 60

    # ── Writing ─────────────────────────────────────────────────────────────
    def _open_file(self) -> None:
        import soundfile as sf
        import soxr
        self._file_start = datetime.now(timezone.utc)
        stamp = self._file_start.strftime("%Y%m%dT%H%M%SZ")
        self._file_path = os.path.join(self.dir, f"night_{stamp}.flac.part")
        self._resampler = soxr.ResampleStream(self.in_rate, OUT_RATE, 1, dtype="float32")
        self._file_samples = 0
        self._file = sf.SoundFile(self._file_path, "w", samplerate=OUT_RATE, channels=1,
                                  format="FLAC", subtype="PCM_16")

    def _close_file(self) -> None:
        f, path = self._file, self._file_path
        self._file = None
        if f is None:
            return
        try:
            tail = self._resampler.resample_chunk(np.zeros(0, np.float32), last=True)
            if len(tail):
                f.write(tail); self._file_samples += len(tail)
        except Exception:
            pass
        f.close()
        dur = self._file_samples / OUT_RATE
        if dur < 5:
            os.remove(path)
            return
        final = path[:-5]
        os.rename(path, final)
        with open(final + ".json", "w") as m:
            json.dump({"started_at": self._file_start.isoformat().replace("+00:00", "Z"),
                       "duration_seconds": round(dur, 2), "sample_rate": OUT_RATE,
                       "device_serial": os.uname().nodename, "done": []}, m)
        self.stats["chunks_written"] += 1
        logger.info("Night audio: chunk ready (%.0f s) %s", dur, os.path.basename(final))

    def _writer_loop(self) -> None:
        while self._running.is_set():
            try:
                if time.monotonic() - self._last_probe > PROBE_INTERVAL or not self._last_probe:
                    self._probe()
                active = self._active_now()
                if active and self._file is None:
                    # drain anything queued while idle, then start a chunk
                    while not self._q.empty():
                        self._q.get_nowait()
                    self._open_file()
                elif not active and self._file is not None:
                    self._close_file()
                if self._file is None:
                    time.sleep(5)
                    continue
                try:
                    x = self._q.get(timeout=1.0)
                except queue.Empty:
                    continue
                y = self._resampler.resample_chunk(np.asarray(x, dtype=np.float32))
                if len(y):
                    self._file.write(np.clip(y, -1.0, 1.0))
                    self._file_samples += len(y)
                if self._file_samples >= self._chunk_seconds() * OUT_RATE:
                    self._close_file()
            except Exception as e:
                logger.warning("Night audio writer error: %s", e)
                self._close_file()
                time.sleep(10)

    # ── Uploading ───────────────────────────────────────────────────────────
    def _pending(self) -> List[str]:
        return sorted(os.path.join(self.dir, f) for f in os.listdir(self.dir) if f.endswith(".flac"))

    def _enforce_backlog(self) -> None:
        files = self._pending()
        total = sum(os.path.getsize(f) for f in files)
        while files and total > self.max_backlog_bytes:
            old = files.pop(0)
            total -= os.path.getsize(old)
            self._drop(old)
            self.stats["chunks_dropped"] += 1
            logger.warning("Night audio: backlog over limit, dropped %s", os.path.basename(old))

    def _drop(self, path: str) -> None:
        for p in (path, path + ".json"):
            try:
                os.remove(p)
            except OSError:
                pass

    def _upload_loop(self) -> None:
        import requests
        backoff = 30
        while self._running.is_set():
            try:
                self._enforce_backlog()
                files = self._pending()
                if not files or not self._accepting:
                    time.sleep(30); continue
                path = files[0]
                meta_path = path + ".json"
                meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
                done = set(meta.get("done", []))
                failed = False
                for t in self.targets:
                    if t.name in done or t.name not in self._accepting:
                        continue
                    with open(path, "rb") as f:
                        r = requests.post(
                            f"{_base_url(t.server_url)}/api/v1/night-calls/upload",
                            headers={t.auth_header: t.api_key},
                            data={k: str(meta[k]) for k in ("started_at", "duration_seconds", "sample_rate", "device_serial") if k in meta},
                            files={"file": (os.path.basename(path), f, "audio/flac")}, timeout=300)
                    if r.status_code in (200, 201, 202, 410, 400, 401, 413):
                        if r.status_code >= 400:
                            logger.warning("Night audio: %s answered %d (%s); not retrying this chunk there",
                                           t.name, r.status_code, r.text[:120])
                        done.add(t.name)
                    else:
                        failed = True
                        logger.warning("Night audio upload to %s failed: HTTP %d", t.name, r.status_code)
                meta["done"] = sorted(done)
                if all(t.name in done or t.name not in self._accepting for t in self.targets):
                    self._drop(path)
                    self.stats["chunks_uploaded"] += 1
                    backoff = 30
                else:
                    json.dump(meta, open(meta_path, "w"))
                if failed:
                    time.sleep(backoff); backoff = min(backoff * 2, 1800)
            except Exception as e:
                logger.warning("Night audio upload error: %s", e)
                time.sleep(backoff); backoff = min(backoff * 2, 1800)

    def status(self) -> Dict:
        return {"accepting": sorted(self._accepting), "recording": self._file is not None,
                "backlog": len(self._pending()) if os.path.isdir(self.dir) else 0, **self.stats}
