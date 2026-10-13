"""
Chirp Device — Bat Echolocation Detector (Experimental / Beta)
================================================================

What this is and isn't
-----------------------
This detects the *presence* of ultrasonic pulse trains consistent with bat
echolocation — it does NOT identify species ON THE DEVICE. There is no
bundled species classifier here: running a model like BatDetect2 on a
resource-constrained Pi that's already running BirdNET continuously isn't
worth the added load for an inference call that's infrequent (one per bat
clip, not continuous). Species classification, where enabled, happens
server-side instead — see chirp-server/app/services/bat_species_id.py.

IMPORTANT: even that server-side classifier should not be treated as a
reliable species identification for most deployments. It uses the
open-source BatDetect2 model (macaodha/batdetect2), whose bundled
pretrained checkpoint is trained on 17 UK bat species only. Outside the
UK — including Chirp's own example deployment in Massachusetts — every
prediction is a best-effort guess at the closest UK acoustic match, not a
validated identification of the species actually present. It's off by
default (Settings → bat_species_id_enabled) and every stored result is
explicitly flagged validated=False for exactly this reason. See that
module's docstring for the full explanation and the plan for surfacing
real per-species profiles once a non-UK-trained or fine-tuned model
exists worth showing without a disclaimer attached.

This module itself just flags "ultrasonic activity consistent with
echolocation calls" with a peak frequency and pulse count, and saves a
time-expanded WAV snippet so a person can listen to / spectrogram-analyze
it themselves (or feed it to a dedicated bat classifier outside Chirp, if
they want a second opinion).

Hardware requirement — this is the important part
----------------------------------------------------
Bat echolocation calls run roughly 15 kHz–120 kHz depending on species.
A standard USB microphone (including the ReSpeaker XVF3800 this project
otherwise uses) samples at 48 kHz, giving a Nyquist limit of 24 kHz — it
physically cannot capture most of this range; anything above 24 kHz is
either lost or aliases into garbage. This module requires a *separate*,
purpose-built ultrasonic USB microphone running at a high sample rate
(192 kHz+) to do anything at all. See Settings → Experimental in the
server UI for the current hardware recommendation. If no such device is
configured, this module simply never starts — it does not attempt to
"detect bats" on a normal bird microphone, which would be meaningless.

Detection approach
-------------------
1. Capture raw audio from the configured ultrasonic device at its native
   high sample rate (no resampling — resampling would defeat the purpose).
2. Every analysis window (default 200 ms), compute an STFT and look at the
   15–120 kHz band specifically.
3. A "pulse" is a short (1–20 ms) burst where that band's energy rises
   well above the recent noise floor — much shorter than a continuous tone
   or steady-state noise (e.g. electronics whine, insect stridulation can
   sometimes false-trigger this; pulse-train timing below helps reject it).
4. Track the dominant frequency across a pulse's duration — most
   echolocation calls sweep in frequency (typically downward); a pulse
   with little or no sweep is weighted lower but not discarded outright,
   since some species (e.g. some Myotis search-phase calls) are closer to
   constant-frequency.
5. A single pulse isn't reported — real bat activity comes as a *train*
   of pulses (a bat passing through typically produces several calls per
   second). Pulses accumulate into one open event for as long as they keep
   arriving within event_gap_seconds of each other (configurable — see
   config.yaml's bat_echolocation section); the event is only evaluated
   and logged once a real gap of silence confirms the train has ended
   (and only then if it reached at least min_pulses_for_event pulses in
   total) — capturing the full pass rather than just its first few calls.

This is a coarse activity detector, not a validated scientific instrument —
it's offered as an experimental starting point, not a survey-grade tool.
"""

import contextlib
import json
import logging
import os
import re
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Deque, Dict, List, Optional

import numpy as np

from .utils import rms_db

logger = logging.getLogger(__name__)


def attempt_usb_power_cycle(config: dict) -> bool:
    """
    Best-effort HARD power-cycle of the ultrasonic mic's USB port via
    uhubctl, for the failure mode a software stream reopen can't fix: a
    stuck-sensor AudioMoth whose analog frontend has wedged at the
    firmware/hardware level rather than at the ALSA/PortAudio layer (see
    BatDetector.is_stalled()). Deliberately opt-in and narrow in scope —
    this is a targeted single-port reset, not a Pi reboot, and it does
    nothing unless explicitly configured to a real hub/port.

    Off by default. To use: run `uhubctl` with no arguments on the device
    itself to list every switchable hub/port it can see (not all USB
    controllers/hubs support per-port power switching — the Pi 5's own
    root hub often doesn't; this generally requires a powered hub that
    does), then set detection.bat_echolocation.usb_power_cycle.enabled:
    true with the matching hub_location/port in config.yaml.

    Returns False on ANY failure — disabled, unconfigured, uhubctl
    missing, wrong port, unsupported hardware, permission issue — so
    callers fall back to the existing log-and-wait-for-a-human path
    rather than assuming this fixed anything. Never raises.
    """
    import shutil
    import subprocess

    cfg = ((config.get("detection", {}) or {}).get("bat_echolocation", {}) or {}) \
        .get("usb_power_cycle", {}) or {}
    if not cfg.get("enabled", False):
        return False

    location = str(cfg.get("hub_location", "") or "")
    port = str(cfg.get("port", "") or "")
    if not location or not port:
        logger.warning(
            "Bat detector: usb_power_cycle.enabled is true but "
            "hub_location/port aren't both set. Run `uhubctl` with no "
            "arguments on the device to list real hub locations/ports, "
            "then fill both in — doing nothing until then."
        )
        return False

    if shutil.which("uhubctl") is None:
        logger.warning(
            "Bat detector: usb_power_cycle enabled but uhubctl isn't "
            "installed (try: sudo apt install uhubctl). Even installed, "
            "not every Pi USB controller/hub supports per-port power "
            "switching — a plain USB extension cable doesn't; a powered "
            "hub with documented uhubctl support does."
        )
        return False

    try:
        result = subprocess.run(
            ["sudo", "uhubctl", "-l", location, "-p", port, "-a", "cycle"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            logger.warning(
                "Bat detector: power-cycled USB hub %s port %s via uhubctl "
                "(stuck-sensor recovery).", location, port,
            )
            return True
        logger.warning(
            "Bat detector: uhubctl power-cycle failed (rc=%d): %s",
            result.returncode, (result.stderr or "").strip()[:300],
        )
        return False
    except Exception as e:
        logger.warning("Bat detector: uhubctl power-cycle raised: %s", e)
        return False


@contextlib.contextmanager
def _suppress_alsa_probe_noise():
    """
    PortAudio's ALSA backend writes raw C-level diagnostics directly to file
    descriptor 2 (stderr) — entirely bypassing Python's try/except and
    logging — whenever a sample rate it's probing turns out to be
    unsupported by the hardware. Lines like:

        Expression 'ret' failed in 'src/hostapi/alsa/pa_linux_alsa.c', line: 1736
        Expression 'AlsaOpen( hostApi, parameters, streamDir, &pcm )' failed

    are the direct result of start()'s candidate-rate loop below doing
    exactly what it's designed to do: trying several plausible rates
    against real hardware via check_input_settings() and expecting most of
    them to fail until it finds the one the device actually supports (a
    device like the AudioMoth, which only accepts one specific fixed rate,
    will legitimately reject every other candidate on the way to finding
    it). Harmless — but raw, unlabeled C output in the systemd journal
    reads as an alarming crash when it's actually just an expected part of
    discovery, which is exactly what prompted this: real confusion from a
    real log, even though nothing was actually broken by these specific
    lines.

    Suppressed only around the probing loop itself, at the raw file-
    descriptor level (Python-level stderr redirection wouldn't catch this,
    since PortAudio is C code writing directly to fd 2, not going through
    Python's sys.stderr object at all). Any REAL failure — the actual
    stream failing to open or start afterward — is unaffected and still
    raises/logs normally through ordinary Python exception handling.
    """
    try:
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        saved_stderr_fd = os.dup(2)
        os.dup2(devnull_fd, 2)
    except Exception:
        # If fd redirection itself fails for any reason, just don't suppress
        # anything rather than risk leaving stderr in a broken state.
        yield
        return
    try:
        yield
    finally:
        try:
            os.dup2(saved_stderr_fd, 2)
        finally:
            os.close(saved_stderr_fd)
            os.close(devnull_fd)

try:
    import sounddevice as sd
    _SD_OK = True
except (ImportError, OSError) as _e:
    _SD_OK = False
    sd = None
    logger.debug("sounddevice unavailable (bat detector will stay disabled): %s", _e)

try:
    import scipy.signal as sps
    _SCIPY_OK = True
except ImportError:
    _SCIPY_OK = False

try:
    import soundfile as sf
    _SF_OK = True
except ImportError:
    _SF_OK = False

try:
    import requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False


# ── Tunables ───────────────────────────────────────────────────────────────────
ANALYSIS_WINDOW_SECONDS = 0.2       # how often we run an STFT pass
BAND_LOW_HZ = 15_000
BAND_HIGH_HZ = 120_000
PULSE_MIN_MS = 1.0
PULSE_MAX_MS = 25.0
PULSE_SNR_THRESHOLD = 4.0            # ~6dB above rolling noise floor
# Event-timing / snippet-length settings (minimum pulses per event, the
# silence gap that closes an event, snippet padding/minimum/maximum
# duration) all moved from fixed constants here to configurable instance
# attributes — see __init__'s "Event timing / snippet length" section —
# so they can actually be adjusted via config.yaml without a code change.


@dataclass
class Pulse:
    timestamp: float          # time.time() when detected
    peak_freq_hz: float
    duration_ms: float
    swept: bool                # did frequency change meaningfully during the pulse?


@dataclass
class BatActivityEvent:
    started_at: datetime
    ended_at: datetime
    pulse_count: int
    peak_freq_hz: float        # median peak frequency across pulses in this event
    mean_pulse_duration_ms: float
    swept_fraction: float       # fraction of pulses that showed an FM sweep
    sample_rate: int
    timing_cv: Optional[float] = None       # coefficient of variation of inter-pulse intervals — flags likely electrical/mechanical interference, see _finalize_event
    likely_interference: bool = False
    clip_path: Optional[str] = None


class BatDetector:
    """
    Independent ultrasonic capture + coarse echolocation-pulse detector.

    Runs its own sounddevice.InputStream entirely separate from the main
    BirdNET audio pipeline (different device, vastly different sample
    rate — there's no sane way to share one capture stream between a 48kHz
    bird mic and a 192kHz+ ultrasonic mic).
    """

    def __init__(self, config: dict):
        bat_cfg = (config.get("detection", {}) or {}).get("bat_echolocation", {}) or {}
        self.enabled: bool = bool(bat_cfg.get("enabled", False))
        self.device_name_hint: str = bat_cfg.get("device_name", "")
        self._device_actual_name: str = ""  # set in start() from sd.query_devices() — see there
        self.min_sample_rate: int = int(bat_cfg.get("min_sample_rate", 192_000))
        # expanduser: config.yaml and server pushes use "~/chirp/bat_events"
        self.events_dir = Path(os.path.expanduser(
            bat_cfg.get("events_dir", "~/chirp/bat_events")))
        self.log_path = self.events_dir / "bat_events.jsonl"

        # ── Noise / quality filters ───────────────────────────────────────────
        # Minimum fraction of pulses that must show an FM sweep (frequency
        # modulation). Real bat echolocation calls sweep in frequency; broadband
        # machine noise (lawnmowers, power tools, motors) does not.
        # Default is currently 0 (disabled) — permissive until there's a
        # baseline of real detections to tune a real threshold against, so
        # genuine early activity isn't filtered out before there's data to
        # know where the right cutoff actually is. Set to e.g. 0.3 (at least
        # 30% of pulses must show FM sweep) once that baseline exists.
        self.min_swept_fraction: float = float(bat_cfg.get("min_swept_fraction", 0))

        # Maximum pulse rate within the detection window (pulses/second).
        # Real bats call 5-30 times/second. Continuous machine noise produces
        # hundreds of "pulses" per second. Default is currently 600 — a very
        # generous upper bound while other filters are also permissive during
        # this same initial data-gathering period; tighten once real activity
        # patterns are known.
        self.max_pulse_rate: float = float(bat_cfg.get("max_pulse_rate_per_sec", 600.0))
        # Below this coefficient-of-variation of inter-pulse timing, an
        # event gets flagged (not rejected) as likely electrical/mechanical
        # interference rather than a real bat pass — see _finalize_event's
        # comment for why this exists and why it's a flag, not a reject.
        # Real bat calls, even from one species in one pass, vary in
        # spacing because the animal is alive, not a fixed oscillator;
        # anything this metronomic is a real, useful tell. 0.15 chosen
        # conservatively (a real pass would need to be extremely uniform
        # to trip this) after finding several real forum reports of
        # exactly this class of interference on AudioMoth-on-Pi setups.
        self.min_timing_cv_for_real: float = float(bat_cfg.get("min_timing_cv_for_real", 0.15))
        # Off by default — flagging alone (see likely_interference below)
        # doesn't remove anything from a saved recording, just marks it.
        # Stays opt-in since a false positive means a real bat pass never
        # gets saved, with no way to recover it after the fact.
        self.discard_likely_interference: bool = bool(bat_cfg.get("discard_likely_interference", False))

        # Off by default per explicit request: the server is the durable
        # store once upload succeeds, so keeping a second local copy
        # forever just accumulates files on the Pi's SD card for no
        # benefit. Set true to keep every local snippet regardless of
        # upload outcome (e.g. for offline analysis without touching the
        # server). A FAILED upload always keeps its local copy regardless
        # of this setting — that's the only copy that exists in that case.
        self.keep_local_snippets: bool = bool(bat_cfg.get("keep_local_snippets", False))

        # Minimum peak frequency. At 192kHz sample rate, bat calls are
        # typically 15-120kHz. Below this likely means audio aliasing or EMI.
        self.min_peak_freq_hz: float = float(bat_cfg.get("min_peak_freq_hz", BAND_LOW_HZ))

        # ── Observability ──────────────────────────────────────────────────────
        # Periodic status logging (see _on_audio's heartbeat) — without
        # this, a silently-stalled AudioMoth stream looks identical in the
        # logs to "genuinely no bats calling."
        self._total_pulses_seen: int = 0
        self._total_events_fired: int = 0
        self._last_heartbeat: float = 0.0
        self._heartbeat_interval_s: float = 60.0
        # Ambient-diagnostic trigger: `touch` this file (from an SSH session
        # or a small helper script) to get a real ambient-audio sample while
        # chirp-device is running its normal capture pipeline — see
        # dump_ambient_diagnostic()'s docstring for why this exists.
        self._ambient_trigger_path = self.events_dir / "capture_ambient.trigger"

        # ── Event timing / snippet length ─────────────────────────────────────
        # All previously hardcoded module-level constants with no way to
        # adjust them without a code change — now configurable, directly
        # answering a real question ("how do I increase recording length,
        # still getting short <1s clips sometimes") that had no actual
        # answer before this, since nothing here was exposed at all.
        #
        # Minimum pulses required before a pulse train counts as a real
        # event at all (vs. noise/a single stray pulse). Doesn't affect
        # clip LENGTH directly, but a higher value means only more
        # substantial passes get recorded in the first place.
        self.min_pulses_for_event: int = int(bat_cfg.get("min_pulses_for_event", 3))

        # How long a gap of silence (no new pulse) means a pulse train has
        # actually ended, vs. just a normal brief pause within one
        # continuous bat pass. Pulses accumulate into one open event for as
        # long as they keep arriving within this gap of each other; the
        # event only closes (capturing the FULL train, first pulse to
        # last) once a real gap of silence this long confirms the pass has
        # ended. Raising this lets a single event span longer pauses within
        # one bat's pass (capturing more of a longer, intermittent
        # encounter as ONE event instead of splitting it into several
        # shorter ones) — but also delays when a genuinely-ended event
        # actually gets saved/uploaded, and increases the chance unrelated
        # passes a while apart get merged into one event.
        self.event_gap_seconds: float = float(bat_cfg.get("event_gap_seconds", 2.0))

        # Fixed padding added before the first pulse and after the last
        # pulse of an event when extracting its audio clip — pure buffer
        # room, always added regardless of how long the pulse train itself
        # was. Raising this adds real context to every clip, short or long.
        self.snippet_padding_seconds: float = float(bat_cfg.get("snippet_padding_seconds", 0.5))

        # Real fix for "still getting short <1s clips sometimes": a
        # legitimate pulse train that only just barely reaches
        # min_pulses_for_event can genuinely span well under a second on
        # its own — the fixed padding above still isn't much once added to
        # such a short span. This is a hard FLOOR on total clip length: if
        # (event span + padding) comes out shorter than this, the padding
        # window is symmetrically expanded (equally on both sides) until it
        # reaches this minimum, rather than only ever getting the fixed
        # padding regardless of how brief the underlying pass was. Default
        # 2.0s comfortably covers the vast majority of brief passes while
        # staying well under typical inter-event gaps.
        self.snippet_min_seconds: float = float(bat_cfg.get("snippet_min_seconds", 2.0))

        # Upper bound on total clip length/memory, regardless of how long a
        # continuous pulse train runs. Raised from an original 6.0 once
        # events started correctly capturing a FULL pulse train (via
        # event_gap_seconds above) instead of just the first few pulses —
        # a genuine continuous pass can legitimately run longer than a few
        # seconds. Raising this further lets longer real passes be captured
        # in full, at the cost of more memory per event and a larger
        # upload; lowering it truncates anything longer to this length
        # (keeping the most recent portion — see _extract_raw_audio).
        self.snippet_max_seconds: float = float(bat_cfg.get("snippet_max_seconds", 20.0))

        # Same dB-based gain the bird pipeline supports (audio.input_gain_db) —
        # separate control here since the bat mic is usually a different,
        # purpose-built ultrasonic device with its own sensitivity/placement,
        # not necessarily needing the same gain as the bird mic. Applied once
        # per audio chunk in _on_audio(), before the sample is used for
        # anything (live level display, pulse-detection analysis, or saved
        # clip audio) — one control point affects all three consistently.
        self.gain_db: float = float(bat_cfg.get("gain_db", 0.0))
        self.gain_linear: float = 10 ** (self.gain_db / 20.0)

        # ── Time-of-day gating ────────────────────────────────────────────────
        # When enabled, bat detections are only logged during the allowed window.
        # This avoids daytime machine noise (lawnmowers, power tools) being
        # flagged as bats. Bats in northeastern North America are strictly
        # crepuscular/nocturnal; activity outside 30 min after sunset and
        # before 30 min after sunrise is almost certainly a false positive.
        #
        # Format: "HH:MM" in 24-hour local time. Both must be set to enable.
        # Example: active_hours_start: "20:00", active_hours_end: "06:00"
        # (wraps midnight). Set both to null/empty to disable gating entirely.
        self.active_hours_start: Optional[str] = bat_cfg.get("active_hours_start") or None
        self.active_hours_end:   Optional[str] = bat_cfg.get("active_hours_end")   or None

        # ── Stalled-sensor detection ──────────────────────────────────────────
        # A distinct failure mode from a dead stream (see is_active() below):
        # the ALSA stream stays healthy — callbacks keep firing on schedule,
        # audio level keeps varying normally — while the AudioMoth itself
        # stops registering any pulses at all, for hours on end, during a
        # window it should clearly be hearing SOMETHING if it were working
        # (active_hours=True). Found via a real deployment: 3295 pulses in
        # under 3.5 hours on first boot, then bit-for-bit zero new pulses for
        # 9 straight days across every subsequent night, with the stream
        # reporting active=True and a plausibly-varying dBFS reading the
        # entire time — ruling out both a dead stream (is_active() would
        # have caught that) and a simple quiet night (one quiet night is
        # normal; 9 consecutive ones with zero new pulses, even briefly, is
        # not). Most consistent with an AudioMoth analog-frontend/ultrasonic-
        # sensitivity fault that leaves its general USB audio path
        # functioning normally — is_active() structurally cannot see this,
        # since it only measures whether the callback is still firing, not
        # whether what it's finding is plausible for the time of day.
        # 0 (or any non-positive value) disables this check entirely.
        self.stuck_pulse_hours: float = float(bat_cfg.get("stuck_pulse_hours", 4.0))
        self._pulse_count_at_last_check: int = 0
        self._stall_started_at: Optional[float] = None

        # Real gap found and fixed: this used to reuse server_sync's
        # single legacy server_url/api_key, which is only ONE server —
        # even when upload.targets configures multiple. Bird recordings
        # correctly upload to every configured target (see uploader.py's
        # FileUploader); bat events silently never did, always landing on
        # whichever server happened to be upload.targets[0] (or the
        # legacy single server_url) and never anywhere else. Resolved
        # here the same way uploader.py resolves its own target list —
        # from upload.targets, not server_sync.targets (a different,
        # pairing-only list that happens to often list the same servers,
        # but isn't the authoritative one for where uploads go) — with
        # the same legacy single-target fallback for an existing
        # config.yaml that predates targets:.
        upload_cfg = config.get("upload", {}) or {}
        target_configs = upload_cfg.get("targets")
        if not target_configs:
            target_configs = [{
                "name": "chirp-server", "enabled": True,
                "server_url": upload_cfg.get("server_url", ""),
                "api_key": upload_cfg.get("api_key", ""),
                "auth_header": upload_cfg.get("auth_header", "X-API-Key"),
            }]
        self._upload_targets: List[Dict] = []
        for tc in target_configs:
            if not tc.get("enabled", True):
                continue
            # upload.targets' own server_url is a FULL endpoint
            # (".../api/v1/recordings/upload"), not a bare base URL —
            # bat-activity has its own, different endpoint, so the
            # recordings-specific suffix is stripped back to the base
            # first, however deep the actual path turns out to be,
            # rather than assuming one exact fixed suffix string.
            full_url = (tc.get("server_url", "") or "").rstrip("/")
            base_url = full_url.split("/api/v1/")[0] if "/api/v1/" in full_url else full_url
            if not base_url or not tc.get("api_key"):
                continue
            self._upload_targets.append({
                "name": tc.get("name", "chirp-server"),
                "base_url": base_url,
                "api_key": tc.get("api_key", ""),
                "auth_header": tc.get("auth_header", "X-API-Key"),
            })
        self._device_serial: str = socket.gethostname()

        self._device_index: Optional[int] = None
        self._sample_rate: Optional[int] = None
        self._stream = None
        self._running = False
        self._lock = threading.Lock()
        # Real, previously-missing staleness tracking: is_active() alone
        # (checking self._stream.active) is confirmed insufficient — a
        # real, direct report showed AudioMoth stuck at a fixed dBFS
        # reading with a spectrogram that had stopped updating entirely,
        # meaning no new audio was actually flowing, while the stream
        # object itself can still report active=True (a known real
        # failure mode for this hardware — see start()'s own comment on
        # devices getting stuck permanently busy at the OS/driver level,
        # confirmed via fuser/lsof in an earlier investigation). Tracking
        # the real wall-clock time of the last callback that actually
        # fired lets is_active() detect THIS failure mode too, not just
        # a stream that's genuinely stopped.
        self._last_callback_at: float = 0.0

        # Comfortably covers the worst case: a pass running the full
        # snippet_max_seconds, plus event_gap_seconds of silence before the
        # event actually closes and extraction runs, plus whichever padding
        # ends up larger — the fixed snippet_padding_seconds on each side,
        # or half of snippet_min_seconds if the minimum-duration floor ends
        # up expanding the window beyond that (see _extract_raw_audio) —
        # with a safety margin on top. Each callback chunk is ~0.05s of
        # audio (ANALYSIS_WINDOW_SECONDS/4, constant regardless of sample
        # rate since blocksize scales with it), so this many chunks
        # reliably corresponds to _RAW_BUFFER_SECONDS of real time.
        # Previously a fixed 200 (~10s) — fine for the old design's short,
        # immediately-fired events, but would have silently truncated the
        # beginning of any pass longer than ~10s under the new gap-based
        # grouping, since a maxlen deque just drops the oldest entries as
        # new ones arrive. Now correctly recalculates whenever these
        # settings change, since they're no longer fixed constants.
        _effective_padding = max(self.snippet_padding_seconds, self.snippet_min_seconds / 2)
        _RAW_BUFFER_SECONDS = self.snippet_max_seconds + self.event_gap_seconds + _effective_padding + 5.0
        _CHUNK_SECONDS_APPROX = ANALYSIS_WINDOW_SECONDS / 4
        self._raw_buffer: Deque = deque(maxlen=int(_RAW_BUFFER_SECONDS / _CHUNK_SECONDS_APPROX))
        self._analysis_buffer = np.zeros(0, dtype=np.float32)
        self._noise_floor: Optional[float] = None

        self._pending_pulses: List[Pulse] = []

        self._callbacks: List[Callable[[BatActivityEvent], None]] = []

    def add_callback(self, cb: Callable[[BatActivityEvent], None]) -> None:
        self._callbacks.append(cb)

    # ── Device discovery ─────────────────────────────────────────────────────────

    def _find_device(self) -> Optional[int]:
        if not _SD_OK:
            return None
        try:
            devices = sd.query_devices()
        except Exception as e:
            logger.warning("Bat detector: could not query audio devices: %s", e)
            return None

        candidates = []
        all_inputs = []  # every real input device seen, regardless of name match —
                          # logged below so a name mismatch is immediately visible
                          # in the log itself instead of requiring a separate
                          # manual --list-devices run to diagnose.
        for i, d in enumerate(devices):
            if d.get("max_input_channels", 0) <= 0:
                continue
            name = d.get("name", "")
            max_rate = int(d.get("default_samplerate", 0) or 0)
            all_inputs.append((i, name, max_rate))
            if self.device_name_hint and self.device_name_hint.lower() not in name.lower():
                continue
            candidates.append((i, name, max_rate))

        if not candidates:
            if all_inputs:
                seen = ", ".join(f"'{name}' ({rate} Hz)" for _, name, rate in all_inputs)
                logger.warning(
                    "Bat detector enabled but no input device name contains '%s'. "
                    "Real input devices seen: %s. If your ultrasonic mic is listed "
                    "above under a different name, update detection.bat_echolocation."
                    "device_name in config.yaml to match it (or set it to \"\" to "
                    "auto-pick whichever device reports the highest sample rate).",
                    self.device_name_hint or "<any>", seen,
                )
            else:
                logger.warning(
                    "Bat detector enabled but no input audio devices were found at "
                    "all (not a name-matching issue — sounddevice saw zero input-"
                    "capable devices). Check the mic is actually connected: "
                    "arecord -l  should list it."
                )
            return None

        # Prefer the device reporting the highest default sample rate
        candidates.sort(key=lambda c: -c[2])
        idx, name, rate = candidates[0]
        logger.info("Bat detector: using device '%s' (index %d, default rate %d Hz)", name, idx, rate)
        return idx

    def start(self) -> bool:
        if not self.enabled:
            return False
        if not (_SD_OK and _SCIPY_OK and _SF_OK):
            logger.warning("Bat detector enabled but sounddevice/scipy/soundfile not all available")
            return False

        idx = self._find_device()
        if idx is None:
            return False
        self._device_index = idx

        try:
            info = sd.query_devices(idx)
            device_name = info.get("name", "")
            native_rate = int(round(info.get("default_samplerate", 0) or 0))
        except Exception:
            device_name = ""
            native_rate = 0

        # Persisted so status_server.py's /listen and /levels can report the
        # SAME name sd.query_devices() gave server_sync.py's _get_mic_info()
        # for this same device (i.e. what the UI's mic dropdown actually
        # shows and sends back as ?name=). Previously these two functions
        # fell back to self.device_name_hint (a user-configured substring
        # like "" or "AudioMoth", not the real device name) or the literal
        # string "AudioMoth" — a mismatch against the long real PortAudio
        # name (e.g. "384kHz AudioMoth USB Microphone: Audio (hw:0,0)") that
        # made every by-name /listen lookup 404 for this stream specifically,
        # even though the bird stream (which always used the real device
        # name) worked fine.
        self._device_actual_name = device_name

        # AudioMoth encodes its currently-configured sample rate directly in
        # its own USB device name (e.g. "384kHz AudioMoth USB Microphone") —
        # confirmed via real device logs this is a MORE reliable signal than
        # PortAudio's default_samplerate for this hardware: a real run showed
        # check_input_settings failing for BOTH min_sample_rate (192000) and
        # whatever native_rate was reported, meaning default_samplerate
        # simply wasn't 384000 even though the device's own name said so and
        # the device only actually works at that one specific rate (common
        # for simple USB Audio Class 1.0 devices in a fixed-rate mode, which
        # can reject sample rates other than their one supported rate rather
        # than accepting any rate up to some maximum).
        name_rate_match = re.search(r"(\d+)\s*k\s*hz", device_name, re.IGNORECASE)
        name_rate = int(name_rate_match.group(1)) * 1000 if name_rate_match else 0

        # Capped at 2 candidates, tried by DIRECTLY constructing the real
        # InputStream (not a separate check_input_settings probe followed by
        # a second, duplicate real open) — deliberately conservative after a
        # real run showed a device getting stuck permanently busy (confirmed
        # via `fuser`/`lsof` — the SAME process PID still held the device
        # open several minutes later, well after this function had already
        # logged giving up) following a version of this code that tried up
        # to 6 candidates via check_input_settings THEN a separate real
        # open. That's strong evidence of a PortAudio/ALSA-level handle leak
        # on some failing probe-and-close cycle for this specific hardware —
        # not something fixable on this side of the sounddevice/PortAudio
        # boundary, only avoidable by minimizing how many open/close cycles
        # get attempted in the first place. Name-parsing (above) already
        # gets the right answer on the first try in the common case; the
        # second candidate is a single, minimal fallback, not a broad sweep.
        candidate_rates = []
        if name_rate > 0:
            candidate_rates.append(name_rate)
        for fallback in (self.min_sample_rate, native_rate):
            if fallback > 0 and fallback not in candidate_rates:
                candidate_rates.append(fallback)
        candidate_rates = candidate_rates[:2]

        tried = []
        opened_stream = None
        with _suppress_alsa_probe_noise():
            for candidate_rate in candidate_rates:
                tried.append(candidate_rate)
                try:
                    blocksize = max(512, int(candidate_rate * ANALYSIS_WINDOW_SECONDS / 4))
                    opened_stream = sd.InputStream(
                        device=idx, channels=1, samplerate=float(candidate_rate),
                        blocksize=blocksize, dtype="float32", callback=self._on_audio,
                        finished_callback=self._on_stream_finished,
                    )
                    self._sample_rate = candidate_rate
                    break
                except Exception:
                    # Explicit, immediate cleanup on this specific failed
                    # attempt before trying the next candidate — belt and
                    # braces against the exact class of leak this whole
                    # restructure exists to avoid. sounddevice's own
                    # constructor is expected to clean up after itself on a
                    # raised exception, but being explicit here costs
                    # nothing and removes any doubt.
                    if opened_stream is not None:
                        try:
                            opened_stream.close()
                        except Exception:
                            pass
                        opened_stream = None
                    continue

        if opened_stream is None or self._sample_rate is None or self._sample_rate < self.min_sample_rate:
            logger.warning(
                "Bat detector: device does not support >= %d Hz sampling — "
                "cannot capture full bat-echolocation range, not starting. "
                "(Tried: %s Hz. Device name suggested %s Hz; PortAudio's own "
                "default_samplerate reported %s Hz — if those disagree with "
                "what the device can actually do, that's exactly the kind "
                "of mismatch this name-parsing fallback exists for. If the "
                "device now shows as busy in other tools too, restart "
                "chirp-device — a previous failed attempt may have left a "
                "stuck ALSA handle open; this version deliberately tries "
                "far fewer candidates than before specifically to make that "
                "much less likely going forward.)",
                self.min_sample_rate, tried, name_rate or "none", native_rate or "none",
            )
            return False

        try:
            self.events_dir.mkdir(parents=True, exist_ok=True)
            self._stream = opened_stream
            self._stream.start()
            self._running = True
            self._last_callback_at = time.time()  # fresh baseline — not stale yet, first real callback hasn't fired
            logger.info(
                "Bat detector started: %d Hz (Nyquist %.0f kHz, covers most bat species)",
                self._sample_rate, self._sample_rate / 2000,
            )
            # Logged explicitly (not just implied by config) because this is
            # exactly the kind of path that quietly differs between a
            # fresh-install default and a real deployment's config.yaml
            # override — a mismatch here means snippets/triggers silently
            # go to a directory nobody's looking at, with no error anywhere.
            logger.info("Bat detector events_dir: %s", self.events_dir)
            return True
        except Exception as e:
            logger.error("Bat detector: failed to open ultrasonic stream: %s", e)
            if self._stream is not None:
                try:
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
            return False

    def stop(self) -> None:
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def is_running(self) -> bool:
        return self._running

    def _on_stream_finished(self) -> None:
        """
        Real, previously-missing instrumentation: the bird pipeline's own
        DeviceStream logs a clear warning the moment its stream
        unexpectedly ends (see audio.py's _finished) — the bat detector had
        no equivalent at all, meaning a real AudioMoth crash left no trace
        in the logs whatsoever, no timestamp, nothing to correlate against.
        Found while investigating a real report of AudioMoth crashing daily,
        only recovering on a full device reboot.
        """
        logger.warning(
            "Bat detector: ultrasonic stream finished unexpectedly (device "
            "disconnected or crashed?). device_index=%s, sample_rate=%s Hz. "
            "This will be picked up by the next health check and the stream "
            "will be automatically restarted.",
            self._device_index, self._sample_rate,
        )

    def is_active(self) -> bool:
        """
        The REAL, current health of the stream — distinct from is_running(),
        which only reflects whether start() succeeded at some point in the
        past and is never updated if the underlying stream dies on its own.
        A real, confirmed gap: nothing in this codebase ever called this
        (or anything like it) before now, meaning a dead AudioMoth stream
        was invisible to every health check in the system — is_running()
        stayed True forever after a successful start(), even once the
        actual sd.InputStream had silently stopped delivering audio.
        Returns False if never started, True if genuinely still delivering
        audio, False if the stream object exists but has gone inactive
        (matches the exact check the bird pipeline's DeviceStream already
        uses in AudioCapture.check_streams()).

        A real, confirmed gap in this check itself, found from a direct
        report after this exact fix had already shipped once: a stream
        can report active=True while genuinely delivering no new audio
        at all — confirmed by a stuck dBFS reading and a spectrogram
        that had stopped updating entirely, a real, observed hardware
        failure mode distinct from the stream cleanly stopping (which
        the .active check above already caught correctly). Now also
        checks real staleness: how long it's actually been since
        _on_audio last fired, not just whether the stream object still
        thinks it's open. 30 seconds is generous enough that a normal
        quiet moment between real analysis windows never trips this,
        while still catching a genuine, sustained stall well before a
        person would notice on their own.
        """
        if not self._running or self._stream is None:
            return False
        try:
            if not bool(self._stream.active):
                return False
        except Exception:
            # A real, observed failure mode for this hardware specifically
            # (see start()'s own comment on stuck ALSA handles): if even
            # reading .active raises, treat that as unhealthy rather than
            # letting the exception propagate into the caller's health-check
            # loop and potentially block the OTHER health checks that run
            # after this one.
            return False

        staleness = time.time() - self._last_callback_at
        if staleness > 30.0:
            logger.warning(
                "Bat detector: stream reports active but no audio callback "
                "has fired in %.0fs — treating as stalled, not genuinely "
                "healthy. device_index=%s",
                staleness, self._device_index,
            )
            return False
        return True

    def is_stalled(self) -> bool:
        """
        Detects a live-but-deaf sensor: is_active() is True (stream healthy,
        callbacks firing) but zero NEW pulses have been registered in
        stuck_pulse_hours while active_hours says bats should be audible
        right now. See the __init__ comment on stuck_pulse_hours for the
        real deployment this was found from.

        Deliberately conservative to avoid false-triggering on a genuinely
        quiet night: only counts elapsed time while _is_active_hour() is
        True (a quiet daytime stretch never accumulates toward the
        threshold), and resets its internal clock the moment pulses_seen
        moves at all, so a single real pulse hours into a dry spell clears
        the stall timer rather than needing a full window of total silence.

        Only meaningful for a detector that's enabled and currently
        believed active — a disabled or not-yet-started detector isn't
        "stalled," it's simply off, and get_status() callers should not
        confuse the two.
        """
        if self.stuck_pulse_hours <= 0:
            return False
        if not self._running or not self.is_active():
            # Not this check's job — a dead/never-started stream is
            # is_active()'s (or is_running()'s) concern, not this one's.
            self._stall_started_at = None
            return False
        if not self._is_active_hour():
            # No bats expected right now — an unmoving pulse count during
            # the day is completely normal, not evidence of anything.
            self._stall_started_at = None
            return False

        now = time.time()
        if self._total_pulses_seen != self._pulse_count_at_last_check:
            self._pulse_count_at_last_check = self._total_pulses_seen
            self._stall_started_at = None
            return False

        if self._stall_started_at is None:
            self._stall_started_at = now
            return False

        stalled_for_s = now - self._stall_started_at
        if stalled_for_s >= self.stuck_pulse_hours * 3600.0:
            logger.warning(
                "Bat detector: zero new pulses in %.1fh while active_hours="
                "True and the stream itself reports healthy (callback "
                "firing, level varying) — likely a stuck AudioMoth sensor "
                "rather than a dead stream. Total pulses_seen=%d.",
                stalled_for_s / 3600.0, self._total_pulses_seen,
            )
            return True
        return False

    def get_live_level_snapshot(self, window_seconds: float = 0.3, n_bins: int = 32) -> Optional[dict]:
        """
        Return live RMS/peak/spectrum for the ultrasonic stream from the
        in-memory raw buffer already populated by _on_audio(). No second
        ALSA open — same rationale as AudioCapture.get_live_level_snapshot().
        Returns None if the detector isn't running (nothing to report).
        """
        if not self._running or self._device_index is None:
            return None
        from .audio import _level_snapshot_from_samples, _alsa_card_for_device_name
        name = self._device_actual_name or self.device_name_hint or "AudioMoth"
        # Cached — see AudioCapture.get_live_level_snapshot for why this must
        # never re-shell-out to `arecord -l` on every poll tick, and must
        # stay outside self._lock (also held by the real-time audio callback).
        if not hasattr(self, "_alsa_card_cache"):
            self._alsa_card_cache = _alsa_card_for_device_name(name)
        alsa_card = self._alsa_card_cache
        with self._lock:
            chunks = [c for _, c in self._raw_buffer]
        if not chunks:
            return {
                "name": name, "role": "bat",
                "sd_index": self._device_index, "alsa_card": alsa_card, "sr": self._sample_rate,
                "db": None, "peak": None, "bins": [0] * n_bins,
                "error": "no buffered audio yet",
            }
        audio = np.concatenate(chunks)
        sr = self._sample_rate or 192000
        n_samples = int(window_seconds * sr)
        if n_samples > 0 and len(audio) > n_samples:
            audio = audio[-n_samples:]
        return _level_snapshot_from_samples(
            audio, name=name, role="bat",
            sr=sr, n_bins=n_bins, extra={"sd_index": self._device_index, "alsa_card": alsa_card},
        )

    def get_recent_audio_samples(self, seconds: float = 4.0) -> Optional[dict]:
        """
        Same purpose and same "read the buffer we already have, don't open
        a second ALSA handle" reasoning as AudioCapture.get_recent_audio_
        samples() (audio.py) — returns the last `seconds` of RAW ultrasonic
        audio for listening to the AudioMoth, not just watching
        its level. Reads self._raw_buffer, the exact same buffer
        get_live_level_snapshot() above already reads.

        Unlike the bird path, this is inaudible as-is — bat
        echolocation runs ~15-120kHz, well above human hearing — so the
        caller (status_server.py) is expected to apply the same time-
        expansion downshift the server's own downshift_bat_clip() already
        uses for post-hoc review of full recordings, not play these
        samples back untouched. Returns None if the detector isn't
        running, matching get_live_level_snapshot()'s own convention.
        """
        if not self._running or self._device_index is None:
            return None
        from .audio import _alsa_card_for_device_name
        name = self._device_actual_name or self.device_name_hint or "AudioMoth"
        if not hasattr(self, "_alsa_card_cache"):
            self._alsa_card_cache = _alsa_card_for_device_name(name)
        alsa_card = self._alsa_card_cache
        with self._lock:
            chunks = [c for _, c in self._raw_buffer]
        sr = self._sample_rate or 192000
        if not chunks:
            return {
                "name": name, "role": "bat",
                "sd_index": self._device_index, "alsa_card": alsa_card, "sr": sr,
                "audio": None, "error": "no buffered audio yet",
            }
        audio = np.concatenate(chunks)
        n_samples = int(seconds * sr)
        if n_samples > 0 and len(audio) > n_samples:
            audio = audio[-n_samples:]
        return {
            "name": name, "role": "bat",
            "sd_index": self._device_index, "alsa_card": alsa_card, "sr": sr,
            "audio": audio.copy(), "error": None,
        }

    # ── Capture callback ─────────────────────────────────────────────────────────

    def set_gain_db(self, gain_db: float) -> None:
        """
        Update the gain applied to this already-running stream in place —
        mirrors AudioStream.set_gain_db in audio.py exactly. gain_linear is
        read fresh from this instance attribute on every audio chunk in
        _on_audio(), so a config push changes it immediately without
        stopping or reopening the ultrasonic capture stream.
        """
        self.gain_db = gain_db
        self.gain_linear = 10 ** (gain_db / 20.0)

    def _on_audio(self, indata, frames, time_info, status) -> None:
        self._last_callback_at = time.time()
        mono = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
        if self.gain_linear != 1.0:
            mono = (mono.astype(np.float32) * self.gain_linear)
        with self._lock:
            self._raw_buffer.append((time.time(), mono))
            self._analysis_buffer = np.concatenate([self._analysis_buffer, mono])
        # Run analysis once we have a full window's worth of samples
        win_samples = int(self._sample_rate * ANALYSIS_WINDOW_SECONDS)
        if len(self._analysis_buffer) >= win_samples:
            with self._lock:
                chunk = self._analysis_buffer[:win_samples]
                self._analysis_buffer = self._analysis_buffer[win_samples:]
            try:
                self._analyze_window(chunk)
            except Exception as e:
                logger.debug("Bat detector analysis error: %s", e)
        # Checked unconditionally on every callback, independent of whether
        # _analyze_window ran this time (and independent of its several
        # early-return paths, e.g. no signal in the band at all) — a pulse
        # train "ending" is defined by an absence of new pulses, which is
        # exactly the case where _analyze_window would have nothing to do.
        # Cheap (a list-empty check plus one timestamp comparison in the
        # common case), safe to run at full callback rate.
        try:
            self._check_pending_event_timeout(time.time())
        except Exception as e:
            logger.debug("Bat detector event-timeout check error: %s", e)

        # ── Periodic heartbeat ────────────────────────────────────────────────
        # Runs on every audio callback but self-throttled to roughly once
        # per _heartbeat_interval_s, matching watcher.py's own "♥ Status"
        # heartbeat so the two are easy to correlate in the log stream.
        now_hb = time.time()
        if now_hb - self._last_heartbeat >= self._heartbeat_interval_s:
            self._last_heartbeat = now_hb
            try:
                level_db = rms_db(mono)
                self._last_level_db = level_db
                logger.info(
                    "♥ Bat detector | level=%.0fdBFS | active_hours=%s | pulses_seen=%d | events_fired=%d",
                    level_db, self._is_active_hour(), self._total_pulses_seen, self._total_events_fired,
                )
            except Exception as e:
                logger.debug("Bat detector heartbeat error: %s", e)
            # Ambient diagnostic capture — see dump_ambient_diagnostic()'s
            # docstring for what this is for. Checked on the same cadence as
            # the heartbeat rather than every callback: a stat() call per
            # audio callback (hundreds/sec) would be wasteful, and there's
            # no reason this needs sub-minute latency — it's a manual,
            # one-off diagnostic request, not a real-time control.
            try:
                if self._ambient_trigger_path.exists():
                    self._ambient_trigger_path.unlink(missing_ok=True)
                    self.dump_ambient_diagnostic()
            except Exception as e:
                # Was logger.debug — invisible at the INFO level this
                # deployment actually runs at, which meant a real failure
                # here would look identical to "nothing happened," exactly
                # the class of silent gap this whole feature exists to
                # avoid repeating.
                logger.warning("Bat detector ambient-diagnostic trigger check error: %s", e)

    def get_status(self) -> dict:
        """Current status for reporting to the server (see server_sync.py's
        heartbeat) — same numbers as the log heartbeat above, just structured
        for a JSON payload instead of a log line.

        sample_rate specifically: the ACTUAL rate this AudioMoth reported
        over USB and is currently streaming at (see start()'s device-name
        parsing) — not a configured/assumed value. Added because
        confirming this previously required either watching this process's
        own startup log line or using the separate AudioMoth USB
        Microphone App on another machine; surfacing it here means it's
        visible directly in Chirp's own Settings/Diagnostics UI, useful
        for exactly the kind of "is this the rate I think it's at"
        question that comes up when investigating a suspected sample-rate-
        dependent artifact (self-noise/aliasing at a given rate is a
        documented AudioMoth behavior, not unique to this deployment —
        see AUDIT_REPORT.md's wobble-investigation notes)."""
        return {
            "enabled": self.enabled,
            "level_db": getattr(self, "_last_level_db", None),
            "active_hours": self._is_active_hour(),
            "pulses_seen": self._total_pulses_seen,
            "events_fired": self._total_events_fired,
            "last_heartbeat_age_s": (time.time() - self._last_heartbeat) if self._last_heartbeat else None,
            "sample_rate": self._sample_rate,
        }

    # ── Pulse / event detection ──────────────────────────────────────────────────

    def _analyze_window(self, chunk: np.ndarray) -> None:
        sr = self._sample_rate
        n_fft = 256
        hop = 64
        if len(chunk) < n_fft:
            return

        freqs, times, Zxx = sps.stft(chunk, fs=sr, nperseg=n_fft, noverlap=n_fft - hop)
        mag = np.abs(Zxx)

        band_mask = (freqs >= BAND_LOW_HZ) & (freqs <= BAND_HIGH_HZ)
        if not band_mask.any():
            return
        band_energy = mag[band_mask, :].sum(axis=0)

        # Rolling noise floor (simple exponential average of the quiet frames)
        quiet_level = np.percentile(band_energy, 20)
        if self._noise_floor is None:
            self._noise_floor = quiet_level
        else:
            self._noise_floor = 0.9 * self._noise_floor + 0.1 * quiet_level
        floor = max(self._noise_floor, 1e-6)

        snr = band_energy / floor
        above = snr > PULSE_SNR_THRESHOLD
        if not above.any():
            return

        # Group contiguous "above threshold" frames into candidate pulses
        frame_dt = hop / sr
        idx = np.where(above)[0]
        groups: List[List[int]] = []
        cur = [idx[0]]
        for i in idx[1:]:
            if i - cur[-1] <= 1:
                cur.append(i)
            else:
                groups.append(cur)
                cur = [i]
        groups.append(cur)

        now = time.time()
        band_freqs = freqs[band_mask]
        for g in groups:
            duration_ms = (len(g) * frame_dt) * 1000
            if not (PULSE_MIN_MS <= duration_ms <= PULSE_MAX_MS):
                continue
            # Dominant frequency per frame within the pulse, to check for a sweep
            frame_peaks = [band_freqs[np.argmax(mag[band_mask, fi])] for fi in g]
            peak_freq = float(np.median(frame_peaks))
            freq_range = max(frame_peaks) - min(frame_peaks)
            swept = freq_range > 0.15 * peak_freq  # >15% frequency excursion

            pulse = Pulse(timestamp=now, peak_freq_hz=peak_freq,
                          duration_ms=duration_ms, swept=swept)
            self._register_pulse(pulse)

    def _is_active_hour(self) -> bool:
        """Return True if the current local time is within the configured bat-active window."""
        if not self.active_hours_start or not self.active_hours_end:
            return True  # no gating configured — always active
        try:
            now = datetime.now()
            h_now  = now.hour * 60 + now.minute
            sh, sm = self.active_hours_start.split(":")
            eh, em = self.active_hours_end.split(":")
            start_m = int(sh) * 60 + int(sm)
            end_m   = int(eh) * 60 + int(em)
            if start_m <= end_m:
                return start_m <= h_now <= end_m
            else:
                # Wraps midnight (e.g. 20:00–06:00)
                return h_now >= start_m or h_now <= end_m
        except Exception:
            return True

    def _register_pulse(self, pulse: Pulse) -> None:
        """
        Accumulate this pulse into the currently-open pending event. Does
        NOT evaluate or fire anything itself — see _check_pending_event_timeout,
        called on every analysis window regardless of whether that window
        contained a pulse, which is what actually decides when a pulse
        train has ended and finalizes/uploads the event covering the whole
        thing. Splitting these two concerns is what makes it possible to
        wait for a real gap of silence instead of firing the instant a
        minimum pulse count is reached.
        """
        self._pending_pulses.append(pulse)
        self._total_pulses_seen += 1

    def _check_pending_event_timeout(self, now: float) -> None:
        """
        Called on every analysis window (see _on_audio -> _analyze_window),
        independent of whether THIS window contained a pulse — a pulse
        train ending is defined by the ABSENCE of new pulses for
        event_gap_seconds, which can only be detected by checking elapsed
        time on an ongoing basis, not just reactively when a new pulse
        arrives. If the gap has passed, finalizes whatever pulses
        accumulated in the pending event (the FULL train, first pulse to
        last — not just the first few) and evaluates it as one event.
        """
        if not self._pending_pulses:
            return
        if now - self._pending_pulses[-1].timestamp < self.event_gap_seconds:
            return

        pulses = self._pending_pulses
        self._pending_pulses = []
        self._finalize_event(pulses)

    def _finalize_event(self, pulses: List[Pulse]) -> None:
        """
        Evaluate a complete, closed pulse train (already confirmed ended by
        a real gap of silence) against the noise-rejection filters and, if
        it passes, build and upload the BatActivityEvent covering the
        ENTIRE train from first pulse to last — the actual fix for "only a
        couple pulses in each clip": the event's time span is no longer
        capped at whatever happened to be in a fixed lookback window at the
        moment a minimum threshold was crossed.
        """
        if len(pulses) < self.min_pulses_for_event:
            return

        # ── Time-of-day gate ─────────────────────────────────────────────────
        if not self._is_active_hour():
            logger.debug(
                "Bat detector: suppressed event at %s — outside active hours %s–%s",
                datetime.now().strftime("%H:%M"),
                self.active_hours_start, self.active_hours_end,
            )
            return

        # ── Machine-noise rejection ───────────────────────────────────────────
        train_duration = max(1e-6, pulses[-1].timestamp - pulses[0].timestamp)
        pulse_rate = len(pulses) / train_duration
        swept_frac = float(np.mean([p.swept for p in pulses]))

        # Filter 1: swept fraction — real echolocation calls sweep in frequency;
        # broadband machine noise (lawnmowers, motors) produces flat-spectrum bursts.
        if self.min_swept_fraction > 0 and swept_frac < self.min_swept_fraction:
            logger.debug(
                "Bat detector: suppressed event — swept_fraction %.2f < min %.2f "
                "(likely machine/broadband noise)",
                swept_frac, self.min_swept_fraction,
            )
            return

        # Filter 2: pulse rate — real bats pulse at 5-30 calls/sec;
        # continuous noise produces extremely high apparent pulse rates.
        # Computed over the train's own actual duration now (not a fixed
        # window), since trains are variable-length by design.
        if pulse_rate > self.max_pulse_rate:
            logger.debug(
                "Bat detector: suppressed event — pulse_rate %.1f/s > max %.1f/s "
                "(continuous noise source)",
                pulse_rate, self.max_pulse_rate,
            )
            return

        # Filter 3: minimum peak frequency sanity check
        median_freq = float(np.median([p.peak_freq_hz for p in pulses]))
        if median_freq < self.min_peak_freq_hz:
            logger.debug(
                "Bat detector: suppressed event — peak_freq %.0fHz < min %.0fHz",
                median_freq, self.min_peak_freq_hz,
            )
            return

        # ── Interference flagging (not rejection) ───────────────────────────
        # A smoothly-oscillating electrical/mechanical noise source (a
        # switching power supply's ripple, RF pickup from a nearby Pi —
        # both real, documented issues on AudioMoth-as-USB-mic setups) can
        # genuinely sweep in frequency (passing Filter 1) and pulse slowly
        # enough to not trip the pulse-rate ceiling (Filter 2) either — so
        # neither existing filter catches it. What DOES distinguish it: a
        # real bat, being alive rather than a fixed oscillator, never
        # produces perfectly metronomic timing between calls. Computed as
        # coefficient of variation (stdev/mean) of inter-pulse intervals —
        # unitless, so it's comparable across events regardless of how
        # fast or slow the pulse rate itself is.
        timing_cv = None
        likely_interference = False
        if len(pulses) >= 4:
            intervals = np.diff([p.timestamp for p in pulses])
            if len(intervals) > 0 and np.mean(intervals) > 0:
                timing_cv = float(np.std(intervals) / np.mean(intervals))
                likely_interference = timing_cv < self.min_timing_cv_for_real
                if likely_interference:
                    logger.debug(
                        "Bat detector: flagged (not rejected) — timing_cv %.3f < %.3f "
                        "(unusually regular spacing, possible electrical/mechanical interference "
                        "rather than a real bat pass)",
                        timing_cv, self.min_timing_cv_for_real,
                    )
                    if self.discard_likely_interference:
                        logger.info(
                            "Bat detector: discarding event (discard_likely_interference is on) — "
                            "timing_cv %.3f, %d pulses, peak %.0fHz",
                            timing_cv, len(pulses), median_freq,
                        )
                        return

        event = BatActivityEvent(
            started_at=datetime.fromtimestamp(pulses[0].timestamp, tz=timezone.utc),
            ended_at=datetime.fromtimestamp(pulses[-1].timestamp, tz=timezone.utc),
            pulse_count=len(pulses),
            peak_freq_hz=median_freq,
            mean_pulse_duration_ms=float(np.mean([p.duration_ms for p in pulses])),
            swept_fraction=swept_frac,
            sample_rate=self._sample_rate,
            timing_cv=timing_cv,
            likely_interference=likely_interference,
        )
        self._total_events_fired += 1

        raw_audio = self._extract_event_audio(event)

        try:
            event.clip_path = self._save_snippet(event, raw_audio)
        except Exception as e:
            logger.debug("Bat detector: snippet save failed: %s", e)

        self._log_event(event)
        uploaded = self._upload_to_server(event, raw_audio)
        if uploaded and not self.keep_local_snippets and event.clip_path:
            try:
                Path(event.clip_path).unlink(missing_ok=True)
            except Exception as e:
                # Non-fatal — the file just lingers this once rather than
                # blocking anything; not worth failing the whole event over.
                logger.debug("Bat detector: could not remove local snippet after upload: %s", e)

        for cb in self._callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.warning("Bat detector callback error: %s", e)

    # ── Snippet extraction, local logging, and server upload ─────────────────────

    def _extract_event_audio(self, event: BatActivityEvent) -> Optional[np.ndarray]:
        """
        Pull the raw (native sample rate, un-shifted) audio covering this
        event's time window out of the rolling capture buffer. Shared by
        both the local time-expanded snippet save and the server upload —
        the server gets this RAW audio and decides whether/how to downshift
        it (mirrors how bird audio enhancement is entirely server-side).
        """
        with self._lock:
            chunks = list(self._raw_buffer)
        if not chunks:
            return None

        start_t = event.started_at.timestamp() - self.snippet_padding_seconds
        end_t = event.ended_at.timestamp() + self.snippet_padding_seconds

        # A pulse train barely reaching min_pulses_for_event can span well
        # under a second on its own, and fixed padding alone isn't much
        # added to such a short span. If the padded window is still
        # shorter than snippet_min_seconds, expand it symmetrically (equal
        # extra time before and after, not tacked onto one end) until it
        # reaches that floor, so every saved clip has at least this much
        # context regardless of how brief the underlying pass was.
        current_span = end_t - start_t
        if current_span < self.snippet_min_seconds:
            extra = (self.snippet_min_seconds - current_span) / 2.0
            start_t -= extra
            end_t += extra

        selected = [c for ts, c in chunks if start_t <= ts <= end_t]
        if not selected:
            selected = [c for _, c in chunks][-10:]  # fallback: most recent chunks
        audio = np.concatenate(selected) if selected else np.zeros(0, dtype=np.float32)
        max_samples = int(self.snippet_max_seconds * self._sample_rate)
        if len(audio) > max_samples:
            audio = audio[-max_samples:]
        if len(audio) < self._sample_rate * 0.05:
            return None
        return audio

    def _save_snippet(self, event: BatActivityEvent, audio: Optional[np.ndarray]) -> Optional[str]:
        """
        Save a time-expanded WAV of the activity window LOCALLY so a person
        can listen to it directly on the device without needing the server —
        raw ultrasonic audio played back at its native rate is silent to
        human ears. "Time expansion" here just means writing the same
        high-rate samples into a WAV tagged at a much lower nominal sample
        rate (no resampling/DSP needed) — exactly what dedicated
        bat-detector software does for human playback. This divides every
        frequency down by the same factor, e.g. a 40kHz call becomes a
        clearly audible ~4kHz tone at 10x expansion.

        This is independent of (and in addition to) the server upload below
        — the server gets the RAW audio and generates its own downshifted
        version on demand, so the two paths don't need to agree on exactly
        how the downshift is done.
        """
        if not _SF_OK or audio is None:
            return None

        ts_str = event.started_at.strftime("%Y%m%d_%H%M%S")
        out_path = self.events_dir / f"bat_{ts_str}_timeexpand10x.wav"
        expansion = 10
        sf.write(str(out_path), audio, int(self._sample_rate / expansion), subtype="PCM_16")
        return str(out_path)

    def dump_ambient_diagnostic(self) -> Optional[dict]:
        """
        On-demand diagnostic capture of whatever's currently sitting in the
        rolling raw-audio buffer — NOT tied to a bat pulse train, just
        "whatever this mic has heard in roughly the last _RAW_BUFFER_SECONDS".

        Exists specifically to unblock the AudioMoth interference
        investigation: bat_detector.py holds the ultrasonic mic device open
        exclusively (see start()), so a separate script like
        test_mic_noise.py can never sample from it while this service is
        running — any prior comparison that stopped chirp-device first was
        therefore comparing "everything off" against "everything off", not
        a real fan-on/fan-off or normal-operation test. This method reuses
        audio the device is already capturing as part of its normal job, so
        no second process, no exclusive-lock conflict, no need to stop
        anything.

        Triggered by the presence of `self._ambient_trigger_path` (checked
        on the heartbeat cadence — see _on_audio) rather than called
        directly, so the only thing a person needs to do on the device is:

            touch ~/chirp/bat_events/capture_ambient.trigger

        (adjust the path if bat_echolocation.events_dir is customized in
        config.yaml) and wait up to _heartbeat_interval_s for it to fire.
        Two files get written: the raw native-rate capture (for accurate
        frequency measurement) and a 10x time-expanded copy (for a quick
        listen — human ears can't hear the raw ultrasonic-rate file at all).

        Saves regardless of whether _SF_OK / soundfile is available for the
        raw dump specifically (raw dump only needs numpy.save as a
        fallback) — worth having even in a stripped-down environment where
        soundfile might not be installed, since the raw samples plus sample
        rate are all a later offline analysis actually needs.
        """
        with self._lock:
            # _raw_buffer holds (timestamp, audio_chunk) tuples, not bare
            # arrays — same shape _extract_event_audio unpacks a few
            # methods up. Concatenating the raw tuples directly (an
            # earlier version of this method did exactly that) fails with
            # numpy's "inhomogeneous shape" error, since each tuple is a
            # (scalar, array) pair, not two same-shaped arrays.
            chunks = [c for _, c in self._raw_buffer]
        if not chunks:
            logger.warning("dump_ambient_diagnostic: raw buffer is empty, nothing to save")
            return None
        audio = np.concatenate(chunks)

        self.events_dir.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        result = {"duration_s": len(audio) / self._sample_rate, "sample_rate": self._sample_rate}

        if _SF_OK:
            raw_path = self.events_dir / f"ambient_diag_{ts_str}_raw.wav"
            sf.write(str(raw_path), audio, self._sample_rate, subtype="PCM_16")
            result["raw_path"] = str(raw_path)

            expansion = 10
            expanded_path = self.events_dir / f"ambient_diag_{ts_str}_timeexpand10x.wav"
            sf.write(str(expanded_path), audio, int(self._sample_rate / expansion), subtype="PCM_16")
            result["expanded_path"] = str(expanded_path)
        else:
            # Fallback so the capture isn't lost entirely if soundfile isn't
            # installed — .npy plus the sample_rate recorded above is
            # enough for offline analysis (e.g. scipy.io.wavfile.write, or
            # loading directly in numpy) even without soundfile.
            npy_path = self.events_dir / f"ambient_diag_{ts_str}_raw.npy"
            np.save(str(npy_path), audio)
            result["raw_path"] = str(npy_path)
            logger.warning("dump_ambient_diagnostic: soundfile unavailable, saved raw samples as .npy instead of .wav")

        logger.info("Ambient diagnostic capture saved: %s (%.1fs @ %dHz)",
                     result.get("raw_path"), result["duration_s"], self._sample_rate)
        return result

    def _upload_to_server(self, event: BatActivityEvent, audio: Optional[np.ndarray]) -> bool:
        """
        POST this event to every configured upload target (see
        self._upload_targets, resolved in __init__ — real gap found and
        fixed: this used to post to a single hardcoded server_sync URL,
        so a bat event only ever reached whichever server happened to be
        upload.targets[0], never any additional configured target, even
        though regular bird recordings correctly reach every one). Never
        raises — a failed upload just means the event stays local-only
        (still in bat_events.jsonl), exactly like how a failed bird
        recording upload gets retried/queued rather than crashing the
        detector.

        Returns whether the FIRST (primary) target's upload succeeded —
        matching uploader.py's own policy that only the first target
        decides whether the local snippet file is safe to delete (see
        keep_local_snippets): deleting on a failed primary upload would
        destroy the only copy that exists, even if a secondary target
        happened to succeed.
        """
        if not (_REQUESTS_OK and self._upload_targets):
            return False

        data = {
            "started_at": event.started_at.isoformat(),
            "ended_at": event.ended_at.isoformat(),
            "pulse_count": str(event.pulse_count),
            "peak_freq_hz": str(event.peak_freq_hz),
            "sample_rate": str(event.sample_rate),
            "mean_pulse_duration_ms": str(event.mean_pulse_duration_ms),
            "swept_fraction": str(event.swept_fraction),
            "device_serial": self._device_serial,
        }
        if event.timing_cv is not None:
            data["timing_cv"] = str(event.timing_cv)
        data["likely_interference"] = str(event.likely_interference)

        # The same audio bytes are POSTed to every target — built once
        # up front rather than per-target, since re-encoding identical
        # audio N times for N targets would be pure waste.
        raw_wav_bytes = None
        if _SF_OK and audio is not None:
            try:
                import io
                _buf = io.BytesIO()
                sf.write(_buf, audio, self._sample_rate, format="WAV", subtype="PCM_16")
                raw_wav_bytes = _buf.getvalue()
            except Exception as e:
                logger.debug("Bat detector: could not prepare audio for upload: %s", e)

        try:
            import certifi as _c; import os as _o; _ca = _c.where()
            _verify = _ca if _o.path.exists(_ca) else "/etc/ssl/certs/ca-certificates.crt"
        except Exception:
            _verify = "/etc/ssl/certs/ca-certificates.crt"

        primary_success = False
        for i, target in enumerate(self._upload_targets):
            files = {"file": ("bat_raw.wav", raw_wav_bytes, "audio/wav")} if raw_wav_bytes else None
            try:
                resp = requests.post(
                    f"{target['base_url']}/api/v1/bat-activity/upload",
                    headers={target["auth_header"]: target["api_key"]},
                    data=data, files=files, timeout=30,
                    verify=_verify,
                )
                if resp.status_code in (200, 201):
                    logger.info("Bat activity uploaded to %s (id=%s)",
                               target["name"], resp.json().get("id", "?"))
                    if i == 0:
                        primary_success = True
                else:
                    logger.warning("Bat activity upload to %s failed: HTTP %d %s",
                                  target["name"], resp.status_code, resp.text[:200])
            except Exception as e:
                logger.warning("Bat detector: upload to %s failed: %s", target["name"], e)
        return primary_success

    def _log_event(self, event: BatActivityEvent) -> None:
        record = {
            "started_at": event.started_at.isoformat(),
            "ended_at": event.ended_at.isoformat(),
            "pulse_count": event.pulse_count,
            "peak_freq_hz": round(event.peak_freq_hz, 1),
            "mean_pulse_duration_ms": round(event.mean_pulse_duration_ms, 2),
            "swept_fraction": round(event.swept_fraction, 2),
            "timing_cv": round(event.timing_cv, 3) if event.timing_cv is not None else None,
            "likely_interference": event.likely_interference,
            "sample_rate": event.sample_rate,
            "clip_path": event.clip_path,
        }
        try:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.warning("Bat detector: could not write event log: %s", e)
        logger.info(
            "Bat activity detected: %d pulses, peak ~%.0f kHz, %.0f%% swept — %s",
            event.pulse_count, event.peak_freq_hz / 1000,
            event.swept_fraction * 100, event.clip_path or "(no clip)",
        )
