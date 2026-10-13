"""
BirdWatch Recording Engine

Handles triggered recordings with:
  - Pre-roll: captures audio BEFORE the trigger (from circular buffer)
  - Post-trigger: continues recording for configured duration
  - Activity extension: extends recording if bird keeps calling
  - Stereo output: left=mic1, right=mic2 (or dual-mono if only one mic)
  - JSON metadata sidecar alongside each WAV file
  - Disk space management: enforces max_disk_gb limit
"""

import json
import logging
import queue
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import soundfile as sf

from .audio import AudioCapture
from .detector import DetectionEvent
from .utils import (
    auto_delete_old_recordings,
    get_disk_usage_gb,
    get_free_disk_gb,
    local_now,
)

logger = logging.getLogger(__name__)


# ── Metadata ──────────────────────────────────────────────────────────────────

@dataclass
class RecordingMetadata:
    """Metadata saved alongside each WAV recording."""
    filename: str
    trigger_timestamp_utc: str
    trigger_timestamp_local: str
    duration_seconds: float
    sample_rate: int
    channels: int
    pre_roll_seconds: float
    detections: List[Dict]
    max_confidence: float
    top_species: str
    energy_db: float
    device_count: int
    software_version: str = "1.0.0"

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), indent=indent, default=str)


# ── Recording Request ─────────────────────────────────────────────────────────

@dataclass
class RecordingRequest:
    """Placed on the recording queue by the detection pipeline."""
    event: DetectionEvent
    requested_at: float = field(default_factory=time.monotonic)


# ── Recording Engine ──────────────────────────────────────────────────────────

class RecordingEngine:
    """
    Listens for DetectionEvents and produces WAV recordings.

    One recording runs at a time; if a new detection fires during recording,
    the recording is extended (up to max_duration_seconds).

    Recordings are placed in a queue for the FileUploader to handle.
    """

    def __init__(
        self,
        config: Dict,
        audio_capture: AudioCapture,
        output_queue: queue.Queue,
    ):
        self.config = config
        self.audio = audio_capture
        self.output_queue = output_queue  # Completed recordings land here

        self.sample_rate: int = config["audio"]["sample_rate"]
        self.output_dir: str = config["recording"]["output_dir"]
        self.duration: float = config["recording"]["duration_seconds"]
        self.pre_roll: float = config["detection"]["pre_roll_seconds"]
        self.extend_on_activity: bool = config["recording"]["extend_on_activity"]
        self.extension_seconds: float = config["recording"]["extension_seconds"]
        self.max_duration: float = config["recording"]["max_duration_seconds"]
        self.normalize: bool = config["recording"]["normalize_output"]
        self.sidecar: bool = config["recording"]["include_metadata_sidecar"]
        self.max_disk_gb: float = config["recording"]["max_disk_gb"]
        self.auto_delete_days: int = config["recording"]["auto_delete_days"]

        # Current recording state
        self._recording_lock = threading.Lock()
        self._is_recording = False
        self._extend_deadline: float = 0.0  # monotonic time to stop recording

        # Trigger queue
        self._trigger_queue: queue.Queue = queue.Queue(maxsize=20)

        # Thread
        self._thread: Optional[threading.Thread] = None
        self._running = threading.Event()

        # Stats
        self.stats = {
            "recordings_completed": 0,
            "recordings_skipped_disk_full": 0,
            "total_seconds_recorded": 0.0,
            "extensions_applied": 0,
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the recording thread."""
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        self._running.set()
        self._thread = threading.Thread(
            target=self._recording_loop,
            name="RecordingEngine",
            daemon=True,
        )
        self._thread.start()
        logger.info("RecordingEngine started → %s", self.output_dir)

    def stop(self) -> None:
        """Stop the recording thread."""
        self._running.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=15.0)
        logger.info(
            "RecordingEngine stopped. Recordings: %d",
            self.stats["recordings_completed"],
        )

    def trigger(self, event: DetectionEvent) -> None:
        """
        Called by DetectionPipeline when a bird is detected.
        Thread-safe; non-blocking.
        """
        with self._recording_lock:
            if self._is_recording:
                if self.extend_on_activity:
                    new_deadline = time.monotonic() + self.extension_seconds
                    if new_deadline > self._extend_deadline:
                        self._extend_deadline = min(
                            new_deadline,
                            self._extend_deadline + self.max_duration,
                        )
                        self.stats["extensions_applied"] += 1
                        logger.debug(
                            "Recording extended by %.1fs (new deadline in %.1fs)",
                            self.extension_seconds,
                            self._extend_deadline - time.monotonic(),
                        )
                return  # Already recording; handled via extension

        # Enqueue new recording request
        try:
            self._trigger_queue.put_nowait(RecordingRequest(event=event))
        except queue.Full:
            logger.warning("Recording queue full; trigger dropped.")

    @property
    def is_recording(self) -> bool:
        with self._recording_lock:
            return self._is_recording

    # ── Recording Loop ────────────────────────────────────────────────────────

    def _recording_loop(self) -> None:
        """Main recording thread. Waits for requests, then records."""
        logger.debug("RecordingEngine thread started")

        # Run periodic cleanup on startup
        if self.auto_delete_days > 0:
            deleted = auto_delete_old_recordings(
                self.output_dir, self.auto_delete_days
            )
            if deleted:
                logger.info("Auto-deleted %d old recording(s)", deleted)

        while self._running.is_set():
            try:
                req = self._trigger_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                self._record(req)
            except Exception as e:
                logger.error(
                    "Recording error: %s", e, exc_info=True
                )
                with self._recording_lock:
                    self._is_recording = False

        logger.debug("RecordingEngine thread exiting")

    def _record(self, req: RecordingRequest) -> None:
        """Perform a single recording. Called from the recording thread."""

        # ── Disk space check ──────────────────────────────────────────────
        disk_used_gb = get_disk_usage_gb(self.output_dir)
        free_gb = get_free_disk_gb(self.output_dir)

        if disk_used_gb >= self.max_disk_gb:
            logger.warning(
                "Disk usage (%.1f GB) exceeds max_disk_gb (%.1f GB). "
                "Skipping recording. Free disk: %.1f GB",
                disk_used_gb, self.max_disk_gb, free_gb,
            )
            self.stats["recordings_skipped_disk_full"] += 1
            # Try to clean up
            if self.auto_delete_days > 0:
                auto_delete_old_recordings(self.output_dir, self.auto_delete_days)
            return

        if free_gb < 0.5:
            logger.warning(
                "Very low free disk space: %.2f GB. Skipping recording.", free_gb
            )
            self.stats["recordings_skipped_disk_full"] += 1
            return

        # ── Build filename ────────────────────────────────────────────────
        event = req.event
        ts = event.timestamp
        top = event.top_detection
        confidence = top.confidence if top else 0.0
        species_tag = (
            top.common_name.replace(" ", "-")[:20] if top else "Unknown"
        )
        # Sanitize species tag for filename
        species_tag = "".join(c for c in species_tag if c.isalnum() or c == "-")

        base_name = (
            f"birdwatch_{ts.strftime('%Y%m%d_%H%M%S')}"
            f"_{species_tag}"
            f"_{confidence:.2f}"
        )
        wav_path = Path(self.output_dir) / f"{base_name}.wav"
        json_path = Path(self.output_dir) / f"{base_name}.json"

        # ── Set recording state ───────────────────────────────────────────
        recording_start = time.monotonic()
        with self._recording_lock:
            self._is_recording = True
            self._extend_deadline = recording_start + self.duration

        logger.info(
            "▶ Recording started: %s | %s",
            wav_path.name,
            event.species_summary,
        )

        # ── Collect audio ─────────────────────────────────────────────────
        # Pre-roll + new audio are both pulled from AudioCapture's own rolling
        # buffer in one shot at the end (see "Assemble full audio" below), so
        # there's nothing to manually accumulate here — this loop just waits
        # until the recording deadline (or an extension) is reached.
        chunk_interval = self.config["audio"]["chunk_size"] / self.sample_rate

        while self._running.is_set():
            with self._recording_lock:
                deadline = self._extend_deadline
                max_end = recording_start + self.max_duration

            if time.monotonic() >= min(deadline, max_end):
                break

            # Get the latest stereo chunk from audio (poll at chunk rate)
            time.sleep(chunk_interval)
            # We'll snapshot the complete stereo at the end for simplicity
            # (AudioCapture maintains its own rolling buffer)

        recording_end = time.monotonic()
        actual_duration = recording_end - recording_start

        with self._recording_lock:
            self._is_recording = False

        # ── Assemble full audio ───────────────────────────────────────────
        total_seconds = self.pre_roll + actual_duration
        # get_stereo_recording always returns shape (N, 2) — 2-channel stereo
        # regardless of how many physical devices are open. Single-device
        # setups get L=R=mono duplicated into both channels. Always write
        # a 2-channel WAV for consistency; the server already expects stereo.
        audio_out = self.audio.get_stereo_recording(total_seconds)
        n_channels = 2

        if audio_out.shape[0] == 0:
            logger.warning("No audio captured for recording; skipping file write.")
            return
        real_duration = len(audio_out) / self.sample_rate
        if abs(real_duration - actual_duration) > 0.05:
            logger.warning(
                "Recording duration mismatch: wall-clock estimate was %.2fs, "
                "actual written audio is %.2fs — using actual for metadata "
                "(pre-roll buffer likely hadn't fully accumulated, or "
                "per-channel buffers had drifted)",
                actual_duration, real_duration,
            )
        actual_duration = real_duration

        # Optional normalization
        if self.normalize:
            peak = np.max(np.abs(audio_out))
            if peak > 0:
                audio_out = (audio_out / peak * 0.95).astype(np.float32)

        # ── Write WAV ─────────────────────────────────────────────────────
        try:
            sf.write(
                str(wav_path),
                audio_out,
                self.sample_rate,
                subtype="PCM_16",
            )
            file_size_mb = wav_path.stat().st_size / (1024 * 1024)
            logger.info(
                "■ Recording saved: %s (%.1fs, %.1f MB)",
                wav_path.name,
                actual_duration,
                file_size_mb,
            )
        except Exception as e:
            logger.error("Failed to write WAV file %s: %s", wav_path, e)
            return

        # ── Write JSON sidecar ────────────────────────────────────────────
        if self.sidecar:
            metadata = RecordingMetadata(
                filename=wav_path.name,
                trigger_timestamp_utc=event.timestamp.isoformat(),
                trigger_timestamp_local=local_now().isoformat(),
                duration_seconds=actual_duration,
                sample_rate=self.sample_rate,
                channels=n_channels,
                pre_roll_seconds=self.pre_roll,
                detections=[
                    {
                        "common_name": d.common_name,
                        "scientific_name": d.scientific_name,
                        "label": d.label,
                        "confidence": round(d.confidence, 4),
                        "start_time": d.start_time,
                        "end_time": d.end_time,
                    }
                    for d in event.detections
                ],
                max_confidence=event.max_confidence,
                top_species=event.top_detection.common_name if event.top_detection else "Unknown",
                energy_db=round(event.energy_db, 2),
                device_count=self.audio.device_count,
            )
            try:
                with open(json_path, "w") as f:
                    f.write(metadata.to_json())
            except Exception as e:
                logger.warning("Failed to write sidecar JSON %s: %s", json_path, e)

        self.stats["recordings_completed"] += 1
        self.stats["total_seconds_recorded"] += actual_duration

        # ── Hand off to uploader ──────────────────────────────────────────
        try:
            self.output_queue.put_nowait({
                "wav_path": str(wav_path),
                "json_path": str(json_path) if self.sidecar else None,
                "event": event,
                "duration": actual_duration,
            })
        except queue.Full:
            logger.warning("Upload queue full; recording will remain local only.")
