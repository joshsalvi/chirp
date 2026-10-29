"""
BirdWeather sync
================
Imports the sound from a BirdWeather station (PUC, BirdNET-Pi or
BirdNET-Go reporting to app.birdweather.com) every 15 minutes, as Chirp
recordings from a virtual device. Same shape as bird_buddy_sync.py: the
audio is downloaded, converted to a 48 kHz mono WAV and analysed by Chirp's
own BirdNET pass like an upload, so scores, spectrograms and species pages
match the rest of Chirp. BirdWeather's own species list isn't copied.

API (https://app.birdweather.com/api/v1, station token in the path):
  GET /stations/{token}/soundscapes?limit=&cursor=&from=
      -> {"soundscapes": [{"id", "timestamp", "duration", "url", ...}]}
  Newest first; `cursor` is the id of the last one on the page.

Only soundscapes after AppSettings.birdweather_cursor_at are fetched (the
first sync goes back FIRST_SYNC_HOURS), so a recording deleted in Chirp
isn't brought back. Recording.birdweather_soundscape_id also guards
against importing one twice.
"""
import hashlib
import json
import logging
import os
import subprocess
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

logger = logging.getLogger("chirp.birdweather_sync")

API_BASE = "https://app.birdweather.com/api/v1"
POLL_INTERVAL_SECONDS = 15 * 60
FIRST_SYNC_HOURS = 24
PAGE_SIZE = 100
MAX_PAGES = 5            # up to 500 soundscapes a sync; the rest come next time
PLATFORM = "BirdWeather"
BACKEND = "birdweather"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_time(ts: str) -> Optional[datetime]:
    """BirdWeather timestamps carry an offset ("2026-10-28T07:12:03.000-04:00"); naive UTC out."""
    if not ts:
        return None
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        return t
    return t.astimezone(timezone.utc).replace(tzinfo=None)


def station_key(token: str) -> str:
    """Stable id for the virtual device that doesn't reveal the token."""
    return hashlib.sha256(token.strip().encode()).hexdigest()[:12]


class BirdWeatherSyncService:
    def __init__(self):
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="birdweather-sync")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._run_sync_all_instances()
            except Exception as e:
                logger.warning("BirdWeather sync error: %s", e)
            self._stop.wait(POLL_INTERVAL_SECONDS)

    def _run_sync_all_instances(self):
        try:
            from ..instance_registry import iter_instance_sessions
        except ImportError:          # chirp-server: one site
            self.run_sync()
            return
        for instance, db in iter_instance_sessions():
            db.close()
            try:
                self.run_sync()
            except Exception as e:
                logger.warning("BirdWeather sync error for instance %s (%s): %s", instance.id, instance.name, e)

    # ── One sync ──────────────────────────────────────────────────────────

    def run_sync(self) -> int:
        """Imports new soundscapes for the current site. Returns how many."""
        from ..database import SessionLocal
        from ..models import AppSettings

        with SessionLocal() as db:
            s = db.query(AppSettings).filter(AppSettings.id == 1).first()
            enabled = bool(getattr(s, "birdweather_enabled", False)) if s else False
            token = (getattr(s, "birdweather_token", None) or "").strip() if s else ""
            since = getattr(s, "birdweather_cursor_at", None) if s else None
        if not enabled or not token:
            return 0

        with self._lock:
            try:
                items = self.fetch_soundscapes(token, since or _utcnow() - timedelta(hours=FIRST_SYNC_HOURS))
            except Exception as e:
                logger.warning("BirdWeather: could not reach the API: %s", e)
                self._record(error=_describe(e))
                self._set_device_status(token, online=False)
                return 0

            with SessionLocal() as db:
                device = self._ensure_virtual_device(db, token)
                db.commit()
                device_id = device.id

            imported, newest = 0, since
            for sc in sorted(items, key=lambda x: x.get("timestamp") or ""):
                ts = parse_time(sc.get("timestamp"))
                try:
                    if self.import_soundscape(sc, device_id):
                        imported += 1
                except Exception as e:
                    logger.warning("BirdWeather: soundscape %s not imported: %s", sc.get("id"), e)
                    break           # retry from here next time
                if ts and (newest is None or ts > newest):
                    newest = ts
            self._record(error=None, cursor=newest)
            if imported:
                logger.info("BirdWeather: imported %d soundscape(s)", imported)
            return imported

    # ── API ───────────────────────────────────────────────────────────────

    def fetch_soundscapes(self, token: str, since: datetime) -> list:
        """Soundscapes newer than `since` (naive UTC), newest pages first."""
        out, cursor = [], None
        url = f"{API_BASE}/stations/{token}/soundscapes"
        with httpx.Client(timeout=20, headers={"User-Agent": "Chirp (ourchirp.com)"}) as c:
            for _ in range(MAX_PAGES):
                params = {"limit": PAGE_SIZE, "from": since.replace(tzinfo=timezone.utc).isoformat()}
                if cursor:
                    params["cursor"] = cursor
                r = c.get(url, params=params)
                if r.status_code in (401, 403, 404):
                    raise PermissionError("BirdWeather didn't accept the station token")
                r.raise_for_status()
                page = (r.json() or {}).get("soundscapes") or []
                fresh = [p for p in page if (parse_time(p.get("timestamp")) or since) > since]
                out.extend(fresh)
                if len(page) < PAGE_SIZE or len(fresh) < len(page):
                    break
                cursor = page[-1].get("id")
        return out

    def check(self, token: str) -> dict:
        """For Settings → Test: whether the token works and how recent the last sound is."""
        items = self.fetch_soundscapes(token.strip(), _utcnow() - timedelta(days=7))
        latest = max((x.get("timestamp") or "" for x in items), default=None)
        return {"ok": True, "soundscapes_last_7_days": len(items), "latest": latest}

    # ── Import ────────────────────────────────────────────────────────────

    def import_soundscape(self, sc: dict, device_id: str) -> bool:
        from ..config import settings
        from ..database import SessionLocal
        from ..models import Recording

        sid = str(sc.get("id") or "")
        url = sc.get("url")
        ts = parse_time(sc.get("timestamp"))
        if not sid or not url or not ts:
            return False
        with SessionLocal() as db:
            if db.query(Recording).filter(Recording.birdweather_soundscape_id == sid).first():
                return False

        rec_id = str(uuid.uuid4())
        os.makedirs(settings.recordings_dir, exist_ok=True)
        raw = os.path.join(settings.recordings_dir, f"{rec_id}.bw")
        wav = os.path.join(settings.recordings_dir, f"{rec_id}.wav")
        try:
            with httpx.Client(timeout=60, follow_redirects=True) as c:
                r = c.get(url)
                r.raise_for_status()
                with open(raw, "wb") as f:
                    f.write(r.content)
            res = subprocess.run(["ffmpeg", "-y", "-i", raw, "-vn", "-ar", "48000", "-ac", "1",
                                  "-sample_fmt", "s16", "-f", "wav", wav], capture_output=True, timeout=120)
            if res.returncode != 0:
                raise RuntimeError("audio conversion failed: " + res.stderr.decode(errors="replace")[-200:])
        finally:
            try:
                os.remove(raw)
            except OSError:
                pass

        duration = float(sc.get("duration") or 0)
        try:
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", wav],
                                   capture_output=True, timeout=30)
            duration = float(json.loads(probe.stdout)["format"]["duration"])
        except Exception:
            pass

        with SessionLocal() as db:
            db.add(Recording(id=rec_id, filename=os.path.basename(wav), wav_path=wav, trigger_timestamp=ts,
                             duration_seconds=duration, sample_rate=48000, channels=1, device_id=device_id,
                             device_count=1, birdweather_soundscape_id=sid, processing_status="pending"))
            db.commit()

        from ..api.recordings import _process_manual_upload
        try:
            _process_manual_upload(rec_id)
        except Exception as e:
            logger.warning("BirdWeather: analysis failed for soundscape %s: %s", sid, e)
        return True

    # ── Device and status ─────────────────────────────────────────────────

    def _ensure_virtual_device(self, db, token: str):
        from ..models import Device
        host = f"birdweather:{station_key(token)}"
        device = db.query(Device).filter(Device.hostname == host).first()
        if device is None:
            device = Device(name="BirdWeather station", api_key_id=None, hostname=host, platform=PLATFORM,
                            birdnet_backend=BACKEND, status="online", last_seen=_utcnow())
            db.add(device)
            db.flush()
            logger.info("BirdWeather: created virtual device (id=%s)", device.id)
        else:
            device.last_seen = _utcnow()
            device.status = "online"
        return device

    def _set_device_status(self, token: str, online: bool):
        from ..database import SessionLocal
        from ..models import Device
        with SessionLocal() as db:
            d = db.query(Device).filter(Device.hostname == f"birdweather:{station_key(token)}").first()
            if d:
                d.status = "online" if online else "offline"
                db.commit()

    def _record(self, error: Optional[str], cursor: Optional[datetime] = None):
        from ..database import SessionLocal
        from ..models import AppSettings
        with SessionLocal() as db:
            s = db.query(AppSettings).filter(AppSettings.id == 1).first()
            if not s:
                return
            s.birdweather_last_sync_at = _utcnow()
            s.birdweather_last_sync_error = (error or None) and error[:500]
            if cursor:
                s.birdweather_cursor_at = cursor
            db.commit()


def _describe(e: Exception) -> str:
    if isinstance(e, PermissionError):
        return str(e)
    if isinstance(e, httpx.HTTPStatusError):
        return f"BirdWeather answered {e.response.status_code}"
    return f"Couldn't reach BirdWeather: {e.__class__.__name__}"


_service: Optional[BirdWeatherSyncService] = None


def get_sync_service() -> BirdWeatherSyncService:
    global _service
    if _service is None:
        _service = BirdWeatherSyncService()
    return _service
