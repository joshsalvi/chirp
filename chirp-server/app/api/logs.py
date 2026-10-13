"""
Chirp — Server & Device Log API

GET /api/v1/logs/server          — recent server log lines (ring buffer)
GET /api/v1/logs/server/history  — historical lines via docker/journalctl
WS  /api/v1/logs/server/stream   — live streaming log tail
GET /api/v1/logs/devices          — list devices available for log viewing
GET /api/v1/logs/devices/{id}     — fetch device logs via SSH (existing endpoint wrapper)
"""

import asyncio
import logging
import os
import subprocess
from typing import Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import log_buffer

logger = logging.getLogger("chirp.api.logs")

router = APIRouter()


# ── Server logs ───────────────────────────────────────────────────────────────

@router.get("/server")
def get_server_logs(
    n:     int           = Query(500, ge=1, le=2000),
    level: Optional[str] = Query(None, description="Filter: DEBUG INFO WARNING ERROR CRITICAL"),
):
    """Return recent server log lines from the in-process ring buffer."""
    return {
        "source": "ring_buffer",
        "lines":  log_buffer.get_lines(n, level or ""),
        "total":  n,
    }


@router.get("/server/history")
def get_server_log_history(
    n: int = Query(500, ge=10, le=5000),
):
    """
    Return historical server log lines by reading from:
      1. docker logs (if running in Docker)
      2. journalctl for the chirp-server service
      3. /app/data/server.log (if file logging is configured)
    Falls back gracefully if none are available.
    """
    lines: list[str] = []

    # Strategy 1: docker logs of the current container
    try:
        container_id = _get_container_id()
        if container_id:
            result = subprocess.run(
                ["docker", "logs", "--tail", str(n), container_id],
                capture_output=True, text=True, timeout=10
            )
            raw = result.stdout + result.stderr
            lines = [l for l in raw.splitlines() if l.strip()]
            if lines:
                return {"source": "docker_logs", "lines": lines[-n:]}
    except Exception as _e:
        logger.debug("docker logs failed: %s", _e)

    # Strategy 2: journalctl
    try:
        result = subprocess.run(
            ["journalctl", "-u", "chirp-server", "-u", "chirp", "-n", str(n), "--no-pager", "--output=short-iso"],
            capture_output=True, text=True, timeout=8
        )
        lines = [l for l in result.stdout.splitlines() if l.strip()]
        if lines:
            return {"source": "journalctl", "lines": lines[-n:]}
    except Exception as _e:
        logger.debug("journalctl failed: %s", _e)

    # Strategy 3: log file
    log_path = os.environ.get("CHIRP_LOG_FILE", "/app/data/server.log")
    if os.path.exists(log_path):
        try:
            with open(log_path) as f:
                all_lines = f.readlines()
            lines = [l.rstrip() for l in all_lines[-n:] if l.strip()]
            if lines:
                return {"source": "file", "lines": lines}
        except Exception as _e:
            logger.debug("log file read failed: %s", _e)

    # Fallback: in-process buffer
    in_proc = log_buffer.get_lines(n)
    return {
        "source": "ring_buffer_only",
        "lines":  [f"[{r['ts']}] {r['level']:8s} {r['name']} — {r['msg']}" for r in in_proc],
        "note":   "No external log source available. Showing in-process buffer only.",
    }


@router.websocket("/server/stream")
async def stream_server_logs(ws: WebSocket):
    """
    WebSocket endpoint: pushes new log lines as they arrive.
    Sends existing buffer immediately, then tails new entries every 0.5s.
    """
    await ws.accept()
    # Send existing buffer first
    initial = log_buffer.get_lines(200)
    try:
        await ws.send_json({"type": "history", "lines": initial})
    except Exception:
        return

    # Tail new entries
    last_count = len(log_buffer._buf)
    try:
        while True:
            await asyncio.sleep(0.5)
            new_count = len(log_buffer._buf)
            if new_count > last_count:
                # Grab the new lines
                with log_buffer._lock:
                    all_records = list(log_buffer._buf)
                new_records = all_records[last_count:] if last_count < len(all_records) else []
                if new_records:
                    await ws.send_json({
                        "type": "lines",
                        "lines": [r.to_dict() for r in new_records],
                    })
                last_count = new_count
    except (WebSocketDisconnect, Exception):
        pass


# ── Device logs (wrapper around the devices endpoint) ────────────────────────

@router.get("/devices")
def list_devices_for_logs(db: Session = Depends(get_db)):
    """
    Return all paired devices with their connectivity status.

    Excludes every virtual device row — not just Haikubox. The original
    fix here only excluded platform == "Haikubox", confirmed a real bug
    (it has no real SSH access at all, so "fetch its logs via SSH" never
    made sense). But Bird Buddy virtual devices hit the exact same
    problem later and were never added to that exclusion — confirmed
    directly: they showed up in this list with "IP unknown", and
    selecting one produced "Device IP unknown — it must have heartbeated
    at least once" since a Bird Buddy device is a cloud account, not
    something that heartbeats or accepts SSH.

    Filtering on api_key_id being unset instead of a platform-name
    allowlist is deliberate: every virtual device (Haikubox, Bird Buddy,
    and anything added later) is created with api_key_id=None (see
    haikubox_sync.py / bird_buddy_sync.py's _ensure_virtual_device — "no
    API key" is explicit in both), while every real paired Pi device gets
    a real one during pairing. This means a future third virtual source
    is excluded automatically, rather than requiring someone to remember
    to extend a platform list again — the exact mistake that let Bird
    Buddy slip through here.
    """
    from ..models import Device
    devices = (
        db.query(Device)
        .filter(Device.api_key_id.isnot(None))
        .order_by(Device.last_seen.desc())
        .all()
    )
    return [
        {
            "id":           d.id,
            "name":         d.name,
            "status":       d.status,
            "ip_address":   d.ip_address,
            "hostname":     d.hostname,
            "last_seen":    d.last_seen.isoformat() if d.last_seen else None,
            "managed_config": d.managed_config or {},
        }
        for d in devices
    ]


@router.get("/devices/{device_id}")
def get_device_log(
    device_id: str,
    lines: int = Query(200, ge=10, le=500),
    ssh_password: Optional[str] = None,
    ssh_user: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Fetch log lines from a device via SSH.
    If ssh_password/ssh_user are not supplied, falls back to values stored
    in the device's managed_config — this is genuinely where the Devices
    page's SSH username/password fields save to (ConfigEditor's ssh_user/
    ssh_password, part of the same config object pushed via
    PUT /{device_id}/managed-config), confirmed by tracing the actual
    save path start to finish. (Device.ssh_username/ssh_password are a
    separate pair of dedicated columns used by the SSH-key-setup and
    auto-discovery flows elsewhere in this file — not the same
    credentials as the ones set here.)"""
    from .devices import get_device_logs, Device
    if not ssh_password or not ssh_user:
        dev = db.query(Device).filter(Device.id == device_id).first()
        cfg = (dev.managed_config or {}) if dev else {}
        ssh_password = ssh_password or cfg.get("ssh_password") or None
        ssh_user     = ssh_user     or cfg.get("ssh_user")     or "pi"
    return get_device_logs(
        device_id=device_id,
        lines=lines,
        ssh_password=ssh_password,
        ssh_user=ssh_user or "pi",
        db=db,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_container_id() -> Optional[str]:
    """Return the current Docker container ID, or None if not in Docker."""
    cgroup = "/proc/1/cgroup"
    if not os.path.exists(cgroup):
        return None
    try:
        with open(cgroup) as f:
            for line in f:
                if "docker" in line or "containerd" in line:
                    # Last component is the container ID
                    parts = line.strip().split("/")
                    for p in reversed(parts):
                        if len(p) >= 12 and all(c in "0123456789abcdef" for c in p[:12]):
                            return p[:12]
    except Exception:
        pass
    # Try /etc/hostname which is set to container id in Docker
    hostname_file = "/etc/hostname"
    if os.path.exists(hostname_file):
        try:
            with open(hostname_file) as f:
                h = f.read().strip()
            if len(h) == 12 and all(c in "0123456789abcdef" for c in h):
                return h
        except Exception:
            pass
    return None
