"""
Chirp Device — Local Status / Live-Levels HTTP Server
=======================================================

Root cause of "dsnoop still erroring on some cards" (handoff, known issue #1):

The bird pipeline (AudioCapture, via sounddevice/PortAudio) and the bat
pipeline (BatDetector, via sounddevice/PortAudio) each open their ALSA
capture device directly through PortAudio's raw `hw:` enumeration. That is
an EXCLUSIVE open. ALSA's dsnoop plugin only allows concurrent readers when
*every* reader — including the first one — opens the device through dsnoop.
Since chirp-device is the first (and exclusive) opener here, a second
process racing to open `dsnoop:CARD=N,DEV=0` on the same card (the old
SSH + `arecord` diagnostics script) fails with "device busy" no matter which
device string it falls back to. This isn't a config problem fixable with an
`.asoundrc` tweak — it's a structural consequence of how chirp-device opens
its own hardware.

Rather than re-architect the primary capture path to go through dsnoop
(materially riskier: it would touch the live detection pipeline, and would
still need a system-level `/etc/asound.conf` change plus a one-time service
restart), this module sidesteps the problem entirely. AudioCapture and
BatDetector already hold the most recent audio in memory (pre-roll ring
buffer / per-device raw buffers) for their own purposes. We just publish
that already-captured data over a small local HTTP server. No second ALSA
open happens at all for any card chirp-device manages.

Cards chirp-device does NOT manage (e.g. an excluded/unused USB device) are
simply not reported here — the server's diagnostics page falls back to the
previous SSH + arecord approach for those, which still works fine since
nothing else holds them open.

Endpoints:
    GET /health          -> {"status": "ok", "version": "..."}
    GET /levels          -> {"streams": [...], "ts": <unix time>}
    GET /listen/<index>  -> audio/wav — a few seconds of RAW audio from
                             stream <index> (same ordering as /levels'
                             streams list), for LISTENING to what
                             a specific mic is picking up (static,
                             clipping, wrong mic, etc.), not just seeing a
                             level number for it. Same "already-captured
                             buffer, no second ALSA open" data source as
                             /levels — see AudioCapture.get_recent_audio_
                             samples()'s own docstring. Deliberately a
                             short polled clip, not a true low-latency
                             stream: the server side re-requests this every
                             few seconds and plays each clip back to back,
                             which is simple, robust, and more than
                             sufficient for a mic-quality check — continuous
                             streaming would need a real-time
                             transport (WebSocket + client-side buffering/
                             jitter handling) for a use case that doesn't
                             need sub-second latency.

Auth: shared-secret header `X-Chirp-Key`, reusing the SAME api_key
chirp-device already uses to authenticate itself to the server
(server_sync.api_key). No new credential to manage. If no key is configured
(empty string), auth is skipped — acceptable for a LAN-only, read-only,
non-destructive status endpoint, but a key is set by default via main.py.
"""

import io
import json
import logging
import re
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8766

_LISTEN_PATH_RE = re.compile(r"^/listen/(\d+)$")


def _samples_to_wav_bytes(samples, sample_rate: int, expansion_factor: int = 1) -> bytes:
    """
    float32 [-1, 1] numpy samples -> a 16-bit PCM mono WAV file's raw
    bytes, using Python's own stdlib `wave` module — no numpy/scipy audio-
    encoding dependency needed for something this simple. Clips rather than
    wraps on out-of-range samples (a hot/clipping mic should sound clipped
    when you listen to it, which is itself useful diagnostic information —
    silently rescaling it away would hide exactly the problem this feature
    exists to reveal).

    expansion_factor > 1 applies the same time-expansion downshift the
    server's own AudioProcessor.downshift_bat_clip() uses for post-hoc bat
    clip review — write the SAME samples, just tagged with a lower declared
    sample rate. No resampling/DSP needed: dividing the declared rate by N
    divides every frequency in the signal by N and slows playback by the
    same factor, which is exactly what turns an inaudible ~40kHz
    echolocation call into a clearly audible ~4kHz tone at the default
    10x factor. Used for the AudioMoth's /listen clips specifically (see
    do_GET below) — genuinely inaudible otherwise, unlike the bird path.
    """
    import numpy as np
    clipped = np.clip(samples, -1.0, 1.0)
    # Explicit little-endian dtype ('<i2'), not just int16 — int16 follows
    # the host platform's native byte order, which happens to be
    # little-endian on every chirp-device target (x86/ARM) but WAV's
    # own format requires little-endian regardless of host, so pin it
    # explicitly rather than relying on that coincidence holding forever.
    pcm16 = (clipped * 32767.0).astype("<i2")
    buf = io.BytesIO()
    declared_rate = max(1, int(sample_rate / max(1, expansion_factor)))
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(declared_rate)
        wf.writeframes(pcm16.tobytes())
    return buf.getvalue()


class _StatusHandler(BaseHTTPRequestHandler):
    server_version = "ChirpStatus/1.0"

    def log_message(self, fmt, *args):
        # Route through our own logger at debug level instead of stderr.
        logger.debug("status_server: " + fmt, *args)

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass  # client disconnected mid-response — not fatal

    def _send_wav(self, status: int, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(body)))
        # Never cache a clip — every request is meant to fetch fresh,
        # currently-buffered audio, not replay a stale one the browser
        # decided to keep around.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _authorized(self) -> bool:
        expected_keys = getattr(self.server, "shared_keys", None)
        if expected_keys is None:
            # Fall back to the old single-key attribute if something
            # external still sets shared_key directly without going
            # through StatusServer's own setup — keeps this handler
            # correct even if only the legacy attribute is present.
            legacy = getattr(self.server, "shared_key", "") or ""
            expected_keys = {legacy} if legacy else set()
        if not expected_keys:
            return True
        return self.headers.get("X-Chirp-Key", "") in expected_keys

    def do_GET(self):
        try:
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
                return
            if self.path == "/health":
                self._send_json(200, {
                    "status": "ok",
                    "version": getattr(self.server, "device_version", ""),
                })
                return
            if self.path == "/levels":
                providers: List[Callable[[], object]] = getattr(self.server, "level_providers", [])
                streams = []
                for i, provider in enumerate(providers):
                    try:
                        result = provider()
                    except Exception as e:
                        # Surfaced as a visible entry rather than silently
                        # dropped — a whole stream vanishing from /levels
                        # with no trace is exactly the kind of "invisible
                        # failure" that made the original dsnoop busy-device
                        # bug hard to diagnose. An admin looking at the
                        # diagnostics page should be able to see *why* a
                        # stream is missing, not just that it's missing.
                        logger.warning("status_server: level provider #%d raised: %s", i, e)
                        streams.append({
                            "name": f"(provider #{i} error)", "role": None,
                            "db": None, "peak": None, "bins": [],
                            "error": f"{type(e).__name__}: {e}",
                        })
                        continue
                    if result is None:
                        continue
                    if isinstance(result, list):
                        streams.extend(result)
                    else:
                        streams.append(result)
                self._send_json(200, {"streams": streams, "ts": time.time()})
                return

            listen_match = _LISTEN_PATH_RE.match(self.path)
            listen_by_name = self.path.startswith("/listen?")
            if listen_match or listen_by_name:
                clip_seconds = float(getattr(self.server, "listen_clip_seconds", 4.0))
                providers: List[Callable[[float], object]] = getattr(self.server, "audio_providers", [])
                # Same flatten-a-list-of-lists-or-single-items shape /levels
                # uses above.
                all_streams = []
                for provider in providers:
                    try:
                        result = provider(clip_seconds)
                    except Exception as e:
                        logger.warning("status_server: audio provider raised: %s", e)
                        continue
                    if result is None:
                        continue
                    if isinstance(result, list):
                        all_streams.extend(result)
                    else:
                        all_streams.append(result)

                if listen_by_name:
                    # Preferred routing: match by device NAME (?name=...),
                    # not position. /levels' streams reach the browser
                    # after being merged server-side with SSH-fallback rows
                    # (see diagnostics.py's own merge step) that can
                    # interleave in an order this module has no visibility
                    # into — a positional index survives that merge only by
                    # coincidence. A name is the same stable identifier
                    # already shown in the UI either way, so matching on it
                    # instead sidesteps the whole problem rather than
                    # trying to keep two independently-computed orderings
                    # in sync.
                    from urllib.parse import urlparse, parse_qs
                    qs = parse_qs(urlparse(self.path).query)
                    wanted_name = (qs.get("name", [""])[0] or "").strip().lower()
                    # Reported directly: AudioMoth lookups 404'd here even
                    # though the same device's name matched fine elsewhere
                    # (the SSH-based mic check). Root cause: PortAudio's
                    # ALSA backend on Linux often bakes the hw-id into a
                    # device's own reported name (e.g. "...Microphone:
                    # Audio (hw:0,0)"), and different code paths that all
                    # legitimately call themselves "the device's name" can
                    # end up with or without that suffix depending on
                    # exactly when/how they captured it — this is the same
                    # class of mismatch _get_mic_info()'s own
                    # device_name_hints substring matching exists to work
                    # around, just hitting it from the other direction.
                    # Exact match first (the common case), falling back to
                    # a bidirectional substring match rather than requiring
                    # both sides to agree on the suffix.
                    entry = next((s for s in all_streams if (s.get("name") or "").strip().lower() == wanted_name), None)
                    if entry is None and wanted_name:
                        entry = next((s for s in all_streams
                                      if wanted_name in (s.get("name") or "").strip().lower()
                                      or (s.get("name") or "").strip().lower() in wanted_name), None)
                    if entry is None:
                        names = ", ".join(repr(x.get("name")) for x in all_streams) or "none"
                        hint = (" — the bat detector isn't capturing right now (starting, restarting, or stopped)"
                                if not any(x.get("role") == "bat" for x in all_streams) else "")
                        self._send_json(404, {"error": f"no stream named {wanted_name!r}; available: {names}{hint}"})
                        return
                else:
                    stream_index = int(listen_match.group(1))
                    if stream_index < 0 or stream_index >= len(all_streams):
                        self._send_json(404, {"error": f"no stream at index {stream_index} ({len(all_streams)} available)"})
                        return
                    entry = all_streams[stream_index]

                if entry.get("audio") is None:
                    self._send_json(503, {"error": entry.get("error") or "no buffered audio yet for this stream"})
                    return

                # Bat echolocation is genuinely inaudible at its native
                # rate — apply the same time-expansion downshift the
                # server's own downshift_bat_clip() uses for post-hoc
                # review, so a bat "Listen" clip actually sounds like
                # something instead of near-silence. Bird clips are
                # already in human hearing range — expansion_factor=1
                # (no-op) for those.
                expansion_factor = int(getattr(self.server, "bat_listen_expansion_factor", 10)) if entry.get("role") == "bat" else 1

                try:
                    wav_bytes = _samples_to_wav_bytes(entry["audio"], entry["sr"], expansion_factor=expansion_factor)
                except Exception as e:
                    logger.warning("status_server: WAV encoding failed: %s", e)
                    self._send_json(500, {"error": f"WAV encoding failed: {e}"})
                    return

                self._send_wav(200, wav_bytes)
                return

            self._send_json(404, {"error": "not found"})
        except Exception as e:
            logger.warning("status_server: request handling error: %s", e)
            try:
                self._send_json(500, {"error": str(e)})
            except Exception:
                pass


class StatusServer:
    """
    Background HTTP server exposing live audio levels already captured by
    the running AudioCapture / BatDetector instances.

    Started once at daemon startup. Binding failure (port already in use,
    etc.) is logged and treated as non-fatal — the server-side diagnostics
    page simply falls back to its previous SSH-based probing for every card,
    exactly as before this feature existed.
    """

    def __init__(self, config: dict, level_providers: List[Callable[[], object]],
                 audio_providers: Optional[List[Callable[[float], object]]] = None,
                 version: str = ""):
        status_cfg = (config or {}).get("status_server", {}) or {}
        self.enabled: bool = bool(status_cfg.get("enabled", True))
        self.port: int = int(status_cfg.get("port", DEFAULT_PORT))
        # How many seconds of audio each /listen/<index> request returns.
        # Kept short and deliberately server-configurable independent of
        # anything else — the server side re-polls this on a timer to
        # approximate continuous playback (see this module's own docstring
        # on why that's the chosen design over true streaming), so this
        # value is really "how big a chunk to hand back each poll", a
        # tradeoff between request overhead (fewer, bigger clips) and
        # playback latency (more, smaller clips) rather than a hard limit.
        self.listen_clip_seconds: float = float(status_cfg.get("listen_clip_seconds", 4.0))
        # Downshift factor applied automatically to bat/AudioMoth /listen
        # clips only (bird clips are already in human hearing range) — see
        # _samples_to_wav_bytes()'s own docstring. 10x matches
        # downshift_bat_clip()'s own default on the server side, so a bat
        # Listen clip and a downloaded/reviewed bat recording sound
        # consistent with each other rather than using two different
        # factors for no reason.
        self.bat_listen_expansion_factor: int = int(status_cfg.get("bat_listen_expansion_factor", 10))
        configured_key = status_cfg.get("shared_key")
        if configured_key is not None:
            # Explicit override (including "" to disable auth entirely,
            # e.g. for local testing off the Pi) always wins, unchanged
            # from before multi-target support existed.
            self.shared_keys: set = {configured_key} if configured_key else set()
        else:
            # Default: reuse the existing device→server pairing key(s) so
            # there's nothing new to provision. Investigated and fixed
            # directly after a real 401 report: this used to read only
            # server_sync.api_key, the single legacy top-level field —
            # once server_sync.targets existed, a request from any
            # target OTHER than the first was carrying a key that field
            # never held at all, so it could never match, regardless of
            # whether the request reached the Pi over the network just
            # fine (which it did — confirmed directly, this was purely
            # an auth mismatch, not a connectivity problem). Any
            # configured target's own key is now accepted, since any of
            # those servers legitimately pairs with this same device.
            sync_cfg = config.get("server_sync", {}) or {}
            target_cfgs = sync_cfg.get("targets") or [sync_cfg]
            self.shared_keys = {tc.get("api_key", "") for tc in target_cfgs if tc.get("api_key")}
        self.shared_key: str = next(iter(self.shared_keys), "")  # kept for any external reference to the old single-key attribute name

        self._level_providers = level_providers
        self._audio_providers = audio_providers or []
        self._version = version
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        if not self.enabled:
            logger.info("Status server disabled via config (status_server.enabled: false)")
            return False
        try:
            self._httpd = ThreadingHTTPServer(("0.0.0.0", self.port), _StatusHandler)
        except OSError as e:
            logger.warning(
                "Status server: could not bind 0.0.0.0:%d (%s). Not fatal — the "
                "server's diagnostics page will fall back to SSH-based mic "
                "probing for every card, same as before this feature existed.",
                self.port, e,
            )
            self._httpd = None
            return False

        self._httpd.level_providers = self._level_providers
        self._httpd.audio_providers = self._audio_providers
        self._httpd.listen_clip_seconds = self.listen_clip_seconds
        self._httpd.bat_listen_expansion_factor = self.bat_listen_expansion_factor
        self._httpd.shared_key = self.shared_key
        self._httpd.shared_keys = self.shared_keys
        self._httpd.device_version = self._version

        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="ChirpStatusServer", daemon=True
        )
        self._thread.start()
        logger.info(
            "Status server listening on 0.0.0.0:%d (auth %s) — serves /health, /levels, /listen/<index>",
            self.port, "enabled" if self.shared_key else "DISABLED (no shared_key)",
        )
        return True

    def stop(self) -> None:
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
