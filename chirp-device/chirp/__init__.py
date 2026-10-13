"""
BirdWatch - Raspberry Pi Bird Call Detection System
"""
import os as _os


def _read_version() -> str:
    """
    Real single source of truth for chirp-device's own version — a
    genuine gap found while investigating an unrelated AudioMoth crash
    report: this project had TWO separate, both-stale, mutually
    inconsistent hardcoded version strings (this file's own
    __version__, frozen at "1.0.0", and server_sync.py's own VERSION,
    separately frozen at "1.1.0") — neither reflecting the real,
    substantially more mature state of this codebase, and __version__
    itself was never even read anywhere in the actual code. Reads a
    real VERSION file (same convention already used by chirp-server and
    chirp-server-instances) with a safe fallback if it's ever missing,
    rather than hardcoding a string here that will just go stale again
    the same way.
    """
    version_path = _os.path.join(_os.path.dirname(__file__), "..", "VERSION")
    try:
        with open(version_path) as f:
            return f.read().strip()
    except OSError:
        return "unknown"


__version__ = _read_version()
__author__ = "BirdWatch"
