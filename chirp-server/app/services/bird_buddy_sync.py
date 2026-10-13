"""
Bird Buddy Sync Service
========================
Polls the Bird Buddy account (via the reverse-engineered pybirdbuddy
GraphQL client — no official API exists) every POLL_INTERVAL_SECONDS for
new postcards and imports them as real Chirp Recordings, analyzed through
the exact same BirdNET pipeline manual audio uploads use.

Bird Buddy has a real, in-built microphone (confirmed directly against
Bird Buddy's own product specs and support docs — https://mybirdbuddy.com/
product/smart-bird-feeder-pro/ lists "Audio: High Fidelity Microphone";
https://support.mybirdbuddy.com/.../Sound-Recording confirms audio capture
is on by default and toggleable). Audio is NOT a separate file — it's the
embedded audio track of each postcard's video. There is no standalone
audio endpoint in the API at all: `Media` objects only expose
`content_url` (full media) and `thumbnail_url`. Audio is extracted to a
real, standalone WAV file via ffmpeg immediately after download (48kHz
mono 16-bit PCM, same normalization ffmpeg already does for manual
bird-audio uploads), rather than leaving `Recording.wav_path` pointing at
the source video — matching how device recordings are stored (real,
directly playable audio, with real spectrograms). The original video is
preserved separately (`Recording.bird_buddy_video_path`) for future
photo/video support, not discarded.

Bird Buddy's own species ID (via its `sightingReport`) is intentionally
NOT used to populate Detection rows — Chirp runs its OWN BirdNET analysis
on the extracted audio instead, for the same reason Haikubox recordings
run through Chirp's pipeline rather than trusting the source's own ID:
consistent confidence scoring and species-profile linkage across every
recording in the system, regardless of source.

One account can own multiple feeders (`bb.feeders`); which ones sync is
configurable via AppSettings.bird_buddy_selected_feeders (list of feeder
ids; empty/None = sync all). Each selected feeder gets its own virtual
Device row, same pattern as the single Haikubox virtual device.

Deduplication key: Media.id, stored in Recording.bird_buddy_media_id —
prevents re-importing the same postcard's video across polling cycles.
Postcards are finished (via finish_postcard, RECOGNIZED strategy) after
successful import, both to reflect Bird Buddy's own collection state
accurately and so new_postcards() naturally stops returning them —
without this, "opened postcards only" would silently stall an
unattended sync loop forever (the exact failure mode ha-birdbuddy's own
auto-collect blueprint exists to avoid).
"""

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("chirp.bird_buddy_sync")

POLL_INTERVAL_SECONDS = 15 * 60  # 15 minutes — matches Haikubox's cadence


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BirdBuddySyncService:
    """Background thread that polls the Bird Buddy account for new postcards."""

    def __init__(self):
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ── Public control ───────────────────────────────────────────────────

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="bird-buddy-sync"
        )
        self._thread.start()
        logger.info("Bird Buddy sync service started (poll every %dm)", POLL_INTERVAL_SECONDS // 60)

    def stop(self):
        self._stop.set()

    # ── Internal loop ────────────────────────────────────────────────────

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._run_sync()
            except Exception as e:
                logger.warning("Bird Buddy sync error: %s", e, exc_info=True)
                self._record_error(str(e))
            self._stop.wait(POLL_INTERVAL_SECONDS)

    def _run_sync(self):
        from ..database import SessionLocal
        from ..models import AppSettings

        with SessionLocal() as db:
            s = db.query(AppSettings).filter(AppSettings.id == 1).first()
            enabled = bool(getattr(s, "bird_buddy_enabled", False)) if s else False
            email = getattr(s, "bird_buddy_email", None) if s else None
            password = getattr(s, "bird_buddy_password", None) if s else None
            selected = getattr(s, "bird_buddy_selected_feeders", None) if s else None

        if not enabled or not email or not password:
            return

        import asyncio
        asyncio.run(self._async_sync(email, password, selected))

    async def _async_sync(self, email: str, password: str, selected_feeders: Optional[list]):
        from birdbuddy.client import BirdBuddy
        from ..database import SessionLocal

        try:
            bb = BirdBuddy(email, password)
            await bb.refresh()
        except Exception as e:
            logger.warning("Bird Buddy: could not reach API: %s", e)
            self._mark_devices_offline()
            raise

        # Touch/ensure a virtual device for every relevant feeder on every
        # successful poll — independent of whether any postcards exist
        # this cycle. Most 15-minute windows will have zero new bird
        # visits (no camera-triggered postcard), and previously
        # _ensure_virtual_device only ran from inside the postcard loop
        # below, so last_seen only ever advanced when a bird actually
        # showed up — not when the sync itself was healthy. That's the
        # real root cause of devices reading "offline" on the Devices page
        # even with Bird Buddy enabled and syncing fine: is_online()'s
        # threshold doesn't matter if last_seen never gets touched at all
        # during quiet periods. haikubox_sync.py already gets this right
        # (_update_device_status(online=True) runs even when a poll
        # returns zero detections) — this brings Bird Buddy in line with
        # that same pattern.
        with SessionLocal() as db:
            for feeder_id, feeder_obj in bb.feeders.items():
                if selected_feeders and feeder_id not in selected_feeders:
                    continue
                self._ensure_virtual_device(db, feeder_id, getattr(feeder_obj, "name", None) or "Bird Buddy")
            db.commit()

        postcards = await bb.new_postcards()
        imported = 0
        for postcard in postcards:
            try:
                sighting = await bb.sighting_from_postcard(postcard)
            except Exception as e:
                logger.warning("Bird Buddy: failed to load sighting for postcard %s: %s", postcard, e)
                continue

            feeder = sighting.feeder or {}
            feeder_id = feeder.get("id")
            if selected_feeders and feeder_id not in selected_feeders:
                continue  # not one of the selected devices

            video_medias = sighting.video_media
            if not video_medias:
                continue  # photo-only postcard — no audio possible, nothing for Chirp to analyze

            with SessionLocal() as db:
                device = self._ensure_virtual_device(db, feeder_id, feeder.get("name") or "Bird Buddy")
                db.commit()
                device_id = device.id

            for media in video_medias:
                if await self._import_media(media, device_id, feeder_id):
                    imported += 1

            try:
                await bb.finish_postcard(postcard.node_id, sighting)
            except Exception as e:
                logger.warning("Bird Buddy: failed to finish postcard %s (will retry next sync): %s", postcard.node_id, e)

        self._record_success(imported)

    async def _import_media(self, media, device_id: str, feeder_id: str) -> bool:
        """
        Downloads one video's audio-bearing file and queues it through the
        real BirdNET pipeline. Returns True if a new Recording was created.
        """
        from ..database import SessionLocal
        from ..models import Recording
        from ..config import settings
        from ..api.recordings import _process_manual_upload

        with SessionLocal() as db:
            existing = db.query(Recording).filter(Recording.bird_buddy_media_id == media.id).first()
            if existing:
                return False

        url = media.content_url
        if not url:
            return False

        import httpx, uuid as _uuid, subprocess, json as _json
        rec_id = str(_uuid.uuid4())
        video_dir = os.path.join(settings.recordings_dir, "birdbuddy_originals")
        os.makedirs(video_dir, exist_ok=True)
        video_path = os.path.join(video_dir, f"{rec_id}.mp4")
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                with open(video_path, "wb") as f:
                    f.write(resp.content)
        except Exception as e:
            logger.warning("Bird Buddy: failed to download media %s: %s", media.id, e)
            return False

        # Extract audio to a real, standalone WAV immediately — matching how
        # device recordings are stored (wav_path pointing at real, playable
        # audio) rather than leaving wav_path pointing at the source .mp4
        # forever. _process_manual_upload does its OWN separate ffmpeg
        # normalization for BirdNET's specific format needs, but never
        # updates rec.wav_path to point at that normalized copy — it's used
        # internally for analysis only, not treated as the recording's
        # canonical audio. A bare mp4 as wav_path would still often play in
        # a browser <audio> tag, but waveform/spectrogram code paths and the
        # audio-serving endpoint both assume this is real, standalone audio,
        # not "audio that happens to be muxed into a video file also
        # containing an unrelated video track" — extracting up front avoids
        # relying on every downstream consumer tolerating that difference.
        wav_path = os.path.join(settings.recordings_dir, f"{rec_id}.wav")
        try:
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", video_path, "-vn", "-ar", "48000", "-ac", "1",
                 "-sample_fmt", "s16", "-f", "wav", wav_path],
                capture_output=True, timeout=60,
            )
            if result.returncode != 0:
                logger.warning("Bird Buddy: audio extraction failed for media %s: %s",
                                media.id, result.stderr.decode()[-300:])
                return False
        except Exception as e:
            logger.warning("Bird Buddy: audio extraction error for media %s: %s", media.id, e)
            return False

        # Real duration, probed from the extracted audio — Recording.duration_seconds
        # is NOT NULL, and _process_manual_upload (unlike the initial upload
        # endpoint, which already has a real value by the time it creates the
        # Recording) never corrects it after the fact; that's a separate, manually-
        # triggered admin repair tool, not part of the normal processing flow.
        duration_seconds = 0.0
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "json", wav_path],
                capture_output=True, timeout=30,
            )
            duration_seconds = float(_json.loads(probe.stdout)["format"]["duration"])
        except Exception as e:
            logger.warning("Bird Buddy: could not probe duration for media %s: %s", media.id, e)

        with SessionLocal() as db:
            rec = Recording(
                id=rec_id,
                filename=os.path.basename(wav_path),
                wav_path=wav_path,
                trigger_timestamp=media.created_at or _utcnow(),
                duration_seconds=duration_seconds,
                device_id=device_id,
                bird_buddy_media_id=media.id,
                bird_buddy_video_path=video_path,  # preserved for future photo/video support
                processing_status="pending",
            )
            db.add(rec)
            db.commit()

        try:
            _process_manual_upload(rec_id)
        except Exception as e:
            logger.warning("Bird Buddy: BirdNET analysis failed for media %s: %s", media.id, e, exc_info=True)
        return True

    # ── Virtual device management ───────────────────────────────────────

    def _ensure_virtual_device(self, db, feeder_id: Optional[str], feeder_name: str):
        from ..models import Device

        device = None
        if feeder_id:
            device = db.query(Device).filter(Device.bird_buddy_feeder_id == feeder_id).first()
        if device is None:
            device = Device(
                name=feeder_name,
                api_key_id=None,  # virtual device — no API key
                bird_buddy_feeder_id=feeder_id,
                hostname=f"birdbuddy:{feeder_id}" if feeder_id else None,
                platform="Bird Buddy",
                birdnet_backend="bird_buddy",
                status="online",
                last_seen=_utcnow(),
            )
            db.add(device)
            db.flush()
            logger.info("Bird Buddy: created virtual device '%s' (id=%s)", feeder_name, device.id)
        else:
            device.name = feeder_name
            device.last_seen = _utcnow()
            device.status = "online"
        return device

    # ── Status tracking ─────────────────────────────────────────────────

    def _mark_devices_offline(self):
        """
        Marks all Bird Buddy virtual devices offline after a genuine API
        failure (bad credentials, network unreachable, etc). Deliberately
        does NOT touch last_seen — unlike haikubox_sync.py's
        _update_device_status(), which updates last_seen on both the
        online and offline branches. Since Device.is_online() (models.py)
        recomputes purely from the last_seen delta on every page load,
        touching last_seen here would make this explicit status="offline"
        write immediately revert back to "online" the next time anyone
        loads the Devices page — the same latent bug worth checking for on
        the Haikubox side too, just not fixed here since it wasn't the
        reported symptom.
        """
        from ..database import SessionLocal
        from ..models import Device
        with SessionLocal() as db:
            devices = db.query(Device).filter(Device.birdnet_backend == "bird_buddy").all()
            for d in devices:
                d.status = "offline"
            db.commit()

    def _record_success(self, imported: int):
        from ..database import SessionLocal
        from ..models import AppSettings
        with SessionLocal() as db:
            s = db.query(AppSettings).filter(AppSettings.id == 1).first()
            if s:
                s.bird_buddy_last_sync_at = _utcnow()
                s.bird_buddy_last_sync_error = None
                db.commit()
        if imported:
            logger.info("Bird Buddy: imported %d new recording(s)", imported)

    def _record_error(self, error: str):
        from ..database import SessionLocal
        from ..models import AppSettings
        with SessionLocal() as db:
            s = db.query(AppSettings).filter(AppSettings.id == 1).first()
            if s:
                s.bird_buddy_last_sync_at = _utcnow()
                s.bird_buddy_last_sync_error = error[:500]
                db.commit()


_service_instance: Optional[BirdBuddySyncService] = None


def get_sync_service() -> BirdBuddySyncService:
    global _service_instance
    if _service_instance is None:
        _service_instance = BirdBuddySyncService()
    return _service_instance
