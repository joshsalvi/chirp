"""
BirdWatch Utilities
Logging setup, disk management, timing, and helper functions.
"""

import logging
import logging.handlers
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np


# ── Logging ──────────────────────────────────────────────────────────────────

def setup_logging(config: Dict, verbose: bool = False) -> None:
    """Configure rotating file + console logging."""
    log_cfg = config["logging"]
    level_str = "DEBUG" if verbose else log_cfg.get("level", "INFO")
    level = getattr(logging, level_str.upper(), logging.INFO)

    log_dir = Path(log_cfg["log_dir"])
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "birdwatch.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # capture everything; handlers filter

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler
    fh = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=log_cfg["max_mb"] * 1024 * 1024,
        backupCount=log_cfg["backup_count"],
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    root.addHandler(fh)

    # Console handler
    if log_cfg.get("console_output", True):
        ch = None
        import sys as _sys
        if not _sys.stdout.isatty():
            # Under systemd the console goes to the journal: one plain line
            # per record (Rich wraps long lines at 80 columns, which splits
            # detections and stats across several journal lines and breaks
            # grep). journald adds its own timestamp.
            ch = logging.StreamHandler(_sys.stdout)
            ch.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
            ch.setLevel(level)
            root.addHandler(ch)
    if log_cfg.get("console_output", True) and ch is None:
        try:
            from rich.logging import RichHandler
            from rich.console import Console
            import io as _io

            # RichHandler importing successfully does NOT guarantee
            # rich_tracebacks actually works — rich.traceback is a
            # SEPARATE module, lazily imported only the first time a real
            # exception is formatted. Confirmed as a real, live failure
            # mode on a real device: rich.logging imported fine here, but
            # rich.traceback later raised ModuleNotFoundError the first
            # time an actual error occurred — which is exactly the worst
            # time for a logging failure, since it masks the real error
            # instead of just rendering it less prettily. Proactively
            # exercise the same lazy-import path right now, against a
            # disposable test logger, so a broken rich.traceback is caught
            # here and falls back cleanly, rather than only being
            # discovered when something has already gone wrong.
            #
            # Real, confirmed bug in a previous version of this self-test:
            # it ran the test exception through the SAME RichHandler
            # instance that would go on to be used for all real future
            # logging — meaning Rich fully rendered that deliberately
            # raised, always-caught exception to the actual console/stderr
            # on every single startup, even when everything worked
            # correctly. Confirmed directly via a real journalctl log: a
            # full, scary-looking traceback printed at every boot, with no
            # real error behind it at all. Fixed by running the self-test
            # against its own separate RichHandler pointed at a throwaway,
            # in-memory Console — the lazy rich.traceback import still gets
            # genuinely exercised (a truly broken rich.traceback still
            # fails here and falls back below), but nothing from the
            # test's own output ever reaches the real console.
            _probe_console = Console(file=_io.StringIO())
            _probe_handler = RichHandler(console=_probe_console, rich_tracebacks=True)
            _probe_logger = logging.getLogger("chirp._rich_traceback_probe")
            _probe_logger.addHandler(_probe_handler)
            _probe_logger.propagate = False
            try:
                raise RuntimeError("rich_tracebacks self-test")
            except RuntimeError:
                _probe_logger.error("self-test", exc_info=True)
            _probe_logger.removeHandler(_probe_handler)

            # Only now create the REAL handler used for actual future
            # logging — confirmed rich.traceback works via the probe
            # above, without ever printing that probe's own output
            # anywhere visible.
            candidate = RichHandler(level=level, show_path=False, rich_tracebacks=True)
            candidate.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))
            ch = candidate
        except Exception as e:
            import sys as _sys
            print(f"[chirp] rich console handler unavailable ({e}) — falling back to plain StreamHandler", file=_sys.stderr)
            ch = logging.StreamHandler()
            ch.setFormatter(formatter)
            ch.setLevel(level)
        root.addHandler(ch)

    # Silence noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("sounddevice").setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging initialized: level=%s, file=%s", level_str, log_file
    )


# ── Disk Management ──────────────────────────────────────────────────────────

def get_disk_usage_gb(path: str) -> float:
    """Return total size of files in path in GB."""
    total = 0
    for f in Path(path).rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total / (1024 ** 3)


def get_free_disk_gb(path: str) -> float:
    """Return free disk space in GB on the filesystem containing path."""
    usage = shutil.disk_usage(path)
    return usage.free / (1024 ** 3)


def auto_delete_old_recordings(directory: str, max_age_days: int) -> int:
    """Delete WAV/JSON files older than max_age_days. Returns count deleted."""
    if max_age_days <= 0:
        return 0
    cutoff = time.time() - (max_age_days * 86400)
    deleted = 0
    for f in Path(directory).glob("birdwatch_*"):
        if f.is_file() and f.stat().st_mtime < cutoff:
            try:
                f.unlink()
                deleted += 1
            except OSError as e:
                logging.getLogger(__name__).warning("Could not delete %s: %s", f, e)
    return deleted


def daily_maintenance() -> dict:
    """
    Daily housekeeping for a long-running Pi process:
      1. Remove orphaned /tmp BirdNET analysis temp files. Each analysis call
         writes a temp WAV (birdwatch_*.wav) and deletes it in a `finally`
         block, but a hard crash, OOM kill, or power loss mid-analysis can
         leave these behind indefinitely — they're small individually but
         accumulate silently over weeks of uptime.
      2. Force a Python garbage collection cycle. TFLite/numpy buffers from
         thousands of analysis calls can leave fragmented memory that the
         allocator doesn't proactively return to the OS; an explicit gc.collect()
         is cheap and gives Python's allocator a chance to release it.
      3. Log current process memory (RSS) and system free memory via psutil,
         so memory creep is visible in logs over time rather than silent
         until something fails.

    Returns a dict summary for logging. Safe to call repeatedly — every step
    is a no-op if there's nothing to clean.
    """
    import gc
    import tempfile

    log = logging.getLogger(__name__)
    summary = {"tmp_files_removed": 0, "tmp_bytes_freed": 0, "gc_collected": 0}

    # 1. Orphaned /tmp analysis temp files older than 1 hour (any still-active
    #    analysis won't be older than the ~3s window it takes to process one
    #    audio chunk, so 1 hour is a generous margin against false deletion).
    tmp_dir = Path(tempfile.gettempdir())
    cutoff = time.time() - 3600
    for f in tmp_dir.glob("birdwatch_*.wav"):
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                size = f.stat().st_size
                f.unlink()
                summary["tmp_files_removed"] += 1
                summary["tmp_bytes_freed"] += size
        except OSError as e:
            log.debug("Could not remove stale tmp file %s: %s", f, e)

    # 2. Force garbage collection
    summary["gc_collected"] = gc.collect()

    # 3. Memory diagnostics (best-effort — psutil is already a dependency)
    try:
        import psutil
        proc = psutil.Process()
        summary["process_rss_mb"] = round(proc.memory_info().rss / (1024 * 1024), 1)
        summary["system_available_mb"] = round(psutil.virtual_memory().available / (1024 * 1024), 1)
    except Exception:
        pass

    log.info(
        "Daily maintenance: removed %d stale tmp file(s) (%.1f KB), "
        "gc collected %d objects%s",
        summary["tmp_files_removed"],
        summary["tmp_bytes_freed"] / 1024,
        summary["gc_collected"],
        f", RSS={summary['process_rss_mb']}MB, available={summary['system_available_mb']}MB"
        if "process_rss_mb" in summary else "",
    )
    return summary


# ── Audio Helpers ─────────────────────────────────────────────────────────────

def rms_db(audio: np.ndarray) -> float:
    """Compute RMS level in dBFS. Returns -inf for silence."""
    if len(audio) == 0:
        return -np.inf
    rms = np.sqrt(np.mean(audio.astype(np.float64) ** 2))
    if rms == 0:
        return -np.inf
    # For int16 audio, full scale is 32768
    if audio.dtype == np.int16:
        rms_normalized = rms / 32768.0
    else:
        rms_normalized = rms  # assume already normalized to [-1, 1]
    if rms_normalized <= 0:
        return -np.inf
    return 20.0 * np.log10(rms_normalized)


def normalize_audio(audio: np.ndarray) -> np.ndarray:
    """Normalize audio to float32 in range [-1, 1]."""
    if audio.dtype == np.int16:
        return audio.astype(np.float32) / 32768.0
    elif audio.dtype == np.int32:
        return audio.astype(np.float32) / 2147483648.0
    elif audio.dtype in (np.float32, np.float64):
        return audio.astype(np.float32)
    return audio.astype(np.float32)


def merge_channels(channels: List[np.ndarray]) -> np.ndarray:
    """Average multiple mono audio arrays into a single mono array.
    All arrays must have the same length."""
    if len(channels) == 1:
        return channels[0].copy()
    min_len = min(len(c) for c in channels)
    stacked = np.stack([c[:min_len].astype(np.float64) for c in channels])
    return np.mean(stacked, axis=0).astype(channels[0].dtype)


def snr_weighted_merge(channels: List[np.ndarray]) -> np.ndarray:
    """Merge channels weighted by their RMS level.

    Channels with stronger signal contribute more to the mix.
    This prevents weak or near-silent channels (e.g. cheap USB mics far
    from the source) from diluting the signal of a strong primary mic.

    Falls back to equal-weight average if all channels are at noise floor.
    """
    if len(channels) == 1:
        return channels[0].copy()
    min_len = min(len(c) for c in channels)
    arrays = [c[:min_len].astype(np.float64) for c in channels]
    weights = np.array([np.sqrt(np.mean(a ** 2)) for a in arrays])
    total = weights.sum()
    if total < 1e-10:
        # All silent — equal mix
        weights = np.ones(len(channels))
        total = float(len(channels))
    weights = weights / total
    stacked = np.stack(arrays)
    return (stacked * weights[:, np.newaxis]).sum(axis=0).astype(channels[0].dtype)


def to_stereo(left: np.ndarray, right: Optional[np.ndarray]) -> np.ndarray:
    """Combine two mono arrays into interleaved stereo. If right is None, duplicate left."""
    if right is None:
        right = left
    n = min(len(left), len(right))
    stereo = np.empty(n * 2, dtype=left.dtype)
    stereo[0::2] = left[:n]
    stereo[1::2] = right[:n]
    return stereo


# ── Timestamp Utilities ───────────────────────────────────────────────────────

def utc_now() -> datetime:
    """Current UTC datetime."""
    return datetime.now(timezone.utc)


def local_now() -> datetime:
    """Current local datetime."""
    return datetime.now()


def format_duration(seconds: float) -> str:
    """Format seconds as 'Xm Ys' string."""
    m, s = divmod(int(seconds), 60)
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


# ── Watchdog Timer ────────────────────────────────────────────────────────────

class WatchdogTimer:
    """Simple watchdog: raise alarm if not petted within timeout."""

    def __init__(self, timeout_seconds: float, name: str = "watchdog"):
        self.timeout = timeout_seconds
        self.name = name
        self._last_pet = time.monotonic()

    def pet(self) -> None:
        """Reset the watchdog timer."""
        self._last_pet = time.monotonic()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._last_pet

    @property
    def is_expired(self) -> bool:
        return self.elapsed > self.timeout

    def __str__(self) -> str:
        return f"WatchdogTimer({self.name}, timeout={self.timeout}s, elapsed={self.elapsed:.1f}s)"
