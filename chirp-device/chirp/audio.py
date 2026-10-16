"""
BirdWatch Audio Capture Module
Handles USB microphone discovery, ReSpeaker integration, capture, and pre-roll buffering.

Key fix: ReSpeaker XVF3800 (and v2.0/v2.1) only accepts 16000 Hz from PortAudio/ALSA.
We open the stream at the device's native rate and resample to the pipeline rate (48000 Hz)
in software using scipy.signal.resample_poly.  The rest of the pipeline sees 48000 Hz.
"""

import logging
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import sounddevice as sd

from .utils import merge_channels, snr_weighted_merge, rms_db

logger = logging.getLogger(__name__)

# Sample rates to try when probing a device, in preference order.
# XVF3800 only accepts 16000; older v2.0 accepts 16000 or 44100.
_CANDIDATE_RATES = [48000, 44100, 32000, 22050, 16000]


# ── AGC Disable ──────────────────────────────────────────────────────────────

def _alsa_card_for_device_name(device_name: str) -> Optional[int]:
    """
    Best-effort lookup of the ALSA card number for a device, by matching the
    first 12 characters of its PortAudio/sounddevice name against `arecord
    -l` output — same matching convention disable_device_agc() above already
    uses. Extracted into its own function so get_live_level_snapshot() can
    embed the real card number in its output, letting the server match
    "which card is chirp-device already using" by an exact integer instead
    of fuzzy name-substring matching (PortAudio's device name and arecord
    -l's card name are DIFFERENT strings describing the same hardware — the
    ReSpeaker in particular has historically been observed to differ enough
    that a name-substring match doesn't reliably find it). Returns None if
    arecord isn't available or no match is found — callers must treat this
    as best-effort, not guaranteed.
    """
    try:
        import subprocess as _sp
        result = _sp.run(["arecord", "-l"], capture_output=True, text=True, timeout=3)
        for line in result.stdout.splitlines():
            if "card" in line and device_name.lower()[:12] in line.lower():
                parts = line.split()
                idx = parts.index("card")
                card_str = parts[idx + 1].rstrip(":")
                if card_str.isdigit():
                    return int(card_str)
    except Exception:
        pass
    return None


def disable_device_agc(device_name: str, alsa_card_num: Optional[int] = None) -> None:
    """
    Attempt to disable Automatic Gain Control on a USB microphone.

    AGC causes the input level to be constantly readjusted, which produces the
    characteristic 'pumping' or 'cutting out' sound when a bird calls loudly:
    the AGC clamps down on loud audio, then slowly recovers, making the call
    appear to drop out mid-way.

    This is a best-effort call — not all USB mics expose AGC controls via ALSA,
    and failures are silently ignored so the pipeline continues normally.
    """
    import subprocess

    agc_control_names = [
        "Auto Gain Control",
        "AGC",
        "Automatic Gain Control",
        "Input Gain Control",
        "Mic AGC",
        "MIC AGC",
    ]

    def _try_amixer(card_arg: str) -> bool:
        success = False
        for ctrl in agc_control_names:
            try:
                result = subprocess.run(
                    ["amixer", "-c", card_arg, "sset", ctrl, "off"],
                    capture_output=True, timeout=2,
                )
                if result.returncode == 0:
                    logger.info("Disabled AGC control '%s' on card %s (%s)",
                                ctrl, card_arg, device_name)
                    success = True
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                pass
        return success

    if alsa_card_num is not None:
        _try_amixer(str(alsa_card_num))
        return

    # Try to find the ALSA card number from the device name
    found_card = _alsa_card_for_device_name(device_name)
    if found_card is not None:
        _try_amixer(str(found_card))
    else:
        logger.debug("AGC disable: could not determine ALSA card for '%s'", device_name)


# ── Device Discovery ──────────────────────────────────────────────────────────

@dataclass
class AudioDevice:
    index: int
    name: str
    max_input_channels: int
    default_samplerate: float

    def __str__(self) -> str:
        return f"[{self.index}] {self.name} ({self.max_input_channels}ch, {self.default_samplerate:.0f}Hz)"


def compute_excluded_cards(candidates: List["AudioDevice"], excludes: List[str]) -> set:
    """
    Resolves every candidate whose NAME matches device_name_excludes to its
    real ALSA card number, returning the set of card numbers to treat as
    reserved. Used alongside (not instead of) the name-substring check, to
    catch a confirmed real-world case: PortAudio can enumerate the SAME
    physical hardware under a completely different alias name than the one
    listed in device_name_excludes (observed on real hardware — an
    AudioMoth reserved via `device_name_excludes: ["AudioMoth"]` was ALSO
    being enumerated as a device literally named "speex", containing no
    "audiomoth" substring at all, which the name check alone could never
    catch). Card-number comparison is exact by construction and closes
    that gap regardless of how many different names the same hardware gets
    enumerated under.
    """
    excluded_cards: set = set()
    if not excludes:
        return excluded_cards
    for cand in candidates:
        if any(ex.lower() in cand.name.lower() for ex in excludes):
            card_num = _alsa_card_for_device_name(cand.name)
            if card_num is not None:
                excluded_cards.add(card_num)
    return excluded_cards


def is_candidate_excluded(dev: "AudioDevice", excludes: List[str], excluded_cards: set) -> Optional[str]:
    """
    Returns a human-readable reason string if `dev` should be excluded from
    bird-pipeline device claiming (either by name match or by resolving to
    an already-excluded ALSA card number under a different name), or None
    if it's fine to claim.
    """
    if excludes and any(ex.lower() in dev.name.lower() for ex in excludes):
        return "matches device_name_excludes"
    if excluded_cards:
        dev_card = _alsa_card_for_device_name(dev.name)
        if dev_card is not None and dev_card in excluded_cards:
            return (
                f"resolves to ALSA card {dev_card}, which matches an excluded device "
                f"by card number even though the name itself doesn't contain any "
                f"device_name_excludes substring — an aliased enumeration of the same "
                f"physical hardware as something already reserved"
            )
    return None


# ALSA-level pseudo/virtual PCM names that PortAudio always enumerates on Linux
# but that are never a real, separate physical microphone — they're routing
# views over OTHER underlying hardware (often the SAME hardware some other
# process already has open), or non-functional placeholders. Falling back to
# trying these is pointless: they were never going to capture bird audio, and
# attempting to open them floods the log with ALSA's own internal multi-card
# probing noise (the burst of "unable to open slave" lines for one open()
# call) without ever succeeding.
_ALSA_PSEUDO_DEVICE_TOKENS = (
    "sysdefault", "default", "spdif", "iec958", "hdmi", "dmix", "dsnoop",
    "pulse", "pipewire", "jack", "front", "surround", "lavrate",
    "samplerate", "speexrate", "speex", "upmix", "vdownmix", "modem", "null",
)


def _is_real_capture_device(name: str, max_input_channels: int) -> bool:
    """
    Heuristic filter for whether a PortAudio-enumerated input device could
    plausibly be a real, distinct microphone worth trying as a fallback.
    Excludes known ALSA pseudo-device name tokens and implausible channel
    counts (no real USB mic for this project has more than a handful of
    channels — 128ch readings are a known ALSA quirk indicating a broken/
    misconfigured virtual device, not a real one).
    """
    lname = name.lower()
    if any(tok in lname for tok in _ALSA_PSEUDO_DEVICE_TOKENS):
        return False
    if max_input_channels > 16:
        return False
    return True


def list_all_devices() -> List[AudioDevice]:
    devices = []
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            devices.append(AudioDevice(
                index=i,
                name=dev["name"],
                max_input_channels=dev["max_input_channels"],
                default_samplerate=dev["default_samplerate"],
            ))
    return devices


def list_real_fallback_devices() -> List[AudioDevice]:
    """list_all_devices(), minus known-bogus ALSA pseudo-devices. Use this for
    fallback candidate selection — list_all_devices() itself stays unfiltered
    since it also backs --list-devices, where showing everything (including
    oddities) is the whole point."""
    return [d for d in list_all_devices() if _is_real_capture_device(d.name, d.max_input_channels)]


def find_usb_devices(hints: List[str], max_devices: int) -> List[AudioDevice]:
    all_devices = list_all_devices()
    matched = []
    for dev in all_devices:
        if any(hint.lower() in dev.name.lower() for hint in hints):
            matched.append(dev)
            logger.info("Found USB microphone: %s", dev)
            if len(matched) >= max_devices:
                break
    if not matched:
        all_input = [
            f"  [{i}] {d['name']} (ch={d['max_input_channels']})"
            for i, d in enumerate(sd.query_devices())
            if d["max_input_channels"] > 0
        ]
        device_list = "\n".join(all_input) if all_input else \
            "  (none — no input devices seen by sounddevice)\n" \
            "  Fix: sudo usermod -aG audio $USER  then log out and back in\n" \
            "  Also check: arecord -l"
        logger.warning(
            "No USB microphones found matching hints %s. Available input devices:\n%s",
            hints, device_list,
        )
    return matched


def get_default_input_device() -> Optional[AudioDevice]:
    try:
        idx = sd.default.device[0]
        if idx is None or idx < 0:
            return None
        dev = sd.query_devices(idx)
        return AudioDevice(
            index=idx,
            name=dev["name"],
            max_input_channels=dev["max_input_channels"],
            default_samplerate=dev["default_samplerate"],
        )
    except Exception as e:
        logger.warning("Could not get default input device: %s", e)
        return None


def probe_device_sample_rate(device_index: int, n_channels: int,
                             preferred_rate: int) -> int:
    """
    Find the highest sample rate the device actually accepts.
    Returns the first working rate from _CANDIDATE_RATES, falling back to
    the device's default_samplerate if nothing works.
    """
    candidates = sorted(set([preferred_rate] + _CANDIDATE_RATES), reverse=True)
    for rate in candidates:
        try:
            sd.check_input_settings(device=device_index,
                                    channels=min(n_channels, 2),
                                    samplerate=rate,
                                    dtype="float32")
            return rate
        except Exception:
            continue
    # Last resort: whatever the device reports as its default
    try:
        return int(sd.query_devices(device_index)["default_samplerate"])
    except Exception:
        return 16000


# ── Shared live-level snapshot helper (used by status_server.py) ──────────────

def _level_snapshot_from_samples(
    samples: np.ndarray, name: str, role: str, sr: int, n_bins: int = 32,
    extra: Optional[dict] = None,
) -> dict:
    """
    Build the same {name, db, peak, bins, sr, ...} shape the old SSH/arecord
    diagnostic script produced, from an in-memory sample array instead of a
    fresh ALSA capture. Keeps the wire format identical so the frontend and
    the SSH-fallback path stay drop-in compatible with this source.
    """
    n = len(samples)
    if n == 0:
        result = {"name": name, "role": role, "sr": sr, "db": None, "peak": None,
                   "bins": [0] * n_bins, "error": "empty buffer"}
        if extra:
            result.update(extra)
        return result

    rms_lin = float(np.sqrt(np.mean(np.square(samples))))
    pk_lin = float(np.max(np.abs(samples)))
    db_rms = 20 * np.log10(rms_lin + 1e-10)
    db_pk = 20 * np.log10(pk_lin + 1e-10)

    chunk = max(1, n // n_bins)
    bins = []
    for b in range(n_bins):
        sl = samples[b * chunk:(b + 1) * chunk]
        bins.append(float(np.sqrt(np.mean(np.square(sl)))) if len(sl) else 0.0)
    mx = max(bins) if bins else 0.0
    bins = [int(v / mx * 255) for v in bins] if mx > 0 else [0] * n_bins

    result = {
        "name": name, "role": role, "sr": sr,
        "db": round(db_rms, 1), "peak": round(db_pk, 1), "bins": bins,
    }
    if extra:
        result.update(extra)
    return result


# ── Pre-roll Buffer ───────────────────────────────────────────────────────────

class PreRollBuffer:
    """Thread-safe circular buffer holding last N seconds of mono float32 audio."""

    def __init__(self, seconds: float, sample_rate: int, chunk_size: int):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        max_chunks = int(np.ceil(seconds * sample_rate / chunk_size)) + 4
        self._buf: deque = deque(maxlen=max_chunks)
        self._lock = threading.Lock()
        self._seconds = seconds

    def push(self, chunk: np.ndarray) -> None:
        with self._lock:
            self._buf.append(chunk.copy())

    def get_audio(self, seconds: Optional[float] = None) -> np.ndarray:
        with self._lock:
            chunks = list(self._buf)
        if not chunks:
            return np.array([], dtype=np.float32)
        audio = np.concatenate(chunks)
        if seconds is not None:
            n_samples = int(seconds * self.sample_rate)
            if len(audio) > n_samples:
                audio = audio[-n_samples:]
        return audio

    @property
    def buffered_seconds(self) -> float:
        with self._lock:
            return len(self._buf) * self.chunk_size / self.sample_rate


# ── Resampler ─────────────────────────────────────────────────────────────────

class _Resampler:
    """
    Lightweight streaming resampler using scipy.signal.resample_poly.
    Accumulates input samples and emits resampled chunks at the target rate.
    Thread-safe: intended to run only from the audio callback thread.
    """

    def __init__(self, in_rate: int, out_rate: int, chunk_out: int):
        from math import gcd
        g = gcd(in_rate, out_rate)
        self._up   = out_rate // g
        self._down = in_rate  // g
        self._chunk_out = chunk_out
        # Expected input samples to produce one output chunk
        self._chunk_in = int(np.ceil(chunk_out * in_rate / out_rate))
        self._buf = np.array([], dtype=np.float32)
        self._enabled = (in_rate != out_rate)

    def push(self, samples: np.ndarray) -> List[np.ndarray]:
        """Push raw samples; returns list of resampled output chunks (may be empty)."""
        if not self._enabled:
            return [samples]
        from scipy.signal import resample_poly
        self._buf = np.concatenate([self._buf, samples])
        out_chunks = []
        while len(self._buf) >= self._chunk_in:
            block = self._buf[:self._chunk_in]
            self._buf = self._buf[self._chunk_in:]
            resampled = resample_poly(block, self._up, self._down).astype(np.float32)
            # Emit in pipeline-sized chunks
            pos = 0
            while pos + self._chunk_out <= len(resampled):
                out_chunks.append(resampled[pos:pos + self._chunk_out])
                pos += self._chunk_out
            if pos < len(resampled):
                # Partial chunk — prepend back so it combines with next block
                self._buf = np.concatenate([resampled[pos:], self._buf])
        return out_chunks


# ── Per-Device Stream ─────────────────────────────────────────────────────────

class DeviceStream:
    """
    Wraps a sounddevice InputStream for one microphone.

    Handles:
    - Multi-channel ReSpeaker devices: channel extraction via ChannelPlan
    - Sample rate mismatch: opens at device native rate, resamples to pipeline rate
    - Mono and multi-channel callbacks
    """

    def __init__(
        self,
        device: AudioDevice,
        pipeline_rate: int,           # rate the rest of the pipeline expects (e.g. 48000)
        chunk_size: int,              # output chunk size at pipeline_rate
        gain_db: float = 0.0,
        channel_plan=None,            # respeaker.ChannelPlan or None
        force_channels: int = 1,
        device_native_rate: Optional[int] = None,  # if None, probe automatically
    ):
        self.device = device
        self.pipeline_rate = pipeline_rate
        self.chunk_size = chunk_size
        self.gain_linear = 10 ** (gain_db / 20.0)
        self.channel_plan = channel_plan
        self.force_channels = force_channels

        # Determine the actual rate to open the hardware stream at
        if device_native_rate is not None:
            self._hw_rate = device_native_rate
        else:
            self._hw_rate = pipeline_rate  # will be confirmed/corrected in start()

        # Resampler is created (or updated) in start() once we know _hw_rate
        self._resampler: Optional[_Resampler] = None

        self.queue: queue.Queue = queue.Queue(maxsize=100)
        self._stream: Optional[sd.InputStream] = None
        self._error_count = 0
        self._chunk_index = 0
        self._lock = threading.Lock()

    def set_gain_db(self, gain_db: float) -> None:
        """
        Update the gain applied to this already-running stream in place.
        gain_linear is read fresh from this instance attribute on every audio
        chunk in the capture callback, so a config push can change it without
        stopping or reopening the underlying hardware stream.
        """
        self.gain_linear = 10 ** (gain_db / 20.0)

    @property
    def sample_rate(self) -> int:
        """Pipeline-facing sample rate (post-resample)."""
        return self.pipeline_rate

    def start(self) -> bool:
        """Open the hardware stream, probing sample rate if needed."""
        n_ch = self.force_channels

        # If the stream was previously told a hw_rate but it might be wrong,
        # or if pipeline_rate != default_samplerate, probe what the device accepts.
        if self._hw_rate != self.pipeline_rate:
            # Already know the native rate — use it directly
            hw_rate = self._hw_rate
        else:
            # Try the preferred rate first; fall back if PortAudio refuses
            hw_rate = probe_device_sample_rate(self.device.index, n_ch, self.pipeline_rate)
            self._hw_rate = hw_rate

        if hw_rate != self.pipeline_rate:
            logger.info(
                "Device '%s' native rate %d Hz → resampling to %d Hz for pipeline",
                self.device.name, hw_rate, self.pipeline_rate
            )

        # Build resampler for this hw_rate → pipeline_rate
        self._resampler = _Resampler(hw_rate, self.pipeline_rate, self.chunk_size)

        # hw_chunk_size: how many frames to request from the device
        # Scale so we get roughly the same wall-clock chunk as the pipeline chunk
        hw_chunk = max(256, int(self.chunk_size * hw_rate / self.pipeline_rate))

        for attempt_ch in ([n_ch, 1] if n_ch > 1 else [1]):
            try:
                self._stream = sd.InputStream(
                    device=self.device.index,
                    channels=attempt_ch,
                    samplerate=float(hw_rate),
                    blocksize=hw_chunk,
                    dtype="float32",
                    latency="high",
                    callback=self._callback,
                    finished_callback=self._finished,
                )
                self._stream.start()
                if attempt_ch != n_ch:
                    logger.info("Stream opened in mono fallback for '%s'", self.device.name)
                    self.force_channels = 1
                    self.channel_plan = None
                    # Rebuild resampler with mono chunk size unchanged
                    self._resampler = _Resampler(hw_rate, self.pipeline_rate, self.chunk_size)
                logger.info(
                    "Opened stream: '%s' @ %d Hz %dch → pipeline %d Hz",
                    self.device.name, hw_rate, attempt_ch, self.pipeline_rate
                )
                return True
            except Exception as e:
                logger.error("Failed to open stream for %s @ %d Hz %dch: %s",
                             self.device, hw_rate, attempt_ch, e)
                _msg = str(e).lower()
                if any(s in _msg for s in (
                    "unable to open slave", "device or resource busy",
                    "device unavailable", "resource busy",
                )):
                    logger.error(
                        "  → This usually means another process already has '%s' open "
                        "exclusively. If the chirp systemd service is running, stop it "
                        "first: sudo systemctl stop chirp — then re-run this test, and "
                        "restart the service afterward with: sudo systemctl start chirp",
                        self.device.name,
                    )

        return False

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.debug("Error stopping stream %s: %s", self.device, e)
            self._stream = None

    @property
    def is_active(self) -> bool:
        return self._stream is not None and self._stream.active

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        """sounddevice callback — runs in real-time audio thread."""
        if status and status.input_overflow:
            self._error_count += 1
            if self._error_count == 1 or self._error_count % 100 == 0:
                logger.warning(
                    "Audio overflow on '%s' (count: %d) — "
                    "consider increasing audio.chunk_size in config.yaml",
                    self.device.name, self._error_count,
                )
            return

        # Extract mono from multi-channel (ReSpeaker channel plan)
        if self.channel_plan is not None and indata.ndim > 1:
            from .respeaker import extract_mono
            raw = extract_mono(indata, self.channel_plan)
        elif indata.ndim > 1:
            raw = indata[:, 0].copy()
        else:
            raw = indata.ravel().copy()

        raw = raw.astype(np.float32) * self.gain_linear

        # Resample if hw_rate != pipeline_rate
        chunks_out = self._resampler.push(raw) if self._resampler else [raw]

        with self._lock:
            for chunk in chunks_out:
                try:
                    idx = self._chunk_index
                    self._chunk_index += 1
                    self.queue.put_nowait((idx, chunk))
                except queue.Full:
                    pass  # pipeline lagging; drop

    def _finished(self) -> None:
        logger.warning("Stream finished (device disconnected?): %s", self.device)


# ── Audio Capture Manager ─────────────────────────────────────────────────────

class AudioCapture:
    """
    Main audio capture manager.

    Priority on start():
      1. ReSpeaker (if respeaker.mode != disabled)
      2. USB mics matching device_name_hints
      3. System default (if fallback_to_default=true)

    Streams open at native hardware rate and resample to pipeline_rate internally.
    The rest of the codebase always sees pipeline_rate (default 48000 Hz).
    """

    def __init__(self, config: Dict):
        self.config = config
        self.sample_rate: int = config["audio"]["sample_rate"]   # pipeline rate
        self.chunk_size: int = config["audio"]["chunk_size"]
        self.gain_db: float = config["audio"].get("input_gain_db", 0.0)
        self.pre_roll_seconds: float = config["detection"]["pre_roll_seconds"]

        self.analysis_window_seconds: float = (
            config["detection"]["birdnet"]["analysis_window_seconds"]
        )
        self.analysis_window_samples: int = int(
            self.analysis_window_seconds * self.sample_rate
        )

        self._streams: List[DeviceStream] = []
        self._devices_found: List[AudioDevice] = []
        self._respeaker_device = None

        self._pre_roll = PreRollBuffer(
            self.pre_roll_seconds + 1.0,
            self.sample_rate,
            self.chunk_size,
        )

        self._detection_accumulator: np.ndarray = np.array([], dtype=np.float32)
        self._detection_lock = threading.Lock()
        self._detection_queue: queue.Queue = queue.Queue(maxsize=10)
        self._overlap_throttled = False

        self._raw_buffers: Dict[int, deque] = {}
        self._raw_lock = threading.Lock()

        # How to mix multi-device audio for BirdNET analysis:
        #   "primary" — only the first/best device (ReSpeaker if present) [RECOMMENDED]
        #   "weighted" — all devices, weighted by current signal strength
        #   "all"     — equal average of all devices (legacy)
        self._detection_source: str = (
            config["audio"].get("detection_source", "primary").lower()
        )
        # Separate detection accumulator so detection always uses primary/weighted signal
        self._detect_accumulator: np.ndarray = np.array([], dtype=np.float32)
        self._detect_lock = threading.Lock()

        self._merger_thread: Optional[threading.Thread] = None
        self.night_sink = None        # set by BirdWatcher: gets every recording-mix chunk
        self._running = threading.Event()

        self.stats = {
            "chunks_merged": 0,
            "detection_windows_queued": 0,
            "detection_windows_dropped": 0,
            "stream_errors": 0,
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """
        Open all audio input streams, then start the merger.

        Device collection order:
          1. ReSpeaker (USB or HAT) — if respeaker.mode != disabled
          2. Additional USB mics matching device_name_hints (ReSpeaker excluded)
          3. System default fallback if still nothing

        All streams run concurrently and are mixed together, so using
        ReSpeaker + extra USB mics improves spatial coverage.
        """
        rs_mode = self.config.get("respeaker", {}).get("mode", "auto")
        max_devices = self.config["audio"]["max_devices"]
        # Raw buffer per device: holds enough for full recording duration.
        # pre_roll_seconds + max recording duration + generous margin so
        # get_stereo_recording can always retrieve a complete recording.
        # Previously was only pre_roll_seconds + 5.0 = 10s, which silently
        # truncated all recordings to ~10s regardless of configured duration.
        max_recording = self.config["recording"].get("max_duration_seconds", 120.0)
        raw_buf_seconds = self.pre_roll_seconds + max_recording + 10.0
        raw_buf_chunks = int(raw_buf_seconds * self.sample_rate / self.chunk_size)

        # Track device indices already claimed so USB scan won't double-open them
        claimed_indices: set = set()

        # ── Step 1: ReSpeaker ──────────────────────────────────────────────────
        if rs_mode.lower() != "disabled":
            try:
                from .respeaker import probe_respeaker
                rs_dev = probe_respeaker(rs_mode)
                if rs_dev is not None:
                    stream = self._build_respeaker_stream(rs_dev)
                    if stream is not None and stream.start():
                        self._respeaker_device = rs_dev
                        dev_key = (stream.device.index
                                   if isinstance(stream.device.index, int) else 0)
                        self._streams.append(stream)
                        self._devices_found.append(stream.device)
                        self._raw_buffers[dev_key] = deque(maxlen=raw_buf_chunks)
                        claimed_indices.add(dev_key)
                        logger.info("ReSpeaker stream active: %s | %s",
                                    rs_dev.display_name, rs_dev.channel_plan.description)
                    else:
                        logger.warning(
                            "ReSpeaker detected but stream failed — continuing with USB scan"
                        )
            except ImportError:
                logger.debug("respeaker module not available")

        # ── Step 2: Additional USB mics (skip indices already claimed) ─────────
        # Strategy: try hint-matched devices first (more likely to be mics), then
        # fall through to ALL remaining input devices so nothing is missed.
        remaining = max_devices - len(self._streams)
        if remaining > 0:
            hints = self.config["audio"]["device_name_hints"]
            # Build an ordered candidate list: hint-matched first, then everything else.
            # Note: extra/fallback candidates are filtered through
            # list_real_fallback_devices(), NOT the raw list_all_devices() —
            # the raw list includes ALSA pseudo-devices (sysdefault, spdif,
            # hdmi, etc.) that can never be a real microphone and that
            # previously got tried here, flooding the log with ALSA's
            # internal probing noise for devices that were never going to
            # work in the first place.
            hint_matched = find_usb_devices(hints, max_devices * 4)
            hint_indices = {d.index for d in hint_matched}
            all_inputs = list_real_fallback_devices()
            # Append devices not already in hint_matched (preserves order)
            extra = [d for d in all_inputs if d.index not in hint_indices]
            candidates = hint_matched + extra

            excludes = self.config["audio"].get("device_name_excludes", [])

            # Resolve every excluded device's real ALSA card number ONCE, up
            # front — reused for every candidate below. This is the actual
            # root-cause fix for a confirmed real-world conflict, verified
            # two ways: (1) direct evidence — the bird pipeline was found
            # holding the AudioMoth's ALSA device open under a completely
            # different enumerated name ("speex", no "audiomoth" substring
            # at all, invisible to the name-based exclude check), which is
            # exactly why the bat detector could never open the same
            # hardware afterward regardless of which sample rate it tried —
            # not a rate mismatch, not a PortAudio leak, just chirp-device's
            # own bird pipeline legally holding hardware the bat detector
            # needed. (2) confirmed conclusively — unplugging the physical
            # AudioMoth made BOTH "AudioMoth" and "speex" disappear from the
            # device list together, proving they were always the same
            # hardware under two different names, not two separate devices.
            # Name-substring matching alone can never catch this class of
            # bug since it's fundamentally two different strings describing
            # the same hardware — card-number matching is exact by
            # construction and closes the gap regardless of naming.
            excluded_cards = compute_excluded_cards(candidates, excludes)

            for dev in candidates:
                if remaining <= 0:
                    break
                if dev.index in claimed_indices:
                    continue
                # Real fix for a confirmed real-world conflict: the
                # fallback above is deliberately a SEPARATE, broader scan
                # than device_name_hints (so a legitimate mic that didn't
                # match a hint still gets picked up) — meaning narrowing
                # device_name_hints alone can't reserve a device for
                # another pipeline (e.g. the bat detector) if there's
                # still max_devices headroom, since this loop will happily
                # claim it anyway. device_name_excludes is checked here
                # specifically, independent of the hints list, so a
                # device can be reliably excluded from bird detection
                # regardless of how the broader fallback scan finds it —
                # by name AND (see compute_excluded_cards above) by an
                # aliased enumeration under a different name entirely.
                exclusion_reason = is_candidate_excluded(dev, excludes, excluded_cards)
                if exclusion_reason:
                    logger.info("Skipping '%s' — %s", dev.name, exclusion_reason)
                    continue
                stream = DeviceStream(
                    device=dev,
                    pipeline_rate=self.sample_rate,
                    chunk_size=self.chunk_size,
                    gain_db=self.gain_db,
                )
                if stream.start():
                    self._streams.append(stream)
                    self._devices_found.append(dev)
                    self._raw_buffers[dev.index] = deque(maxlen=raw_buf_chunks)
                    claimed_indices.add(dev.index)
                    remaining -= 1
                    logger.info("Added extra input device: %s", dev)
                    # Disable AGC on USB mics — prevents level-pumping dropouts
                    if self.config["audio"].get("disable_agc_on_start", True):
                        disable_device_agc(dev.name)

        # ── Step 3: Fallback to system default if still nothing ────────────────
        if not self._streams:
            if self.config["audio"]["fallback_to_default"]:
                default = get_default_input_device()
                if default and default.index not in claimed_indices:
                    stream = DeviceStream(
                        device=default,
                        pipeline_rate=self.sample_rate,
                        chunk_size=self.chunk_size,
                        gain_db=self.gain_db,
                    )
                    if stream.start():
                        self._streams.append(stream)
                        self._devices_found.append(default)
                        self._raw_buffers[default.index] = deque(maxlen=raw_buf_chunks)
                        logger.warning("Using system default input as fallback: %s", default)
            if not self._streams:
                logger.error(
                    "No audio streams could be opened. "
                    "Check: arecord -l   and   python main.py --list-devices"
                )
                return False

        # ── Start merger ──────────────────────────────────────────────────────
        names = [s.device.name.split(":")[0][:28] for s in self._streams]
        logger.info("Started %d audio stream(s): %s", len(self._streams), ", ".join(names))

        if len(self._streams) > 1:
            primary_name = self._streams[0].device.name.split(":")[0][:28]
            if self._detection_source == "primary":
                logger.info(
                    "Detection source: PRIMARY only (%s). "
                    "Other device(s) contribute to recording mix only.",
                    primary_name,
                )
            elif self._detection_source == "weighted":
                logger.info(
                    "Detection source: SNR-WEIGHTED mix of all %d devices.",
                    len(self._streams),
                )
            else:
                logger.info(
                    "Detection source: EQUAL mix of all %d devices "
                    "(consider setting detection_source: primary).",
                    len(self._streams),
                )

        self._start_merger()
        return True

    def _build_respeaker_stream(self, rs_dev) -> "Optional[DeviceStream]":
        """
        Build (but do NOT start) a DeviceStream for a ReSpeaker device.
        Returns None if the device cannot be configured.
        The caller is responsible for calling stream.start() and tracking state.
        """
        if rs_dev.mode == "usb":
            try:
                sd_info = sd.query_devices(rs_dev.sd_device_index)
            except Exception as e:
                logger.error("Cannot query ReSpeaker sd_index %s: %s",
                             rs_dev.sd_device_index, e)
                return None

            n_ch = rs_dev.channel_plan.total_channels
            if getattr(rs_dev.model, "value", rs_dev.model) == "usb_xvf3800":
                from .respeaker import configure_xvf3800
                self._xvf3800_mode_applied = self._xvf3800_output_mode()
                configure_xvf3800(rs_dev.channel_plan, self._xvf3800_mode_applied)
            native_rate = probe_device_sample_rate(
                rs_dev.sd_device_index, n_ch, self.sample_rate
            )
            logger.info(
                "ReSpeaker USB '%s': native=%d Hz → pipeline=%d Hz, %dch",
                rs_dev.display_name, native_rate, self.sample_rate, n_ch
            )
            audio_dev = AudioDevice(
                index=rs_dev.sd_device_index,
                name=rs_dev.sd_device_name or sd_info["name"],
                max_input_channels=sd_info["max_input_channels"],
                default_samplerate=native_rate,
            )
            return DeviceStream(
                device=audio_dev,
                pipeline_rate=self.sample_rate,
                chunk_size=self.chunk_size,
                gain_db=self.gain_db,
                channel_plan=rs_dev.channel_plan,
                force_channels=n_ch,
                device_native_rate=native_rate,
            )

        elif rs_dev.mode == "hat":
            sd_idx = None
            for i, dev in enumerate(sd.query_devices()):
                if dev["max_input_channels"] > 0:
                    if (rs_dev.alsa_device and
                            rs_dev.alsa_device.lower() in dev["name"].lower()):
                        sd_idx = i
                        break
                    if rs_dev.alsa_card is not None and str(rs_dev.alsa_card) in dev["name"]:
                        sd_idx = i
                        break

            if sd_idx is None:
                logger.warning(
                    "ReSpeaker HAT ALSA card %s not in sounddevice — using hw:N string",
                    rs_dev.alsa_card
                )
                sd_idx = f"hw:{rs_dev.alsa_card}"

            n_ch = rs_dev.channel_plan.total_channels
            native_rate = (
                probe_device_sample_rate(sd_idx, n_ch, self.sample_rate)
                if isinstance(sd_idx, int) else rs_dev.sample_rate
            )
            audio_dev = AudioDevice(
                index=sd_idx if isinstance(sd_idx, int) else 0,
                name=rs_dev.display_name,
                max_input_channels=n_ch,
                default_samplerate=native_rate,
            )
            return DeviceStream(
                device=audio_dev,
                pipeline_rate=self.sample_rate,
                chunk_size=self.chunk_size,
                gain_db=self.gain_db,
                channel_plan=rs_dev.channel_plan,
                force_channels=n_ch,
                device_native_rate=native_rate,
            )
        else:
            logger.error("Unknown ReSpeaker mode: %s", rs_dev.mode)
            return None

    def _start_merger(self) -> None:
        self._running.set()
        self._merger_thread = threading.Thread(
            target=self._merger_loop, name="AudioMerger", daemon=True
        )
        self._merger_thread.start()

    def stop(self) -> None:
        self._running.clear()
        for s in self._streams:
            s.stop()
        if self._merger_thread and self._merger_thread.is_alive():
            self._merger_thread.join(timeout=3.0)
        logger.info("AudioCapture stopped.")

    def update_gain(self, gain_db: float) -> None:
        """
        Apply a new input gain to every currently-running stream, in place.
        Without this, a server-pushed input_gain_db change had no effect
        until the next process restart — gain_linear was only ever computed
        once at stream-open time, and apply_config() merely logged the new
        value without touching the live AudioStream objects.
        """
        self.gain_db = gain_db
        for s in self._streams:
            s.set_gain_db(gain_db)
        logger.info("Audio gain updated to %.1f dB on %d running stream(s)", gain_db, len(self._streams))

    def _effective_overlap(self) -> float:
        """Configured overlap, cut to 1.0 s while BirdNET is backed up (night:
        the bat detector shares the CPU). Widening the hop keeps coverage
        (1 s overlap leaves no gaps between 3 s windows); dropping windows doesn't."""
        overlap = float(self.config["detection"]["birdnet"].get("overlap_seconds", 0.0))
        backlog = self._detection_queue.qsize()
        if overlap > 1.0 and backlog >= self._detection_queue.maxsize // 2:
            if not self._overlap_throttled:
                self._overlap_throttled = True
                self.stats["overlap_throttle_events"] = self.stats.get("overlap_throttle_events", 0) + 1
                logger.info("Detection backlog %d: overlap reduced to 1.0 s until it clears", backlog)
            return 1.0
        if self._overlap_throttled and backlog <= 1:
            self._overlap_throttled = False
            logger.info("Detection backlog cleared: overlap back to %.1f s", overlap)
        return 1.0 if self._overlap_throttled and overlap > 1.0 else overlap

    def _xvf3800_output_mode(self, config: Optional[Dict] = None) -> str:
        return str((config or self.config).get("respeaker", {}).get("xvf3800_output", "raw")).lower()

    def update_respeaker_output(self, config: Dict) -> None:
        """Hot-apply respeaker.xvf3800_output to a running XVF3800 stream."""
        rs = self._respeaker_device
        if rs is None or getattr(rs.model, "value", rs.model) != "usb_xvf3800":
            return
        mode = self._xvf3800_output_mode(config)
        if mode == getattr(self, "_xvf3800_mode_applied", None):
            return
        from .respeaker import configure_xvf3800
        desc = configure_xvf3800(rs.channel_plan, mode)
        self._xvf3800_mode_applied = mode
        logger.info("XVF3800 output set to %s: %s", mode, desc)

    @property
    def device_count(self) -> int:
        return len(self._streams)

    @property
    def is_running(self) -> bool:
        return self._running.is_set() and any(s.is_active for s in self._streams)

    @property
    def respeaker_info(self) -> Optional[str]:
        if self._respeaker_device:
            return str(self._respeaker_device)
        return None

    # ── Audio Access ──────────────────────────────────────────────────────────

    def get_pre_roll(self, seconds: Optional[float] = None) -> np.ndarray:
        return self._pre_roll.get_audio(seconds or self.pre_roll_seconds)

    def get_detection_window(self, timeout: float = 1.0) -> Optional[np.ndarray]:
        try:
            return self._detection_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_stereo_recording(self, seconds: float) -> np.ndarray:
        """Return interleaved stereo float32 audio for the last `seconds`.

        Always returns a shape-(N, 2) array regardless of device count, so
        the caller can unconditionally write it as a 2-channel WAV.

        Single-device: both channels contain the same mono signal (L=R).
        Two-device: left = device 0 (ReSpeaker), right = device 1.
        """
        n_samples = int(seconds * self.sample_rate)
        channels = []
        with self._raw_lock:
            for dev in self._devices_found[:len(self._streams)]:
                dev_key = dev.index if isinstance(dev.index, int) else 0
                if dev_key in self._raw_buffers:
                    raw = list(self._raw_buffers[dev_key])
                    if raw:
                        audio = np.concatenate(raw)[-n_samples:]
                        channels.append(audio)
        if not channels:
            return np.empty((0, 2), dtype=np.float32)
        if len(channels) == 1:
            c = channels[0]
            # Return (N, 2) with L=R=mono signal — not a flat interleaved
            # array. Previously returned len(c)*2 flat samples, which caused
            # recorder.py's reshape(-1, 1) to treat both copies as sequential
            # mono samples, doubling the apparent duration and producing
            # garbled/noisy audio. Confirmed via real recorded durations:
            # 9.898s recordings became 19.797s = exactly 2× wrong.
            stereo = np.empty((len(c), 2), dtype=np.float32)
            stereo[:, 0] = c
            stereo[:, 1] = c
            return stereo
        n = min(len(c) for c in channels)
        stereo = np.empty((n, 2), dtype=np.float32)
        stereo[:, 0] = channels[0][:n]
        stereo[:, 1] = channels[1][:n]
        return stereo

    def get_current_levels_db(self) -> List[Tuple[str, float]]:
        levels = []
        for s in self._streams:
            try:
                last_chunk = self._pre_roll.get_audio(0.1)
                db = rms_db(last_chunk) if len(last_chunk) > 0 else -np.inf
                levels.append((s.device.name, db))
            except Exception:
                levels.append((s.device.name, -np.inf))
        return levels

    def get_recent_audio_samples(self, seconds: float = 4.0) -> List[dict]:
        """
        Return the last `seconds` of RAW audio per already-open stream, from
        the exact same self._raw_buffers this capture already maintains for
        get_live_level_snapshot() above — same "read what we already
        captured, never open a second ALSA handle" reasoning applies here
        unchanged. Where that method reduces the buffered audio down to a
        level/spectrum summary, this one hands back the samples themselves, for
        a different purpose: letting someone on the server side
        LISTEN to what a specific mic is picking up (static,
        clipping, wrong mic selected, etc. — the kind of problem a level
        number alone doesn't reveal), not just see a number for it.

        Returns raw numpy float32 arrays in the `audio` key, NOT a
        JSON-serializable shape — this is meant to be consumed in-process
        by status_server.py, which turns it into a WAV response; keeping
        the array as-is here avoids the wasted work of encoding it twice
        (once for whatever calls this, once for the WAV itself) since
        status_server.py needs raw samples anyway to write WAV data.
        """
        if not hasattr(self, "_alsa_card_cache"):
            self._alsa_card_cache = {}
        for s in self._streams:
            if s.device.name not in self._alsa_card_cache:
                self._alsa_card_cache[s.device.name] = _alsa_card_for_device_name(s.device.name)

        out = []
        with self._raw_lock:
            for i, s in enumerate(self._streams):
                dev_key = s.device.index if isinstance(s.device.index, int) else 0
                alsa_card = self._alsa_card_cache.get(s.device.name)
                raw = list(self._raw_buffers.get(dev_key, []))
                if not raw:
                    out.append({
                        "name": s.device.name, "role": "bird",
                        "sd_index": s.device.index, "alsa_card": alsa_card, "sr": s.pipeline_rate,
                        "audio": None, "error": "no buffered audio yet",
                    })
                    continue
                audio = np.concatenate(raw)
                n_samples = int(seconds * s.pipeline_rate)
                if n_samples > 0 and len(audio) > n_samples:
                    audio = audio[-n_samples:]
                out.append({
                    "name": s.device.name, "role": "bird",
                    "sd_index": s.device.index, "alsa_card": alsa_card, "sr": s.pipeline_rate,
                    "audio": audio.copy(), "error": None,  # .copy() — leave with our own array, not a view into a buffer that keeps mutating after the lock releases
                })
        return out

    def get_live_level_snapshot(self, window_seconds: float = 0.3, n_bins: int = 32) -> List[dict]:
        """
        Return live RMS/peak/spectrum data for each already-open stream, computed
        entirely from in-memory buffers this capture is already maintaining
        (self._raw_buffers, per-device). No new ALSA device is opened.

        This exists specifically so the server's status endpoint (status_server.py)
        can serve live mic levels without a second process trying to grab the same
        hardware — that second-open approach (SSH + `arecord -D dsnoop:...`) fails
        on most USB audio class devices because chirp-device already holds the
        device via PortAudio's raw `hw:` open, which is exclusive; dsnoop-sharing
        only works when every opener (including the first) goes through dsnoop.
        Reading data we already captured sidesteps that limitation entirely.
        """
        # Resolve each stream's ALSA card number BEFORE taking the lock —
        # _alsa_card_for_device_name shells out to `arecord -l` (up to a 3s
        # timeout), and self._raw_lock is also held by the real-time audio
        # callback thread on every chunk (see the recording callback below).
        # Holding a slow subprocess call under that lock would risk stalling
        # live capture. Cached per-instance since a device's card number is
        # stable for the life of the process — no need to re-shell-out on
        # every poll tick (this method may be called every ~0.5-1.5s by the
        # server's local status polling).
        if not hasattr(self, "_alsa_card_cache"):
            self._alsa_card_cache = {}
        for s in self._streams:
            if s.device.name not in self._alsa_card_cache:
                self._alsa_card_cache[s.device.name] = _alsa_card_for_device_name(s.device.name)

        out = []
        with self._raw_lock:
            for i, s in enumerate(self._streams):
                dev_key = s.device.index if isinstance(s.device.index, int) else 0
                alsa_card = self._alsa_card_cache.get(s.device.name)
                raw = list(self._raw_buffers.get(dev_key, []))
                if not raw:
                    out.append({
                        "name": s.device.name, "role": "bird",
                        "sd_index": s.device.index, "alsa_card": alsa_card, "sr": s.pipeline_rate,
                        "db": None, "peak": None, "bins": [0] * n_bins,
                        "error": "no buffered audio yet",
                    })
                    continue
                audio = np.concatenate(raw)
                n_samples = int(window_seconds * s.pipeline_rate)
                if n_samples > 0 and len(audio) > n_samples:
                    audio = audio[-n_samples:]
                out.append(_level_snapshot_from_samples(
                    audio, name=s.device.name, role="bird",
                    sr=s.pipeline_rate, n_bins=n_bins,
                    extra={"sd_index": s.device.index, "alsa_card": alsa_card},
                ))
        return out

    # ── Merger Thread ─────────────────────────────────────────────────────────

    def _merger_loop(self) -> None:
        logger.debug("AudioMerger thread started")
        while self._running.is_set():
            chunks_this_round: Dict[int, np.ndarray] = {}

            # Paced by the first (primary) stream: wait for its next chunk,
            # then take whatever the other mics have ready. A mic with
            # nothing ready is left out of this round. Until 1.4.1 every
            # stream waited 0.15 s and a miss became a chunk of zeros, but
            # a 8192-sample chunk at 48 kHz takes 0.17 s to arrive, so about
            # half of what fed detection, the pre-roll level meter and night
            # audio was inserted silence (night clips came out "staccato":
            # 0.17 s and 0.34 s gaps every second). Recordings were fine:
            # they're cut from the raw per-mic buffers.
            for i, stream in enumerate(self._streams):
                got = []
                try:
                    if i == 0:
                        got.append(stream.queue.get(timeout=1.0)[1])
                    else:
                        while True:     # everything ready; the newest joins the mix
                            got.append(stream.queue.get_nowait()[1])
                except queue.Empty:
                    pass
                if not got:
                    if i == 0:
                        break
                    continue
                chunks_this_round[i] = got[-1]
                dev_key = stream.device.index if isinstance(stream.device.index, int) else 0
                with self._raw_lock:
                    if dev_key in self._raw_buffers:
                        self._raw_buffers[dev_key].extend(got)

            if 0 not in chunks_this_round:
                # Primary stream had nothing within a second (stalled or
                # stopped): keep the other mics' raw buffers fresh, nothing more.
                time.sleep(0.01)
                continue

            channel_arrays = list(chunks_this_round.values())
            n0 = len(channel_arrays[0])        # the primary sets the length
            channel_arrays = [channel_arrays[0]] + [
                c[:n0] if len(c) >= n0 else np.pad(c, (0, n0 - len(c))) for c in channel_arrays[1:]]

            # ── Recording mix: SNR-weighted so the best mic dominates the WAV ──
            if len(channel_arrays) == 1:
                record_mix = channel_arrays[0]
            else:
                record_mix = snr_weighted_merge(channel_arrays)
            self._pre_roll.push(record_mix)
            sink = self.night_sink          # night audio for Nighthawk (night_audio.py)
            if sink is not None:
                sink(record_mix)

            # ── Detection audio: use best source for BirdNET analysis ─────────
            src = self._detection_source
            if src == "primary" or len(channel_arrays) == 1:
                # Primary = first stream (ReSpeaker when present, since it's
                # always opened first in start()). Never diluted by weak mics.
                detect_chunk = channel_arrays[0]
            elif src == "weighted":
                detect_chunk = snr_weighted_merge(channel_arrays)
            else:
                # "all" — legacy equal average
                detect_chunk = merge_channels(channel_arrays)

            with self._detect_lock:
                self._detect_accumulator = np.concatenate(
                    [self._detect_accumulator, detect_chunk]
                )
                if len(self._detect_accumulator) >= self.analysis_window_samples:
                    window = self._detect_accumulator[:self.analysis_window_samples]
                    keep = int(self._effective_overlap() * self.sample_rate)
                    self._detect_accumulator = self._detect_accumulator[
                        self.analysis_window_samples - keep:
                    ]
                    try:
                        self._detection_queue.put_nowait(window)
                        self.stats["detection_windows_queued"] += 1
                    except queue.Full:
                        # BirdNET is behind (CPU busy, e.g. bat detector at
                        # night). Count it so the heartbeat log shows it.
                        dropped = self.stats.get("detection_windows_dropped", 0) + 1
                        self.stats["detection_windows_dropped"] = dropped
                        if dropped == 1 or dropped % 100 == 0:
                            logger.warning(
                                "Detection falling behind: %d analysis window(s) dropped. "
                                "Lower overlap_seconds or disable the bat detector.", dropped)

            # Keep legacy detection_accumulator in sync (for external callers)
            with self._detection_lock:
                self._detection_accumulator = self._detect_accumulator.copy()

            self.stats["chunks_merged"] += 1

        logger.debug("AudioMerger thread exiting")

    # ── Health Check ──────────────────────────────────────────────────────────

    def check_streams(self) -> bool:
        any_active = False
        for stream in self._streams:
            if not stream.is_active:
                logger.warning("Stream for %s is no longer active, attempting restart...",
                               stream.device)
                stream.stop()
                if stream.start():
                    logger.info("Successfully restarted stream for %s", stream.device)
                else:
                    logger.error("Failed to restart stream for %s", stream.device)
            else:
                any_active = True
        return any_active
