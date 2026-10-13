"""
Chirp Server — Device Management API

Handles pairing, configuration, and heartbeats for Raspberry Pi recording devices.

Auth model:
  - Admin endpoints (list, update config, unpair): standard JWT (same as rest of API)
  - Device endpoints (pair, get config, heartbeat): X-API-Key header with device key
    These bypass JWT middleware so the Pi can authenticate without a browser session.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, WebSocket
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AppSettings, Device
from .auth import require_admin

logger = logging.getLogger("chirp.api.devices")
router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────────


def _config_version_now() -> int:
    """Timestamp-based config version: YYYYMMDDHHmm (UTC).
    Example: 2026-06-02 14:32 UTC → 202606021432"""
    from datetime import datetime as _dt
    return int(_dt.utcnow().strftime("%Y%m%d%H%M"))


def _extract_ipv4(ip: str) -> str:
    """Return a usable IPv4 address string, or '' if the input is bare IPv6.
    Handles: plain IPv4, IPv4-mapped IPv6 (::ffff:1.2.3.4), rejects bare IPv6."""
    if not ip:
        return ""
    # IPv4-mapped IPv6: "::ffff:192.168.1.1"
    if ip.lower().startswith("::ffff:"):
        candidate = ip[7:]
        if candidate.count(".") == 3:
            return candidate
    # Plain IPv4 (no colons)
    if ":" not in ip and ip.count(".") == 3:
        return ip
    # Bare IPv6 — not usable for SSH
    return ""




# Docker bridge and other infrastructure subnets that should never be stored
# as the device's reachable IP — they're internal to the host, not the Pi's real address.
_DOCKER_SUBNETS = [
    "172.17.",   # Docker default bridge (docker0)
    "172.18.",   # Docker networks
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
    "127.",      # loopback
]

def _is_docker_internal(ip: str) -> bool:
    """Return True if this IP is a Docker bridge / infrastructure address, not a real device IP."""
    return any(ip.startswith(prefix) for prefix in _DOCKER_SUBNETS)

def _validate_device_key(api_key: str, db: Session) -> dict:
    """Validate X-API-Key against stored device keys. Returns key entry or raises 401."""
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    keys = s.device_api_keys or [] if s else []
    for k in keys:
        if k.get("key") == api_key:
            return k
    raise HTTPException(status_code=401, detail="Invalid device API key")


def _device_key_from_header(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
) -> str:
    """Extract device key from X-API-Key or Bearer header."""
    if x_api_key:
        return x_api_key
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]
    raise HTTPException(status_code=401, detail="Missing X-API-Key header")


def _get_device_auth(device_id: str, db: Session, api_key: str) -> Device:
    """Validate key and return device, ensuring the key owns this device."""
    key_entry = _validate_device_key(api_key, db)
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.api_key_id != key_entry["id"]:
        raise HTTPException(status_code=403, detail="Key does not own this device")
    return device


# Stage 1 gate and input gain for a newly paired device. These match
# chirp-device/config.yaml. The old pushed values (-55 dB, 0 dB gain) sat
# about 36 dB above the device's own defaults and gated out distant,
# low-pitched night calls (owls) before BirdNET ever heard them.
DEVICE_ENERGY_FILTER_DEFAULTS = {"threshold_db": -90.0, "frequency_band_hz": [150, 12000]}
DEVICE_INPUT_GAIN_DB_DEFAULT = 6.0
DEVICE_DEFAULTS_REV = 3

# Per-device tuning that "sync all devices from settings" leaves alone:
# none of it comes from AppSettings, so re-pushing the pairing defaults
# would undo whatever was set on the Devices page (Coral backend, gate, gain).
_DEVICE_TUNING_KEYS = (("detection", "birdnet", "backend"), ("detection", "energy_filter"), ("audio",))


def _settings_derived_config(s: AppSettings) -> Dict[str, Any]:
    """The part of the default managed config that comes from AppSettings."""
    import copy
    cfg = copy.deepcopy(_default_managed_config(s))
    for path in _DEVICE_TUNING_KEYS:
        node = cfg
        for k in path[:-1]:
            node = node.get(k, {})
        node.pop(path[-1], None)
    cfg.pop("_defaults_rev", None)
    return cfg


def _upgrade_legacy_device_config(device: Device) -> bool:
    """One-time upgrade of a stored managed config still carrying the old
    pushed defaults. Only exact old default values change, so a gate or
    gain someone picked by hand stays. Returns True when it changed."""
    import copy
    cfg = copy.deepcopy(device.managed_config or {})
    if not cfg or int(cfg.get("_defaults_rev", 1) or 1) >= DEVICE_DEFAULTS_REV:
        return False
    ef = cfg.setdefault("detection", {}).setdefault("energy_filter", {})
    # Earlier pushed defaults: -55 (before rev 2), -85 (rev 2).
    if ef.get("threshold_db") in (None, -55, -55.0, -85, -85.0):
        ef["threshold_db"] = DEVICE_ENERGY_FILTER_DEFAULTS["threshold_db"]
    band = ef.get("frequency_band_hz")
    if not band or float(band[0]) > DEVICE_ENERGY_FILTER_DEFAULTS["frequency_band_hz"][0]:
        ef["frequency_band_hz"] = list(DEVICE_ENERGY_FILTER_DEFAULTS["frequency_band_hz"])
    audio = cfg.setdefault("audio", {})
    if audio.get("input_gain_db") in (None, 0, 0.0):
        audio["input_gain_db"] = DEVICE_INPUT_GAIN_DB_DEFAULT
    cfg["_defaults_rev"] = DEVICE_DEFAULTS_REV
    device.managed_config = cfg          # reassign so SQLAlchemy sees the JSON change
    logger.info("Upgraded legacy detection defaults on device %s (gate %s dB, gain %s dB)",
                device.name, ef["threshold_db"], audio["input_gain_db"])
    return True


def _default_managed_config(s: AppSettings) -> Dict[str, Any]:
    """Build a sensible default managed config from server's own settings."""
    return {
        "detection": {
            "birdnet": {
                "min_confidence": s.birdnet_min_confidence or 0.05,
                "overlap_seconds": s.birdnet_overlap or 2.5,
                "backend": "cpu",
                "sensitivity": float(s.birdnet_sensitivity or 1.0),
                "latitude": s.latitude,
                "longitude": s.longitude,
                "species_blacklist": ["Human_Human", "Noise_Noise", "Engine_Engine", "Power tools_Power tools"],
            },
            "energy_filter": dict(DEVICE_ENERGY_FILTER_DEFAULTS),
            "cooldown_seconds": s.recording_min_gap_seconds or 10.0,
            "bat_echolocation": {
                "enabled": bool(getattr(s, "bat_detection_enabled", False)),
                "device_name": getattr(s, "bat_detection_device_name", "") or "",
                "min_sample_rate": 192000,
                "events_dir": "~/chirp/bat_events",
                # These three were configurable in Settings but never
                # actually included in this payload — the device fell
                # back to its own hardcoded defaults regardless of what
                # was set in the UI.
                "min_swept_fraction": float(getattr(s, "bat_min_swept_fraction", 0.3) or 0.0),
                "max_pulse_rate_per_sec": float(getattr(s, "bat_max_pulse_rate", 600.0) or 600.0),
                "discard_likely_interference": bool(getattr(s, "bat_discard_likely_interference", False)),
            },
        },
        "recording": {
            "duration_seconds": float(s.recording_max_duration_sec or 30),
            "extend_on_activity": True,
            "extension_seconds": 10.0,
            "max_duration_seconds": float((s.recording_max_duration_sec or 30) * 4),
            "delete_after_upload": False,
            "max_disk_gb": 20.0,
            "auto_delete_days": 30,
            "max_per_hour": s.recording_max_per_hour or 0,
        },
        "audio": {
            "input_gain_db": DEVICE_INPUT_GAIN_DB_DEFAULT,
            "max_devices": 2,
        },
        "_defaults_rev": DEVICE_DEFAULTS_REV,
        "system": {
            "timezone": s.timezone or "America/New_York",
        },
        "logging": {
            "level": "INFO",
        },
    }


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class PairRequest(BaseModel):
    api_key: str
    name: Optional[str] = None
    hostname: Optional[str] = None
    platform: Optional[str] = None
    os_version: Optional[str] = None
    coral_present: bool = False
    coral_form_factor: Optional[str] = None   # "m2_pcie" | "usb" | ""
    coral_model_present: Optional[bool] = None  # compiled BirdNET EdgeTPU model on the device
    mic_count: int = 1
    mic_names: List[str] = []
    birdnet_backend: str = "cpu"
    device_version: Optional[str] = None


class HeartbeatRequest(BaseModel):
    status: str = "online"
    config_applied_version: int = 0
    mic_count: Optional[int] = None
    coral_present: Optional[bool] = None
    coral_form_factor: Optional[str] = None
    coral_model_present: Optional[bool] = None
    birdnet_backend: Optional[str] = None
    uptime_seconds: Optional[float] = None
    disk_free_gb: Optional[float] = None
    cpu_temp_c: Optional[float] = None
    recordings_queued: Optional[int] = None
    local_ip: Optional[str] = None   # LAN IP self-reported by the device
    tailscale_ip: Optional[str] = None   # Tailscale/Headscale IP self-reported by the device (see chirp-device's tailscale_manager.py)
    bat_status: Optional[Dict[str, Any]] = None  # from BatDetector.get_status(), see chirp-device


class ManagedConfigUpdate(BaseModel):
    config: Dict[str, Any]


class DeviceNameUpdate(BaseModel):
    name: str


class DeviceOut(BaseModel):
    id: str
    name: str
    api_key_id: Optional[str] = None     # nullable: virtual devices (e.g. Haikubox) have no real device API key
    bird_buddy_feeder_id: Optional[str] = None  # set only for Bird Buddy virtual devices — lets callers correlate against bird_buddy_selected_feeders
    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    tailscale_ip: Optional[str] = None   # Tailscale/Headscale IP self-reported by the device — was stored in the DB correctly all along, just never declared on this response model, so it never once reached the frontend.
    platform: Optional[str] = None
    os_version: Optional[str] = None
    coral_present: bool = False          # default: safe for NULL rows
    mic_count: int = 1                   # default: safe for NULL rows
    mic_names: List[str] = []            # default: safe for NULL rows
    birdnet_backend: str = "cpu"         # default: safe for NULL rows
    coral_form_factor: Optional[str] = None
    coral_model_present: Optional[bool] = None
    connect_via: Optional[str] = "auto"
    connect_address: Optional[str] = None   # address the server uses right now (see device_net.py)
    device_version: Optional[str] = None
    last_seen: Optional[datetime] = None
    status: str = "never_connected"
    managed_config: Dict[str, Any] = {}  # default: safe for NULL rows
    config_version: int = 0
    config_applied_version: int = 0
    created_at: Optional[datetime] = None  # nullable: old rows may lack this
    ssh_username: Optional[str] = None
    ssh_password_set: bool = False   # never the raw password — just whether one is saved
    last_recording_at: Optional[datetime] = None  # computed per-request, not a stored column

    class Config:
        from_attributes = True


# ── Device endpoints (X-API-Key auth) ─────────────────────────────────────────

@router.post("/pair", status_code=201)
def pair_device(body: PairRequest, request: Request, db: Session = Depends(get_db)):
    """
    Called by a Raspberry Pi to register itself with the server.
    Uses the device API key (not JWT). Safe to call repeatedly — idempotent.
    Returns device_id and initial managed config.
    """
    key_entry = _validate_device_key(body.api_key, db)

    # Check if a device already exists for this key
    device = db.query(Device).filter(Device.api_key_id == key_entry["id"]).first()

    # Get server settings for default config
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    _raw_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
    # Normalise the client IP to IPv4.
    # IPv6 literals look like "2600:4040:..." or "::ffff:192.168.1.1".
    # IPv4 with a port looks like "192.168.1.5:54321".
    _parts = (_raw_ip or "").split(":")
    if len(_parts) == 2 and _parts[0].count(".") == 3:
        # IPv4:port — strip the port
        _raw_ip = _parts[0]
    client_ip = _extract_ipv4(_raw_ip) or _raw_ip


    if device is None:
        # New pairing — create device with default managed config
        default_config = _default_managed_config(s) if s else {}
        device = Device(
            name=body.name or (body.hostname or "Chirp Device"),
            api_key_id=key_entry["id"],
            hostname=body.hostname,
            ip_address=client_ip,
            platform=body.platform,
            os_version=body.os_version,
            coral_present=body.coral_present,
            coral_form_factor=body.coral_form_factor or "",
            coral_model_present=body.coral_model_present,
            mic_count=body.mic_count,
            mic_names=body.mic_names,
            birdnet_backend=body.birdnet_backend,
            device_version=body.device_version,
            last_seen=datetime.utcnow(),
            status="online",
            managed_config=default_config,
            config_version=1,
        )
        db.add(device)
        db.commit()
        db.refresh(device)
        logger.info("New device paired: %s (%s) coral=%s backend=%s",
                    device.name, client_ip, body.coral_present, body.birdnet_backend)
    else:
        # Re-pairing — update hardware info, keep existing managed config
        device.hostname = body.hostname or device.hostname
        device.ip_address = client_ip
        device.platform = body.platform or device.platform
        device.os_version = body.os_version or device.os_version
        device.coral_present = body.coral_present
        device.coral_form_factor = body.coral_form_factor or device.coral_form_factor or ""
        if body.coral_model_present is not None:
            device.coral_model_present = body.coral_model_present
        device.mic_count = body.mic_count
        device.mic_names = body.mic_names
        device.birdnet_backend = body.birdnet_backend
        device.device_version = body.device_version or device.device_version
        device.last_seen = datetime.utcnow()
        device.status = "online"
        if body.name:
            device.name = body.name
        db.commit()
        db.refresh(device)
        logger.info("Device re-paired: %s (%s)", device.name, client_ip)

    return {
        "device_id": device.id,
        "name": device.name,
        "managed_config": with_night_rule(device.managed_config, s),
        "config_version": device.config_version,
        "server_location": {
            "latitude": s.latitude if s else None,
            "longitude": s.longitude if s else None,
            "timezone": s.timezone if s else "UTC",
        },
    }


@router.get("/{device_id}/config")
def get_device_config(
    device_id: str,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
):
    """
    Called by the Pi to poll for config updates.
    Returns managed_config and config_version so the Pi knows if it needs to re-apply.
    """
    raw_key = x_api_key or (authorization[7:] if authorization and authorization.startswith("Bearer ") else None)
    if not raw_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key")
    device = _get_device_auth(device_id, db, raw_key)
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    return {
        "managed_config": with_night_rule(device.managed_config, s),
        "config_version": device.config_version,
    }


def with_night_rule(cfg: Optional[dict], s) -> Optional[dict]:
    """The device's config plus the server's night-caller rule (Settings →
    Detection): night_species_min_confidence (min_confidence in "global"
    mode, so night callers need the same score as everything else) and
    night_global_species (night callers set to the global threshold in
    "per_species" mode; device 1.3.3+)."""
    if not cfg or s is None:
        return cfg
    import copy
    from ..services.birdnet_pass import NIGHT_SPECIES_MIN_CONF, night_rules
    rules = night_rules(s)
    out = copy.deepcopy(cfg)
    bn = out.setdefault("detection", {}).setdefault("birdnet", {})
    min_conf = float(bn.get("min_confidence") or s.birdnet_min_confidence or 0.05)
    # A night floor set on the device's own config (Devices page) wins over
    # the default, e.g. 0.20 so faint night noise doesn't start recordings.
    own = bn.get("night_species_min_confidence")
    night = float(own) if own not in (None, "") else NIGHT_SPECIES_MIN_CONF
    bn["night_species_min_confidence"] = min_conf if rules["mode"] == "global" else night
    bn["night_global_species"] = sorted(k for k, v in rules["per_species"].items() if not v) \
        if rules["mode"] == "per_species" else []
    return out


@router.post("/{device_id}/heartbeat")
def device_heartbeat(
    device_id: str,
    body: HeartbeatRequest,
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
):
    """
    Pi sends a heartbeat every 30–60 seconds to report it's alive.
    Server responds with whether a config update is available.
    """
    raw_key = x_api_key or (authorization[7:] if authorization and authorization.startswith("Bearer ") else None)
    if not raw_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key")
    device = _get_device_auth(device_id, db, raw_key)

    if _upgrade_legacy_device_config(device):
        device.config_version = _config_version_now()

    device.last_seen = datetime.utcnow()
    device.status = "online"
    device.config_applied_version = body.config_applied_version
    if body.mic_count is not None:
        device.mic_count = body.mic_count
    if body.coral_present is not None:
        device.coral_present = body.coral_present
    if body.coral_form_factor is not None:
        device.coral_form_factor = body.coral_form_factor
    if body.coral_model_present is not None:
        device.coral_model_present = body.coral_model_present
    if body.birdnet_backend is not None:
        device.birdnet_backend = body.birdnet_backend
    if body.bat_status is not None:
        device.bat_status = body.bat_status

    # Determine the best IP to store for this device.
    #
    # Priority (highest first):
    #   1. body.local_ip   — the Pi reports its own LAN IP (most reliable when
    #                         traffic passes through Cloudflare/NAT, where XFF
    #                         contains the public WAN IP, not the LAN address)
    #   2. X-Forwarded-For — useful for direct LAN deployments without a proxy
    #   3. request.client  — raw socket IP (usually Docker bridge or NAT)
    #
    # Never store Docker-internal (172.16-31.x.x) or public IPs when we already
    # have a good private LAN address stored.
    import ipaddress as _ipmod

    def _is_private_lan(ip: str) -> bool:
        """True if ip is a real private LAN address (not Docker bridge, not public)."""
        if not ip or _is_docker_internal(ip):
            return False
        try:
            a = _ipmod.ip_address(ip)
            return a.is_private and not a.is_loopback and not a.is_link_local
        except ValueError:
            return False

    _best_ip: Optional[str] = None

    # Tier 1: self-reported LAN IP from the Pi
    if body.local_ip:
        _v4 = _extract_ipv4(body.local_ip.strip())
        if _v4 and _is_private_lan(_v4):
            _best_ip = _v4

    # Tier 2: X-Forwarded-For (only useful on direct LAN deployments)
    if not _best_ip:
        for _candidate in [c.strip() for c in request.headers.get("X-Forwarded-For", "").split(",") if c.strip()]:
            _v4 = _extract_ipv4(_candidate.split(":")[0] if _candidate.count(":") == 1 else _candidate)
            if _v4 and _is_private_lan(_v4):
                _best_ip = _v4
                break

    # Tier 3: raw socket address
    if not _best_ip and request.client:
        _rc = request.client.host or ""
        _v4 = _extract_ipv4(_rc.split(":")[0] if _rc.count(":") == 1 else _rc)
        if _v4 and _is_private_lan(_v4):
            _best_ip = _v4

    if _best_ip:
        if device.ip_address != _best_ip:
            logger.info("Device %s IP updated: %s → %s", device.id[:8], device.ip_address, _best_ip)
        device.ip_address = _best_ip
    elif device.ip_address and _is_private_lan(device.ip_address):
        pass   # Keep existing good LAN address — don't overwrite with public/Docker IP

    # Tailscale/Headscale IP — self-reported only, no "which tier wins"
    # logic needed (there's exactly one source), and deliberately NOT
    # run through _is_private_lan() above: Tailscale addresses live in
    # the CGNAT range (100.64.0.0/10), not a standard LAN range, and
    # the entire point of this address is that it's reachable ACROSS
    # networks, not confined to one — a "is this a local LAN address"
    # check would be actively wrong here, not just unnecessary.
    if body.tailscale_ip:
        _ts_v4 = _extract_ipv4(body.tailscale_ip.strip())
        if _ts_v4 and _ts_v4 != device.tailscale_ip:
            logger.info("Device %s Tailscale IP updated: %s → %s", device.id[:8], device.tailscale_ip, _ts_v4)
        if _ts_v4:
            device.tailscale_ip = _ts_v4

    db.commit()

    config_update_available = device.config_version != body.config_applied_version
    return {
        "ok": True,
        "config_update_available": config_update_available,
        "config_version": device.config_version,
    }




# ── SSH Terminal (WebSocket) ───────────────────────────────────────────────────

def _ws_auth_error(websocket, db) -> Optional[str]:
    """Why a WebSocket may not open an SSH/diagnostic session, or None.
    Browsers can't set headers on a WebSocket, so the JWT arrives as
    ?token=. Admins only when auth is on (matches require_admin)."""
    from .auth import verify_token
    from ..models import AppSettings as _AS, User as _User
    token = websocket.query_params.get("token", "")
    payload = verify_token(token) if token else None
    user = db.query(_User).filter(_User.username == payload.get("sub")).first() if payload else None
    if user and user.active:
        return None if user.role == "admin" else "Admin access required"
    s = db.query(_AS).filter(_AS.id == 1).first()
    from ..config import settings as _cfg
    auth_on = bool(s.auth_enabled) if (s and s.auth_enabled is not None) else _cfg.auth_enabled
    return "Not signed in — reload the page and sign in again" if auth_on else None


@router.websocket("/{device_id}/ssh")
async def device_ssh_terminal(
    websocket: WebSocket,
    device_id: str,
    db: Session = Depends(get_db),
):
    """
    WebSocket-based SSH terminal bridging the browser to the Pi.

    Protocol (text frames, UTF-8):
      Client → Server  {"type": "auth", "via": "local"|"tailscale", ...}  (see below)
      Client → Server  {"type": "input",  "data": "..."}   keyboard input
      Client → Server  {"type": "resize", "cols": N, "rows": N}
      Server → Client  {"type": "output", "data": "..."}   terminal output
      Server → Client  {"type": "error",  "data": "..."}   connection errors
      Server → Client  {"type": "closed"}                  SSH session ended
    """
    import asyncio
    import json
    import threading
    import paramiko

    await websocket.accept()

    auth_err = _ws_auth_error(websocket, db)
    if auth_err:
        await websocket.send_text(json.dumps({"type": "error", "data": auth_err}))
        await websocket.close()
        return

    # Read credentials from first message
    try:
        first = await asyncio.wait_for(websocket.receive_text(), timeout=15.0)
        creds = json.loads(first)
        if creds.get("type") != "auth":
            await websocket.send_text(json.dumps({"type": "error", "data": "Expected auth message first"}))
            await websocket.close()
            return
        password  = creds.get("password", "")
        username  = creds.get("username", "pi")
        ssh_port  = int(creds.get("port", 22))
        # Which of the device's two reported addresses to connect through
        # — defaults to "local" (the original, only behavior before
        # Tailscale support existed), so an older frontend build that
        # never sends this field keeps working unchanged.
        via = creds.get("via", "auto")
    except Exception as e:
        await websocket.send_text(json.dumps({"type": "error", "data": f"Auth timeout or parse error: {e}"}))
        await websocket.close()
        return

    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        await websocket.send_text(json.dumps({"type": "error", "data": "Device not found"}))
        await websocket.close()
        return

    from ..services import device_net
    targets = device_net.candidates(device, via)
    if not targets:
        msg = ("Device has no Tailscale IP yet — confirm Tailscale is installed and connected on the device, and wait for its next heartbeat."
               if via == "tailscale" else "Device IP unknown — wait for a heartbeat")
        await websocket.send_text(json.dumps({"type": "error", "data": msg}))
        await websocket.close()
        return
    ip = targets[0]

    # Open SSH connection in a thread (paramiko is synchronous)
    loop = asyncio.get_event_loop()
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    channel = None

    try:
        def _connect(host):
            ssh_client.connect(
                host, port=ssh_port, username=username, password=password,
                timeout=10, allow_agent=False, look_for_keys=False,
                sock=device_net.paramiko_sock(host, ssh_port),
            )
        # Try the preferred address, then the other one (auto mode). A
        # wrong password stops immediately; a network failure moves on.
        for i, ip in enumerate(targets):
            try:
                await websocket.send_text(json.dumps({"type": "output", "data": f"\r\nConnecting to {username}@{ip}:{ssh_port} ({device_net.via_label(ip)})…\r\n"}))
            except Exception:
                return  # client already disconnected
            try:
                await loop.run_in_executor(None, _connect, ip)
                break
            except paramiko.AuthenticationException:
                raise
            except Exception as e:
                if i == len(targets) - 1:
                    raise
                try:
                    await websocket.send_text(json.dumps({"type": "output", "data": f"\r\n{device_net.via_label(ip)} failed ({e}); trying {device_net.via_label(targets[i + 1])}…\r\n"}))
                except Exception:
                    return

    except paramiko.AuthenticationException:
        try:
            await websocket.send_text(json.dumps({"type": "error", "data": "Authentication failed — check username/password"}))
            await websocket.close()
        except Exception:
            pass
        return
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"type": "error", "data": f"SSH connection failed: {e}"}))
            await websocket.close()
        except Exception:
            pass
        return

    # Request interactive shell with a pty
    channel = ssh_client.invoke_shell(term="xterm-256color", width=220, height=50)
    channel.settimeout(0.05)

    # Save ssh_username if different
    if device.ssh_username != username:
        device.ssh_username = username
        db.commit()

    # Bridge output: SSH → WebSocket (runs in executor thread)
    send_queue: asyncio.Queue = asyncio.Queue(maxsize=256)

    def _read_ssh():
        """Read from SSH channel and put chunks into the async send queue."""
        try:
            while not channel.closed:
                try:
                    data = channel.recv(4096)
                    if not data:
                        break
                    text = data.decode("utf-8", errors="replace")
                    loop.call_soon_threadsafe(send_queue.put_nowait, text)
                except Exception:
                    break
        finally:
            loop.call_soon_threadsafe(send_queue.put_nowait, None)  # sentinel

    reader_thread = threading.Thread(target=_read_ssh, daemon=True)
    reader_thread.start()

    try:
        async def _flush_output():
            """Forward SSH output to WebSocket."""
            while True:
                chunk = await send_queue.get()
                if chunk is None:
                    break
                try:
                    await websocket.send_text(json.dumps({"type": "output", "data": chunk}))
                except Exception:
                    break

        flush_task = asyncio.create_task(_flush_output())

        while True:
            try:
                msg_text = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
            except asyncio.TimeoutError:
                # Send keepalive
                if not channel.closed:
                    continue
                break
            except Exception:
                break

            try:
                msg = json.loads(msg_text)
            except Exception:
                continue

            if msg.get("type") == "input":
                data = msg.get("data", "")
                if data and not channel.closed:
                    await loop.run_in_executor(None, channel.sendall, data.encode("utf-8", errors="replace"))

            elif msg.get("type") == "resize":
                cols = int(msg.get("cols", 80))
                rows = int(msg.get("rows", 24))
                if not channel.closed:
                    await loop.run_in_executor(None, channel.resize_pty, cols, rows)

        flush_task.cancel()

    except Exception as e:
        logger.debug("SSH WebSocket session error: %s", e)
    finally:
        try:
            channel.close()
        except Exception:
            pass
        try:
            ssh_client.close()
        except Exception:
            pass
        try:
            await websocket.send_text(json.dumps({"type": "closed"}))
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass


@router.put("/{device_id}/ssh-credentials")
def update_ssh_credentials(
    device_id: str,
    body: dict,
    admin: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Save SSH username and/or password for a device — admin-only. Partial
    update: only fields actually present in the body are changed, so the
    frontend can save just a username without touching an already-saved
    password (or vice versa).

    Password storage follows the exact same pattern as every other secret
    in this app (see smtp_password in app_settings.py): stored plaintext —
    there's no encryption-at-rest layer anywhere in this codebase to be
    consistent with — and skipped if the incoming value looks like the
    masked placeholder this same endpoint's sibling GET would have returned
    (contains "*"), so re-saving the form after a fetch doesn't clobber the
    real stored password with the masked display value.
    """
    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")

    if "username" in body:
        d.ssh_username = (body.get("username") or "").strip() or None
    if "password" in body:
        pw = body.get("password")
        if pw and "*" not in pw:
            d.ssh_password = pw
        elif pw == "":
            d.ssh_password = None  # explicit clear

    db.commit()
    return {
        "ok": True,
        "ssh_username": d.ssh_username,
        "ssh_password_set": bool(d.ssh_password),
    }


@router.put("/{device_id}/ssh-username")
def update_ssh_username(
    device_id: str,
    body: dict,
    admin: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Deprecated alias for update_ssh_credentials — kept for backward
    compatibility with anything still calling this specific route. Also now
    admin-gated (it previously was not, a real pre-existing gap this fix
    closes for both routes at once rather than leaving one fixed and one not)."""
    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    username = (body.get("username") or "pi").strip()
    d.ssh_username = username
    db.commit()
    return {"ok": True, "ssh_username": d.ssh_username}

# ── Admin endpoints (JWT auth, handled by middleware) ─────────────────────────


@router.get("/{device_id}/config-status")
def get_config_status(device_id: str, db: Session = Depends(get_db)):
    """
    Return whether the device's applied config matches the server's current config.
    Uses config_version / config_applied_version from heartbeat data.
    """
    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")

    in_sync = (d.config_version == d.config_applied_version)
    pending = not in_sync

    return {
        "device_id": d.id,
        "device_name": d.name,
        "server_version": d.config_version,
        "device_applied_version": d.config_applied_version,
        "in_sync": in_sync,
        "pending_update": pending,
        "last_seen": d.last_seen.isoformat() if d.last_seen else None,
        "status": d.status,
        "managed_config": d.managed_config,
        "note": (
            "Device has not yet applied the latest config — it will pick it up on the next heartbeat poll."
            if pending else
            "Device config is current."
        ),
    }


@router.get("/{device_id}/logs")
def get_device_logs(
    device_id: str,
    lines: int = 200,
    ssh_password: Optional[str] = None,
    ssh_user: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Fetch recent log lines from a device via SSH (journalctl -u chirp-device).
    Returns lines as a list of strings, newest last.
    Requires SSH access to the device (same credentials used for push-credentials).
    Falls back to the device's last heartbeat error if SSH unavailable.
    """
    import subprocess

    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    from ..services import device_net
    if not device_net.device_address(d):
        raise HTTPException(status_code=400, detail="Device IP unknown — it must have heartbeated at least once")

    # Real fix: this endpoint is called from two places — this route
    # directly (the Devices page's log icon, via api.devices.logs) and
    # logs.py's /logs/devices/{id} wrapper (the Logs page), which resolves
    # credentials from managed_config itself before calling this function.
    # Called directly, as the Devices page icon does, neither ssh_password
    # nor ssh_user get supplied at all — and this function's own fallback
    # only ever checked d.ssh_username (a separate dedicated column no
    # working UI actually populates) for the username, with no fallback
    # at all for the password. So the Devices page icon always attempted
    # a passwordless connection regardless of what was actually saved via
    # the Devices page's own SSH Username/Password fields (which save to
    # managed_config, not those dedicated columns) — a real, reproducible
    # "Permission denied (publickey,password)" every time, confirmed by
    # testing the exact same stored managed_config credentials manually
    # via sshpass, which connects immediately.
    cfg = d.managed_config or {}
    ssh_password = ssh_password or cfg.get("ssh_password") or None
    ssh_user = ssh_user or cfg.get("ssh_user") or d.ssh_username or "pi"

    stored_ip = device_net.device_address(d) or ""
    ipv4 = _extract_ipv4(stored_ip)
    is_ipv6 = ":" in stored_ip and not ipv4   # bare IPv6, not IPv4-mapped

    # Decide which address / flags to use
    if ipv4:
        target = ipv4
        addr_flags = ["-4"]
    elif is_ipv6:
        # Bare IPv6 literal — pass as-is to ssh, force IPv6 with -6.
        # Brackets are only needed in [host]:port syntax; without a port, use the raw address.
        target = stored_ip
        addr_flags = ["-6"]
    elif d.hostname:
        # Mangled/unknown IP — fall back to hostname if available
        target = d.hostname
        addr_flags = []
    else:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot reach device — stored address '{stored_ip}' is not usable. "
                "Restart the chirp-device service on the Pi to send a fresh heartbeat."
            )
        )

    lines = max(10, min(lines, 500))

    # Build SSH command — use sshpass for password auth, key auth otherwise
    ssh_base = [
        "ssh",
        *addr_flags,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=8",
        "-o", "BatchMode=no",   # allow password prompts via sshpass
        "-o", "PasswordAuthentication=" + ("yes" if ssh_password else "no"),
        *device_net.ssh_opts(target),
        f"{ssh_user}@{target}",
    ]
    if ssh_password:
        ssh_cmd = ["sshpass", "-p", ssh_password] + ssh_base
    else:
        ssh_cmd = ssh_base

    ssh_cmd_with_remote = ssh_cmd + [
        f"journalctl -u chirp-device -n {lines} --no-pager 2>/dev/null "
        f"|| journalctl -u chirp -n {lines} --no-pager 2>/dev/null "
        f"|| tail -n {lines} ~/chirp-device/logs/birdwatch.log 2>/dev/null "
        f"|| tail -n {lines} ~/chirp/logs/chirp.log 2>/dev/null "
        f"|| echo 'No log file found'",
    ]

    try:
        result = subprocess.run(
            ssh_cmd_with_remote,
            capture_output=True, text=True, timeout=10
        )
        log_text = result.stdout or result.stderr or "No output"
        log_lines = [l for l in log_text.splitlines() if l.strip()]
        return {
            "device_id": d.id,
            "device_name": d.name,
            "ip": target,
            "lines": log_lines[-lines:],
            "source": "ssh",
            "ok": True,
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail=f"SSH connection to {target} timed out — check the device is online and reachable.")
    except FileNotFoundError:
        raise HTTPException(
            status_code=501,
            detail="SSH client not installed in server container. Rebuild the Docker image — openssh-client is now included in the Dockerfile."
        )
    except Exception as e:
        msg = str(e)
        if "Permission denied" in msg or "publickey" in msg:
            raise HTTPException(
                status_code=403,
                detail=f"SSH authentication failed ({target}). The server container needs an SSH key trusted by the Pi. "
                       f"Use 'Push Credentials' first to establish trust, or check ~/.ssh/known_hosts."
            )
        raise HTTPException(status_code=500, detail=f"SSH error: {e}")


@router.put("/{device_id}/connect-via", response_model=DeviceOut)
def set_connect_via(device_id: str, body: dict, db: Session = Depends(get_db)):
    """How the server reaches this device: auto | lan | tailscale."""
    from ..services.device_net import VALID_VIA
    via = (body.get("connect_via") or "").strip().lower()
    if via not in VALID_VIA:
        raise HTTPException(status_code=400, detail=f"connect_via must be one of {', '.join(VALID_VIA)}")
    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    d.connect_via = via
    db.commit()
    db.refresh(d)
    logger.info("Device %s connect via %s → %s", d.name, via, d.connect_address)
    return d


@router.put("/{device_id}/ip")
def set_device_ip(device_id: str, body: dict, db: Session = Depends(get_db)):
    """Manually set the IPv4 address for a device. Used when Docker NAT prevents
    automatic IPv4 detection from the heartbeat source address."""
    import re as _re
    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    ip = (body.get("ip_address") or "").strip()
    if not ip:
        raise HTTPException(status_code=400, detail="ip_address is required")
    # Accept plain IPv4 only
    if not _re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip):
        raise HTTPException(status_code=400, detail=f"'{ip}' is not a valid IPv4 address")
    d.ip_address = ip
    db.commit()
    logger.info("Device %s IP manually set to %s", d.name, ip)
    return {"ok": True, "device_id": d.id, "ip_address": d.ip_address}


@router.post("/{device_id}/setup-ssh-key")
def setup_ssh_key(device_id: str, body: dict, db: Session = Depends(get_db)):
    """
    Generate an SSH keypair on the server (if not already present) and install
    the public key on the Pi using ssh-copy-id with the provided password.
    After this, log fetching and push-credentials work without a password.
    """
    import subprocess, os

    ssh_password = body.get("ssh_password")
    ssh_user     = body.get("ssh_user", "pi")
    if not ssh_password:
        raise HTTPException(status_code=400, detail="ssh_password required")

    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")

    from ..services import device_net
    stored_ip = device_net.device_address(d) or ""
    target = _extract_ipv4(stored_ip) or (stored_ip if ":" not in stored_ip else None) or d.hostname
    if not target:
        raise HTTPException(status_code=400, detail="Device IP unknown — heartbeat required first")

    # Key path inside the container (persists as long as container is running;
    # for true persistence mount a volume at /root/.ssh or /home/chirp/.ssh)
    key_path = os.path.expanduser("~/.ssh/id_ed25519_chirp")
    pub_path  = key_path + ".pub"

    # Generate key if not present
    if not os.path.exists(key_path):
        os.makedirs(os.path.expanduser("~/.ssh"), mode=0o700, exist_ok=True)
        r = subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", key_path, "-N", "", "-C", "chirp-server"],
            capture_output=True, text=True
        )
        if r.returncode != 0:
            raise HTTPException(status_code=500, detail=f"ssh-keygen failed: {r.stderr}")

    # Copy public key to Pi using sshpass + ssh-copy-id
    copy_cmd = [
        "sshpass", "-p", ssh_password,
        "ssh-copy-id",
        "-i", pub_path,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        *device_net.ssh_opts(target),
        f"{ssh_user}@{target}",
    ]
    result = subprocess.run(copy_cmd, capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        err = result.stderr or result.stdout or "Unknown error"
        raise HTTPException(status_code=403,
            detail=f"Could not install SSH key on {target}: {err.strip()}")

    return {
        "ok": True,
        "message": f"SSH key installed on {target}. Log fetching will now work without a password.",
        "key": open(pub_path).read().strip(),
    }

@router.get("", response_model=List[DeviceOut])
def list_devices(db: Session = Depends(get_db)):
    """List all paired devices. Updates status based on last_seen."""
    from ..models import AppSettings as _HB_AS
    _hb_s = db.query(_HB_AS).filter(_HB_AS.id == 1).first()
    _haikubox_on = bool(getattr(_hb_s, "haikubox_enabled", False)) if _hb_s else False

    devices = db.query(Device).order_by(Device.created_at.desc()).all()
    if not _haikubox_on:
        # Hard-hide the virtual Haikubox device entirely when disabled —
        # same "as if it never existed" treatment as the recordings list,
        # rather than showing a device card for a feature that's been
        # turned off. Real devices (platform != "Haikubox") are unaffected.
        devices = [d for d in devices if d.platform != "Haikubox" and d.birdnet_backend != "haikubox"]

    # Compute online/offline from last_seen before returning
    changed = False
    for d in devices:
        expected = "online" if d.is_online() else ("offline" if d.last_seen else "never_connected")
        if d.status != expected:
            d.status = expected
            changed = True
    if changed:
        db.commit()

    if devices:
        from ..models import Recording
        from sqlalchemy import func
        rows = (
            db.query(Recording.device_id, func.max(Recording.trigger_timestamp))
            .filter(Recording.device_id.in_([d.id for d in devices]))
            .group_by(Recording.device_id)
            .all()
        )
        last_rec_map = {device_id: ts for device_id, ts in rows}
        for d in devices:
            d.last_recording_at = last_rec_map.get(d.id)

    return devices



# ── Pi auto-discovery ─────────────────────────────────────────────────────────

class DiscoverResult(BaseModel):
    ip: str
    hostname: Optional[str] = None
    port: int = 22
    reachable: bool = True
    chirp_device: bool = False   # True if chirp-device service is running
    ssh_available: bool = False

@router.post("/sync-all-from-settings", status_code=200)
def sync_all_devices_from_settings(db: Session = Depends(get_db)):
    """
    Re-generate and push the default managed config (built from current AppSettings)
    to ALL paired devices. Increments config_version on each device so they pick up
    the update on their next heartbeat/poll.

    Called automatically when the server saves settings that affect recording behaviour
    (recording_min_gap_seconds, recording_max_duration_sec, recording_max_per_hour,
    location, BirdNET parameters).
    """
    devices = db.query(Device).all()
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if not s:
        raise HTTPException(status_code=404, detail="Server settings not initialized")

    default_cfg = _settings_derived_config(s)
    pushed = []
    for d in devices:
        # Fresh settings-derived defaults win over whatever's already stored —
        # swapped argument order from the original (default_cfg, existing)
        # to (existing, default_cfg). _deep_merge_dicts always lets its
        # SECOND argument win on conflict, so this makes default_cfg win for
        # every key it actually defines, while any genuinely custom keys a
        # device carries (set via PUT /{device_id}/managed-config, a real,
        # separate per-device override mechanism) survive untouched, since
        # they only exist in the base dict and default_cfg never mentions
        # them. Getting this backwards meant "sync ALL devices FROM
        # settings" could only ever push a brand-new field once — any field
        # already present (including one set by a PREVIOUS run of this same
        # function) was permanently frozen from then on, silently defeating
        # every subsequent call.
        merged = _deep_merge_dicts(d.managed_config or {}, default_cfg)
        d.managed_config = merged
        d.config_version = _config_version_now()
        pushed.append(d.name)

    db.commit()
    logger.info("Synced settings to %d device(s): %s", len(pushed), pushed)
    return {"ok": True, "devices_updated": len(pushed), "names": pushed}


def _deep_merge_dicts(base: dict, override: dict) -> dict:
    """Recursively merge override onto base. Override wins on conflict."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge_dicts(result[key], val)
        else:
            result[key] = val
    return result

@router.get("/discover", response_model=List[DiscoverResult])
def discover_devices(timeout: float = 8.0, db: Session = Depends(get_db)):
    """
    Scan the local network for Raspberry Pi devices running chirp-device.
    Uses three strategies in order:
     1. mDNS/Avahi: looks for _chirp._tcp services announced by chirp-device
     2. mDNS hostname patterns: *.local hostnames common to Pis
     3. ARP table: parse /proc/net/arp for known Raspberry Pi MAC prefixes
    Returns all discovered candidates within `timeout` seconds.
    """
    import socket, subprocess, concurrent.futures

    found: List[DiscoverResult] = []
    seen_ips: set = set()

    # ── Strategy 1: mDNS service discovery via avahi-browse ──────────────────
    try:
        out = subprocess.check_output(
            ["avahi-browse", "-t", "-r", "-p", "_chirp._tcp"],
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        ).decode(errors="replace")
        for line in out.splitlines():
            if line.startswith("="):
                parts = line.split(";")
                # avahi-browse -p format: =;iface;IPv4;name;_chirp._tcp;local;hostname;ip;port;txt
                if len(parts) >= 9:
                    hostname = parts[6].rstrip(".")
                    ip = parts[7]
                    port_str = parts[8]
                    if ip and ip not in seen_ips:
                        seen_ips.add(ip)
                        found.append(DiscoverResult(
                            ip=ip, hostname=hostname,
                            port=int(port_str) if port_str.isdigit() else 22,
                            chirp_device=True, ssh_available=True
                        ))
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass  # avahi not available or no service found

    # ── Strategy 2: ARP table scan for Raspberry Pi MAC prefixes ─────────────
    # Includes all known OUI prefixes for Raspberry Pi Foundation boards 1–5
    RPI_MAC_PREFIXES = {
        # Raspberry Pi 1, 2, 3 (BCM2835/2836/2837 — Raspberry Pi Foundation)
        "b8:27:eb",
        # Raspberry Pi 3B+, 4 (BCM2837B0 / BCM2711 — Raspberry Pi Trading)
        "dc:a6:32",
        # Raspberry Pi 4 (second batch)
        "e4:5f:01",
        # Raspberry Pi Zero 2W
        "28:cd:c1",
        # Raspberry Pi 5 (BCM2712 — new OUI ranges)
        "d8:3a:dd",
        "2c:cf:67",
        "e4:5f:01",
        # Raspberry Pi Compute Modules
        "b8:27:eb",
        # Additional ranges seen in the wild for Pi 5
        "d8:3a:dd",
        "48:b0:2d",
        "2e:cf:67",
        "d8:3a:dd",
    }
    # Normalise to a frozen set of 8-char lowercase prefixes
    RPI_MAC_PREFIXES = frozenset(p.lower()[:8] for p in RPI_MAC_PREFIXES)

    try:
        with open("/proc/net/arp") as f:
            lines = f.read().splitlines()[1:]  # skip header
        for line in lines:
            parts = line.split()
            if len(parts) < 4:
                continue
            ip, _hw, flags, mac = parts[0], parts[1], parts[2], parts[3]
            if flags == "0x0":  # incomplete — not yet resolved
                continue
            prefix = mac.lower()[:8]
            if prefix in RPI_MAC_PREFIXES and ip not in seen_ips:
                seen_ips.add(ip)
                try:
                    hostname = socket.gethostbyaddr(ip)[0]
                except Exception:
                    hostname = None
                found.append(DiscoverResult(ip=ip, hostname=hostname))
    except Exception as _arp_err:
        logger.debug("ARP scan failed: %s", _arp_err)

    # ── Strategy 3: Ping-sweep the local subnet to populate the ARP cache ─────
    # This is needed when the container's ARP table is empty (e.g. Docker bridge).
    # We detect the local subnet from the host's default interface, then ping
    # all hosts in parallel to fill the ARP cache, then re-read /proc/net/arp.
    if not found:
        try:
            # Get the local subnet from ip route or hostname -I
            _local_ips = []
            try:
                _out = subprocess.check_output(
                    ["hostname", "-I"], stderr=subprocess.DEVNULL, timeout=2
                ).decode().split()
                _local_ips = [ip for ip in _out if "." in ip and not ip.startswith("172.")]
            except Exception:
                pass

            for _local_ip in _local_ips[:2]:
                # Compute /24 subnet
                _parts = _local_ip.rsplit(".", 1)
                if len(_parts) != 2:
                    continue
                _subnet = _parts[0]  # e.g. "192.168.1"

                logger.info("Discovery: ping-sweeping %s.0/24...", _subnet)
                # Fire pings in parallel to populate ARP cache (don't wait for all)
                _pings = [
                    subprocess.Popen(
                        ["ping", "-c1", "-W1", "-q", f"{_subnet}.{i}"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    for i in range(1, 255)
                ]
                # Wait up to timeout-1 seconds for pings to finish
                import time as _time
                _deadline = _time.monotonic() + max(1.0, timeout - 1.5)
                for p in _pings:
                    remaining = _deadline - _time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        p.wait(timeout=min(1.0, remaining))
                    except Exception:
                        p.kill()

                # Re-read ARP table after pings
                try:
                    with open("/proc/net/arp") as f:
                        lines = f.read().splitlines()[1:]
                    for line in lines:
                        parts = line.split()
                        if len(parts) < 4:
                            continue
                        ip, _hw, flags, mac = parts[0], parts[1], parts[2], parts[3]
                        if flags == "0x0":
                            continue
                        prefix = mac.lower()[:8]
                        if prefix in RPI_MAC_PREFIXES and ip not in seen_ips:
                            seen_ips.add(ip)
                            try:
                                hostname = socket.gethostbyaddr(ip)[0]
                            except Exception:
                                hostname = None
                            found.append(DiscoverResult(ip=ip, hostname=hostname))
                            logger.info("Discovery (post-ping): found Pi at %s (%s)", ip, mac)
                except Exception:
                    pass

        except Exception as _ping_err:
            logger.debug("Ping-sweep failed: %s", _ping_err)

    # ── Strategy 4: hostname resolution for common Pi hostnames ───────────────
    PI_HOSTNAMES = [
        "raspberrypi.local", "chirppi.local", "chirp.local",
        "birdwatch.local", "chirp-device.local",
    ]
    for _h in PI_HOSTNAMES:
        try:
            _ip = socket.gethostbyname(_h)
            if _ip not in seen_ips:
                seen_ips.add(_ip)
                found.append(DiscoverResult(ip=_ip, hostname=_h))
                logger.info("Discovery (mDNS hostname): found %s at %s", _h, _ip)
        except Exception:
            pass

    # ── Strategy 5: Check if found devices have chirp-device API responding ──
    def check_chirp(device: DiscoverResult) -> DiscoverResult:  # noqa
        if device.chirp_device:
            return device
        import httpx as _hx
        for port in (8765, 8766, 80):
            try:
                r = _hx.get(f"http://{device.ip}:{port}/api/v1/health",
                            timeout=1.5)
                if r.status_code == 200 and "chirp" in r.text.lower():
                    device.chirp_device = True
                    break
            except Exception:
                pass
        # Check SSH port 22
        try:
            s = socket.socket()
            s.settimeout(1.0)
            s.connect((device.ip, 22))
            banner = s.recv(64).decode(errors="ignore")
            s.close()
            device.ssh_available = "SSH" in banner
        except Exception:
            pass
        return device

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        found = list(ex.map(check_chirp, found))

    logger.info("Discovery found %d candidate Pi devices", len(found))
    return found


class PushCredentialsRequest(BaseModel):
    ip: str
    ssh_port: int = 22
    ssh_user: str = "pi"
    ssh_password: Optional[str] = None
    ssh_key_path: Optional[str] = None
    key_name: str = "Auto-discovered Pi"
    server_url: str   # The URL the Pi should use to reach this server


@router.post("/push-credentials", status_code=200)
def push_credentials(body: PushCredentialsRequest, db: Session = Depends(get_db)):
    """
    Generate a device API key and write it to the Pi's config.yaml via SSH.
    The Pi does NOT need to be manually configured — this handles it end-to-end.
    Returns the generated key (show once to user for reference).

    Requirements on the Pi: SSH enabled, chirp-device installed at /opt/chirp-device/
    or ~/chirp-device/.
    """
    import subprocess

    # 1. Generate a new device API key in DB
    from ..models import AppSettings as _AS
    import secrets as _secrets
    s = db.query(_AS).filter(_AS.id == 1).first()
    if not s:
        raise HTTPException(status_code=500, detail="Server settings not initialized")

    new_key = _secrets.token_urlsafe(32)
    key_entry = {"id": str(__import__("uuid").uuid4()), "name": body.key_name, "key": new_key}
    existing_keys = list(s.device_api_keys or [])
    existing_keys.append(key_entry)
    s.device_api_keys = existing_keys
    db.commit()

    # 2. Write config via SSH

    config_paths = [
        "/opt/chirp-device/config.yaml",
        "~/chirp-device/config.yaml",
        "~/chirp/config.yaml",
        "~/chirp-device/config.yaml",
    ]

    ssh_cmd_base = [
        "ssh",
        "-4",                              # force IPv4 — Docker containers lack IPv6 routing
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        "-p", str(body.ssh_port),
    ]
    if body.ssh_key_path:
        ssh_cmd_base += ["-i", body.ssh_key_path]

    target = f"{body.ssh_user}@{body.ip}"

    # Find config file on Pi
    find_cmd = ssh_cmd_base + [target,
        "for p in " + " ".join(config_paths) + "; do [ -f $p ] && echo $p && break; done"
    ]

    config_path = None
    try:
        if body.ssh_password:
            # Use sshpass for password auth
            find_cmd = ["sshpass", "-p", body.ssh_password] + find_cmd
        result = subprocess.run(find_cmd, capture_output=True, text=True, timeout=15)
        config_path = result.stdout.strip()
    except Exception as e:
        logger.warning("SSH find config error for %s: %s", body.ip, e)

    if not config_path:
        # Try to create it at the default location
        config_path = "~/chirp-device/config.yaml"

    # Write config safely via base64-encoded payload — no interpolation into shell strings
    import base64 as _b64, json as _json
    payload = _json.dumps({
        "path": config_path,
        "server_url": body.server_url,
        "api_key": new_key,
        "device_name": body.key_name,
    })
    b64_payload = _b64.b64encode(payload.encode()).decode()
    safe_script = (
        "import base64, json, yaml, os; "
        f"d = json.loads(base64.b64decode('{b64_payload}').decode()); "
        "p = d['path']; "
        "cfg = yaml.safe_load(open(p)) if os.path.exists(p) else {}; "
        "cfg.setdefault('server_sync', {}).update({"
        "'enabled': True, "
        "'server_url': d['server_url'], "
        "'api_key': d['api_key'], "
        "'device_name': d['device_name']}); "
        "os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True); "
        "yaml.dump(cfg, open(p, 'w'))"
    )
    write_cmd = ssh_cmd_base + [target, "python3 -c " + safe_script]
    if body.ssh_password:
        write_cmd = ["sshpass", "-p", body.ssh_password] + [
            c for c in write_cmd if c not in ["sshpass", "-p", body.ssh_password]
        ]

    try:
        result = subprocess.run(write_cmd, capture_output=True, text=True, timeout=20)
        if result.returncode != 0:
            logger.warning("SSH write config failed for %s: %s", body.ip, result.stderr[:200])
            # Return key anyway so user can manually configure
            return {
                "ok": False,
                "key": new_key,
                "key_id": key_entry["id"],
                "error": f"SSH write failed: {result.stderr[:200]}. Key generated — add manually.",
                "config_path": config_path,
            }
        # Restart chirp-device service on Pi
        restart_cmd = ssh_cmd_base + [target,
            "sudo systemctl restart chirp-device 2>/dev/null || "
            "sudo supervisorctl restart chirp-device 2>/dev/null || "
            "echo 'Service restart not available — restart manually'"
        ]
        if body.ssh_password:
            restart_cmd = ["sshpass", "-p", body.ssh_password] + [c for c in restart_cmd if c not in ["sshpass", "-p", body.ssh_password]]
        subprocess.run(restart_cmd, capture_output=True, text=True, timeout=15)
        logger.info("Credentials pushed to Pi at %s, config: %s", body.ip, config_path)
        return {
            "ok": True,
            "key": new_key,
            "key_id": key_entry["id"],
            "config_path": config_path,
            "message": "Credentials written and service restarted. Pi will pair within 60s.",
        }
    except Exception as e:
        logger.error("SSH push failed for %s: %s", body.ip, e)
        return {
            "ok": False,
            "key": new_key,
            "key_id": key_entry["id"],
            "error": str(e),
        }



@router.get("/{device_id}/config-profile")
def export_config_profile(device_id: str, db: Session = Depends(get_db)):
    """
    Export the current managed config for a device as a downloadable YAML profile.
    The profile can be re-imported later to restore settings after code updates.
    """
    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    import yaml
    from datetime import datetime as _dt
    from fastapi.responses import Response
    profile = {
        "chirp_config_profile": True,
        "device_name": d.name,
        "exported_at": _dt.utcnow().isoformat() + "Z",
        "config": d.managed_config or {},
    }
    yaml_str = yaml.dump(profile, default_flow_style=False, allow_unicode=True)
    safe_name = d.name.replace(" ", "_").lower()
    return Response(
        content=yaml_str,
        media_type="application/x-yaml",
        headers={"Content-Disposition": f'attachment; filename="chirp-profile-{safe_name}.yaml"'},
    )


@router.post("/{device_id}/config-profile")
def import_config_profile(
    device_id: str,
    body: dict,
    db: Session = Depends(get_db),
):
    """
    Import a previously-exported config profile for a device.
    Body: { "config": {...} } or a full profile dict with a 'chirp_config_profile' key.
    Increments config_version so the device picks up the new settings.
    """
    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")

    cfg = body.get("config", body)
    # If it's a full profile export, extract the config key
    if "chirp_config_profile" in cfg:
        cfg = cfg.get("config", {})

    d.managed_config = cfg
    d.config_version = _config_version_now()
    db.commit()
    return {"status": "imported", "config_version": d.config_version}


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(device_id: str, db: Session = Depends(get_db)):
    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    d.status = "online" if d.is_online() else ("offline" if d.last_seen else "never_connected")
    db.commit()
    return d


@router.patch("/{device_id}", response_model=DeviceOut)
def update_device(device_id: str, body: DeviceNameUpdate, db: Session = Depends(get_db)):
    """Rename a device."""
    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    d.name = body.name
    db.commit()
    db.refresh(d)
    return d


@router.put("/{device_id}/managed-config", response_model=DeviceOut)
def push_managed_config(device_id: str, body: ManagedConfigUpdate, db: Session = Depends(get_db)):
    """
    Push a new managed config to the device.
    Increments config_version — the Pi will pick this up on its next poll/heartbeat.
    """
    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    d.managed_config = body.config
    d.config_version = _config_version_now()
    db.commit()
    db.refresh(d)
    logger.info("Config pushed to device %s (version %d)", d.name, d.config_version)
    return d


@router.post("/{device_id}/sync-location", response_model=DeviceOut)
def sync_location_to_device(device_id: str, db: Session = Depends(get_db)):
    """
    Copy the server's configured lat/lon/timezone into this device's managed config.
    Increments config_version so the Pi applies it on next poll.
    """
    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if not s:
        raise HTTPException(status_code=404, detail="Server settings not configured")
    if not s.latitude or not s.longitude:
        raise HTTPException(status_code=400, detail="Server location not set — configure it in Settings first")

    cfg = dict(d.managed_config or {})
    cfg.setdefault("detection", {}).setdefault("birdnet", {})
    cfg["detection"]["birdnet"]["latitude"] = s.latitude
    cfg["detection"]["birdnet"]["longitude"] = s.longitude
    cfg.setdefault("system", {})["timezone"] = s.timezone or "UTC"

    d.managed_config = cfg
    d.config_version = _config_version_now()
    db.commit()
    db.refresh(d)
    logger.info("Location synced to device %s: lat=%.4f lon=%.4f tz=%s",
                d.name, s.latitude, s.longitude, s.timezone)
    return d


@router.post("/{device_id}/dismiss-pending-config", response_model=DeviceOut)
def dismiss_pending_config(device_id: str, db: Session = Depends(get_db)):
    """
    Marks this device's currently-pending config as already applied,
    without touching managed_config or actually sending anything to the
    device — requested directly, as a safety valve for a config_version
    bump that turns out not to reflect any real change the device
    actually needs (config_version is timestamp-based, so ANY code path
    that touches it — Sync Location, a Settings save with a
    device-affecting field changed — looks "new" relative to whatever
    the device last reported, whether or not the device's own config
    genuinely needs to change).

    Important limit on what this actually does: config_applied_version
    is reported BY THE DEVICE on every heartbeat, not tracked
    independently by the server — this only overrides that field until
    the device's own next heartbeat arrives and reports its real value
    again. If the device genuinely hasn't applied the pending change
    yet, dismissing here doesn't make that true — it comes back
    "Pending" again on the device's very next heartbeat. Safe (and
    useful) for a false-positive pending state; not a way to skip a
    real one.
    """
    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    d.config_applied_version = d.config_version
    db.commit()
    db.refresh(d)
    logger.info("Dismissed pending config for device %s (marked v%d as applied)", d.name, d.config_version)
    return d


@router.delete("/{device_id}", status_code=204)
def unpair_device(device_id: str, db: Session = Depends(get_db)):
    """
    Remove a device pairing. The Pi will need to re-pair with a NEW key
    afterward — its old key is genuinely revoked here, not just its
    Device row deleted.

    This used to only delete the Device row, leaving the corresponding
    entry in AppSettings.device_api_keys untouched. Since pair_device()
    looks up an existing Device by matching Device.api_key_id against
    that same key list (not by device_id), a Pi that still had its old,
    never-actually-revoked key cached locally would silently recreate a
    brand-new Device row on its very next pairing attempt (a scheduled
    heartbeat retry, a reboot, etc.) — completely undoing the unpair
    action without the person who clicked "Unpair" ever finding out.
    Removing the matching device_api_keys entry here is what actually
    revokes the credential, so a stale Pi can no longer re-pair with it
    at all — it needs a genuinely new key issued through the normal
    pairing flow.
    """
    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")

    # Virtual devices (Haikubox, Bird Buddy) represent an external
    # service, not a real Pi with its own issued key — api_key_id is
    # None for these (see the column's own comment in models.py), so
    # there's nothing to revoke in device_api_keys for them.
    if d.api_key_id:
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        if s and s.device_api_keys:
            remaining_keys = [k for k in s.device_api_keys if k.get("id") != d.api_key_id]
            if len(remaining_keys) != len(s.device_api_keys):
                s.device_api_keys = remaining_keys
                logger.info("Revoked API key %s for unpaired device %s", d.api_key_id, device_id)

    db.delete(d)
    db.commit()
    logger.info("Device unpaired: %s", device_id)



