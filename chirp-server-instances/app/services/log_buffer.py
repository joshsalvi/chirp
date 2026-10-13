"""
In-process log ring buffer.

A custom logging.Handler captures every record emitted within the server process
and stores it in a fixed-size deque. The /api/v1/logs endpoints read from this
buffer for the live "server logs" view.

The buffer is module-level so it survives across requests in the same worker.
WebSocket clients are tracked separately to receive push updates.
"""

import logging
import threading
from collections import deque
from datetime import datetime
from typing import List

MAX_LINES = 2000   # keep the last N log records in memory


class LogRecord:
    """Lightweight serialisable log record."""
    __slots__ = ("ts", "level", "name", "msg")

    def __init__(self, ts: str, level: str, name: str, msg: str):
        self.ts    = ts
        self.level = level
        self.name  = name
        self.msg   = msg

    def to_dict(self) -> dict:
        return {"ts": self.ts, "level": self.level, "name": self.name, "msg": self.msg}


class _RingBufferHandler(logging.Handler):
    """Thread-safe logging handler that appends to a deque."""

    def __init__(self, buf: deque, lock: threading.Lock):
        super().__init__()
        self._buf  = buf
        self._lock = lock

    def emit(self, record: logging.LogRecord) -> None:
        try:
            ts  = datetime.utcfromtimestamp(record.created).strftime("%H:%M:%S")
            msg = self.format(record)
            rec = LogRecord(ts=ts, level=record.levelname, name=record.name, msg=msg)
            with self._lock:
                self._buf.append(rec)
        except Exception:
            pass  # never crash the caller


# ── Singletons ─────────────────────────────────────────────────────────────────
_buf:  deque       = deque(maxlen=MAX_LINES)
_lock: threading.Lock = threading.Lock()
_handler: _RingBufferHandler | None = None


def install() -> None:
    """Install the ring-buffer handler on the root logger.  Call once at startup."""
    global _handler
    if _handler is not None:
        return   # already installed
    _handler = _RingBufferHandler(_buf, _lock)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _handler.setLevel(logging.DEBUG)
    logging.getLogger().addHandler(_handler)
    logging.getLogger().setLevel(logging.DEBUG)
    # The root logger is at DEBUG for Chirp's own loggers; libraries at DEBUG
    # flooded the log (matplotlib scored every font for each spectrogram,
    # httpcore logged every connection step, Bird Buddy every GraphQL call).
    for name in _QUIET_LIBRARIES:
        logging.getLogger(name).setLevel(logging.WARNING)


_QUIET_LIBRARIES = (
    "matplotlib", "PIL", "httpcore", "hpack", "h2", "urllib3", "asyncio",
    "birdbuddy", "gql", "websockets", "multipart", "python_multipart",
    "charset_normalizer", "numba", "botocore", "aiosqlite", "watchfiles",
)


def get_lines(n: int = 500, level: str = "") -> List[dict]:
    """Return the last *n* records, optionally filtered by level prefix."""
    level_upper = level.upper() if level else ""
    with _lock:
        records = list(_buf)
    if level_upper:
        records = [r for r in records if r.level == level_upper]
    return [r.to_dict() for r in records[-n:]]


def clear() -> None:
    with _lock:
        _buf.clear()
