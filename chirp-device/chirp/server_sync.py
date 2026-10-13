"""
Chirp Device — Server Sync

Handles all communication with the Chirp server:
  - Auto-pairing on startup using the configured API key
  - Periodic heartbeat (every 30s) so the server knows the device is alive
  - Config polling: if the server pushes a new managed config, apply it at runtime
    without requiring a process restart

Config layering:
  local config.yaml  (base)
  └── server managed_config (deep-merged on top, wins on conflict)

The merged result is what BirdWatcher actually uses. Only the detection,
recording, audio, system, and logging sections are managed; upload.server_url
and upload.api_key are always taken from local config.yaml.
"""

import logging
import os
import platform
import socket
import ipaddress
import subprocess
import threading
import time
from typing import Dict, List, Optional, Tuple

from . import __version__ as _CHIRP_VERSION

logger = logging.getLogger(__name__)


# ── Merge helpers ──────────────────────────────────────────────────────────────

def deep_merge(base: Dict, override: Dict) -> Dict:
    """Recursively merge override onto base. Override wins on conflict."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _get_platform_info() -> str:
    """Return a human-readable platform string."""
    try:
        with open("/proc/device-tree/model", "r") as f:
            return f.read().strip().replace("\x00", "")
    except Exception:
        return platform.machine() or "Unknown"


def _get_os_version() -> str:
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return platform.version()


def _coral_model_present() -> bool:
    """True when a compiled BirdNET EdgeTPU model (TFLite header) is installed."""
    try:
        from .birdnet_coral import EDGETPU_MODEL_PATH
        with open(EDGETPU_MODEL_PATH, "rb") as f:
            return f.read(8)[4:8] == b"TFL3"
    except Exception:
        return False


def _detect_coral() -> Tuple[bool, str]:
    """
    Detect Coral Edge TPU presence and form factor.

    Returns (present: bool, form_factor: str).
    form_factor is one of: "m2_pcie", "usb", "unknown"

    Supported hardware:
      - Coral M.2 Accelerator B+M (NVMe-style PCIe connector, gasket-dkms driver)
      - Coral M.2 Accelerator A+E  (standard M.2 PCIe, gasket-dkms driver)
      - Coral PCIe Accelerator     (PCIe x1 card, gasket-dkms driver)
      - Coral USB Accelerator      (USB 3.0, libedgetpu)

    All PCIe variants (M.2 B+M, M.2 A+E, PCIe card) expose /dev/apex_0 via
    the gasket-dkms kernel driver. The M.2 B+M uses an NVMe-style connector
    but carries PCIe signals — it is NOT an NVMe storage device.
    """
    import os

    # ── PCIe/M.2 variants: gasket-dkms creates /dev/apex_N ─────────────────
    for n in range(4):
        if os.path.exists(f"/dev/apex_{n}"):
            # Determine if it's M.2 by checking lspci for Global Unichip
            form = "m2_pcie"
            try:
                out = subprocess.check_output(
                    ["lspci", "-v"], stderr=subprocess.DEVNULL, timeout=3
                ).decode(errors="replace")
                if "Global Unichip" in out or "Coral" in out:
                    # Check if it's on an M.2 slot (reported as PCIe but on M.2)
                    # lspci doesn't distinguish M.2 vs PCIe card by default;
                    # presence of /dev/apex_0 on a Pi 5 is almost certainly M.2
                    form = "m2_pcie"
            except Exception:
                pass
            logger.info("Coral Edge TPU detected (PCIe/M.2): /dev/apex_%d [%s]", n, form)
            return True, form

    # ── USB variant: libedgetpu ──────────────────────────────────────────────
    try:
        out = subprocess.check_output(
            ["lsusb"], stderr=subprocess.DEVNULL, timeout=3
        ).decode(errors="replace")
        # Known Coral USB Accelerator vendor:product IDs
        if "1a6e:089a" in out or "18d1:9302" in out:
            logger.info("Coral Edge TPU detected (USB)")
            return True, "usb"
        # Also check by name
        if "Global Unichip" in out or "Coral" in out:
            logger.info("Coral Edge TPU detected (USB, name match)")
            return True, "usb"
    except Exception:
        pass

    # ── pycoral fallback ─────────────────────────────────────────────────────
    try:
        from pycoral.utils.edgetpu import list_edge_tpus
        tpus = list_edge_tpus()
        if tpus:
            form = "usb" if any("usb" in str(t).lower() for t in tpus) else "m2_pcie"
            logger.info("Coral Edge TPU detected via pycoral: %s", tpus)
            return True, form
    except ImportError:
        pass
    except Exception as e:
        logger.debug("pycoral detection error: %s", e)

    return False, ""


def _get_mic_info(config: Dict) -> Tuple[int, List[str]]:
    """Return (count, names) of detected USB mics matching config hints."""
    try:
        import sounddevice as sd
        hints = config.get("audio", {}).get("device_name_hints", ["USB", "Microphone"])
        names = []
        for d in sd.query_devices():
            if d["max_input_channels"] > 0:
                if any(h.lower() in d["name"].lower() for h in hints):
                    names.append(d["name"])
        return (len(names) or 1), names
    except Exception:
        return 1, []



EFFECTIVE_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state", "effective_config.json")


def _save_effective_config(merged: Dict) -> None:
    """config.yaml with the server's pushed settings applied, for
    tools/check-file.py (the running service keeps it only in memory).
    Credentials are left out."""
    try:
        import copy
        import json as _json
        snap = copy.deepcopy(merged)
        sync = snap.get("server_sync") or {}
        for t in [sync] + list(sync.get("targets") or []):
            if isinstance(t, dict):
                t.pop("api_key", None)
        os.makedirs(os.path.dirname(EFFECTIVE_CONFIG_PATH), exist_ok=True)
        tmp = EFFECTIVE_CONFIG_PATH + ".tmp"
        with open(tmp, "w") as f:
            _json.dump(snap, f, indent=1, default=str)
        os.replace(tmp, EFFECTIVE_CONFIG_PATH)
    except Exception as e:
        logger.debug("Could not save effective config: %s", e)

# ── ServerSync class ───────────────────────────────────────────────────────────

def _get_local_lan_ip() -> str:
    """
    Return this device's LAN IP address — the address reachable from other
    devices on the same network.

    Connects a UDP socket to 8.8.8.8 (no data sent) so the OS picks the
    outbound interface, then reads the local address.  Much more reliable
    than parsing ifconfig/ip output and always returns the right interface
    when the Pi has both eth0 and wlan0.
    """
    for target in ("8.8.8.8", "1.1.1.1", "192.168.1.1"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((target, 80))
            ip = s.getsockname()[0]
            s.close()
            # Validate it looks like a private LAN address
            try:
                addr = ipaddress.ip_address(ip)
                if addr.is_private and not addr.is_loopback and not addr.is_link_local:
                    return ip
            except ValueError:
                pass
        except Exception:
            pass
    return ""


class _SecondarySyncTarget:
    """
    A server_sync target beyond the first — pairs and sends heartbeats
    so that server's own Devices page shows this device as paired and
    online, same as the primary. Deliberately does NOT fetch or apply
    managed config: main.py wires ServerSync's own _apply_config (and
    _on_config_update, _bat_status_getter) with monkey-patching specific
    to ITS pairing lifecycle (OLED display, mDNS discovery state) — a
    second target trying to also drive those would mean two servers
    racing to decide the device's actual running configuration, with no
    principled way to pick a winner. One authoritative source of
    applied config (the primary target, unchanged from before this
    class existed) is simpler and safer than resolving that conflict.

    Investigated and added directly after a real report: recordings
    were uploading successfully to a second chirp-server-type upload
    target (see uploader.py's own matching fix), but that server's own
    Devices page never showed the device at all, and its heartbeat/
    online status could never work either — server_sync only ever
    knew about ONE server, with no concept of additional targets, and
    was never updated when multi-target uploading was added.
    """

    HEARTBEAT_INTERVAL = 30
    PAIR_RETRY_INTERVAL = 60

    def __init__(self, target_cfg: Dict, shared: "ServerSync"):
        self.name: str = target_cfg.get("name", target_cfg.get("server_url", "secondary"))
        self.enabled: bool = target_cfg.get("enabled", True)
        self.server_url: str = target_cfg.get("server_url", "").rstrip("/")
        self.api_key: str = target_cfg.get("api_key", "")
        self.device_name: str = target_cfg.get("device_name", shared.device_name)
        self._shared = shared  # read-only hardware info (platform, coral, mic_count, etc.) — device-wide facts true regardless of which server is asking
        self._device_id: Optional[str] = None
        self._paired: bool = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if not self.enabled:
            return
        if (not self.server_url or not self.api_key
                or "PLACEHOLDER" in self.server_url or "PLACEHOLDER" in self.api_key):
            logger.warning("server_sync target '%s' disabled: still has a PLACEHOLDER value in config.yaml", self.name)
            return
        self._thread = threading.Thread(target=self._run, name=f"ServerSync-{self.name}", daemon=True)
        self._thread.start()
        logger.info("ServerSync target '%s' started → %s", self.name, self.server_url)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)

    def _run(self) -> None:
        while not self._stop_event.is_set() and not self._paired:
            if self._pair():
                break
            logger.warning("[%s] Pairing failed — retrying in %ds", self.name, self.PAIR_RETRY_INTERVAL)
            self._stop_event.wait(self.PAIR_RETRY_INTERVAL)

        if not self._paired:
            return

        while not self._stop_event.is_set():
            self._heartbeat()
            self._stop_event.wait(self.HEARTBEAT_INTERVAL)

    def _pair(self) -> bool:
        try:
            import requests
            try:
                import certifi as _c; import os as _o; _ca = _c.where()
                _verify = _ca if _o.path.exists(_ca) else "/etc/ssl/certs/ca-certificates.crt"
            except Exception:
                _verify = "/etc/ssl/certs/ca-certificates.crt"
            payload = {
                "api_key": self.api_key,
                "name": self.device_name,
                "hostname": socket.gethostname(),
                "platform": self._shared._platform,
                "os_version": self._shared._os_version,
                "coral_present": self._shared._coral,
                "coral_form_factor": self._shared._coral_form,
                "coral_model_present": self._shared._coral_model,
                "mic_count": self._shared._mic_count,
                "mic_names": self._shared._mic_names,
                "birdnet_backend": self._shared._effective_backend(),
                "device_version": ServerSync.VERSION,
            }
            resp = requests.post(f"{self.server_url}/api/v1/devices/pair", json=payload, timeout=15, verify=_verify)
            if resp.status_code in (200, 201):
                self._device_id = resp.json()["device_id"]
                self._paired = True
                logger.info("[%s] Paired successfully, device_id=%s", self.name, self._device_id)
                return True
            logger.error("[%s] Pairing failed HTTP %d: %s", self.name, resp.status_code, resp.text[:200])
            return False
        except Exception as e:
            logger.warning("[%s] Pairing error: %s", self.name, e)
            return False

    def _heartbeat(self) -> None:
        try:
            import requests
            try:
                import certifi as _c; import os as _o; _ca = _c.where()
                _verify = _ca if _o.path.exists(_ca) else "/etc/ssl/certs/ca-certificates.crt"
            except Exception:
                _verify = "/etc/ssl/certs/ca-certificates.crt"
            local_ip = _get_local_lan_ip()
            payload = {
                "status": "online",
                "config_applied_version": 0,   # this target never applies config — see class docstring
                "mic_count": self._shared._mic_count,
                "coral_present": self._shared._coral,
                "coral_form_factor": self._shared._coral_form,
                "coral_model_present": self._shared._coral_model,
                "birdnet_backend": self._shared._effective_backend(),
            }
            if local_ip:
                payload["local_ip"] = local_ip
            _ts_mgr = getattr(self._shared, "_tailscale_manager", None)
            if _ts_mgr is not None:
                _ts_ip = _ts_mgr.get_ip()
                if _ts_ip:
                    payload["tailscale_ip"] = _ts_ip
            requests.post(
                f"{self.server_url}/api/v1/devices/{self._device_id}/heartbeat",
                json=payload, headers={"X-API-Key": self.api_key}, timeout=10, verify=_verify,
            )
        except Exception as e:
            logger.debug("[%s] Heartbeat error: %s", self.name, e)


class ServerSync:
    """
    Runs as a background thread. Pairs with the server on startup,
    sends heartbeats, and hot-applies managed config updates.

    Supports multiple targets (server_sync.targets: — same shape as
    upload.targets), matching a real gap found directly: without this,
    only ever one server could see this device as paired/online at
    all, regardless of how many upload targets were configured. The
    FIRST target is the one this class itself represents — everything
    below this docstring is completely unchanged from before targets:
    existed, since main.py reaches directly into several of this
    class's own private attributes and even replaces _apply_config
    with a wrapped version (OLED display, mDNS discovery state) —
    changing what those refer to would break that integration. Any
    additional targets are handled by separate _SecondarySyncTarget
    instances instead (see that class's own docstring for why they
    deliberately never apply config), created and started alongside
    this one in start()/stop() below.
    """

    HEARTBEAT_INTERVAL = 30      # seconds between heartbeats
    CONFIG_POLL_INTERVAL = 60    # seconds between explicit config polls (on top of heartbeat)
    PAIR_RETRY_INTERVAL = 60     # seconds to wait before retrying a failed pairing
    VERSION = _CHIRP_VERSION     # chirp-device version reported to server — real single source of truth (see chirp/__init__.py), not a separately hardcoded string that can drift out of sync

    def __init__(self, config: Dict, on_config_update=None, bat_status_getter=None):
        """
        :param config: Full merged config dict from config.yaml
        :param on_config_update: Optional callback(new_merged_config) called when
                                 the server pushes a new managed config.
        """
        sync_cfg = config.get("server_sync", {})
        target_configs = sync_cfg.get("targets")
        if target_configs:
            primary_cfg = target_configs[0]
            self._secondary_target_configs = target_configs[1:]
        else:
            # Legacy format: no targets: list — this IS the one and only
            # target, exactly as before this feature existed.
            primary_cfg = sync_cfg
            self._secondary_target_configs = []

        self.enabled: bool = primary_cfg.get("enabled", sync_cfg.get("enabled", False))
        self.server_url: str = primary_cfg.get("server_url", "").rstrip("/")
        self.api_key: str = primary_cfg.get("api_key", "")
        self.device_name: str = primary_cfg.get("device_name", socket.gethostname())

        self._base_config = config
        self._managed_config: Dict = {}
        self._applied_version: int = 0
        self._server_config_version: int = 0

        self._device_id: Optional[str] = None
        self._paired: bool = False

        self._on_config_update = on_config_update
        # Called fresh at each heartbeat, not captured once at construction
        # time — the actual BatDetector instance gets replaced whenever its
        # config changes (see watcher.py), so a lambda reading through to
        # whatever the CURRENT instance is avoids reporting stale state
        # after that kind of swap.
        self._bat_status_getter = bat_status_getter
        self._active_backend_getter = None   # set by main.py; returns "coral" | "cpu" | None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Hardware info (gathered once at startup)
        self._platform = _get_platform_info()
        self._os_version = _get_os_version()
        self._coral, self._coral_form = _detect_coral()
        self._coral_model = _coral_model_present()
        self._mic_count, self._mic_names = _get_mic_info(config)
        self._backend = config.get("detection", {}).get("birdnet", {}).get("backend", "cpu")

        # Coral present but config says cpu: only worth suggesting when a
        # compiled BirdNET EdgeTPU model exists (none is published upstream).
        if self._coral and self._backend == "cpu" and self._coral_model:
            logger.info(
                "Coral TPU detected (%s) but backend=cpu in config. "
                "Consider setting backend: coral in config.yaml or via server managed config.",
                self._coral_form,
            )

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        # Secondary targets are independent of whether the primary is
        # enabled — each is separately gated by its own enabled flag,
        # same as upload.targets already works. Started first, before
        # any of the primary's own early returns below, so a disabled
        # primary doesn't also silently disable every secondary.
        self._secondary_targets: List[_SecondarySyncTarget] = [
            _SecondarySyncTarget(tc, self) for tc in self._secondary_target_configs
        ]
        for t in self._secondary_targets:
            t.start()

        if not self.enabled:
            logger.warning(
                "ServerSync is DISABLED — config push from server will NOT work. "
                "Set server_sync.enabled: true and server_url/api_key in config.yaml "
                "to enable remote config management and device pairing."
            )
            return
        if (not self.server_url or not self.api_key
                or "PLACEHOLDER" in self.server_url
                or "PLACEHOLDER" in self.api_key):
            logger.warning(
                "ServerSync: server_url or api_key not configured (placeholder values detected) — "
                "edit config.yaml to enable server sync"
            )
            return

        self._thread = threading.Thread(target=self._run, name="ServerSync", daemon=True)
        self._thread.start()
        logger.info("ServerSync started → %s", self.server_url)

    def stop(self) -> None:
        for t in getattr(self, "_secondary_targets", []):
            t.stop()
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)

    def is_paired(self) -> bool:
        return self._paired and self._device_id is not None

    def get_merged_config(self) -> Dict:
        """Return base config deep-merged with latest server managed config."""
        with self._lock:
            if not self._managed_config:
                return self._base_config
            return deep_merge(self._base_config, self._managed_config)

    # ── Background thread ──────────────────────────────────────────────────────

    def _run(self) -> None:
        while not self._stop_event.is_set() and not self._paired:
            if self._pair():
                break
            logger.warning("Pairing failed — retrying in %ds", self.PAIR_RETRY_INTERVAL)
            self._stop_event.wait(self.PAIR_RETRY_INTERVAL)

        if not self._paired:
            return

        last_heartbeat = 0.0
        last_config_poll = 0.0

        while not self._stop_event.is_set():
            now = time.monotonic()

            if now - last_heartbeat >= self.HEARTBEAT_INTERVAL:
                config_update_available = self._heartbeat()
                last_heartbeat = time.monotonic()
                if config_update_available:
                    self._fetch_and_apply_config()
                    last_config_poll = time.monotonic()

            if now - last_config_poll >= self.CONFIG_POLL_INTERVAL:
                self._fetch_and_apply_config()
                last_config_poll = time.monotonic()

            self._stop_event.wait(5)

    # ── Pairing ────────────────────────────────────────────────────────────────

    def _pair(self) -> bool:
        try:
            import requests
            # Resolve CA bundle (certifi cacert.pem can go missing after Python upgrades)
            try:
                import certifi as _c; import os as _o; _ca = _c.where()
                _verify = _ca if _o.path.exists(_ca) else "/etc/ssl/certs/ca-certificates.crt"
            except Exception:
                _verify = "/etc/ssl/certs/ca-certificates.crt"
            payload = {
                "api_key": self.api_key,
                "name": self.device_name,
                "hostname": socket.gethostname(),
                "platform": self._platform,
                "os_version": self._os_version,
                "coral_present": self._coral,
                "coral_form_factor": self._coral_form,   # NEW: "m2_pcie" | "usb" | ""
                "coral_model_present": self._coral_model,
                "mic_count": self._mic_count,
                "mic_names": self._mic_names,
                "birdnet_backend": self._backend,
                "device_version": self.VERSION,
            }
            resp = requests.post(
                f"{self.server_url}/api/v1/devices/pair",
                json=payload,
                timeout=15,
                verify=_verify,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                self._device_id = data["device_id"]
                managed = data.get("managed_config", {})
                self._server_config_version = data.get("config_version", 1)

                with self._lock:
                    self._managed_config = managed
                    self._applied_version = 0

                self._paired = True
                logger.info(
                    "Paired with server: device_id=%s name=%s coral=%s(%s)",
                    self._device_id, data.get("name"),
                    self._coral, self._coral_form,
                )

                if managed:
                    self._apply_config(self._server_config_version)

                return True
            else:
                logger.error("Pairing failed HTTP %d: %s", resp.status_code, resp.text[:200])
                return False
        except Exception as e:
            logger.warning("Pairing error: %s", e)
            return False

    # ── Heartbeat ──────────────────────────────────────────────────────────────

    def _effective_backend(self) -> str:
        """Backend BirdNET is running on; falls back to the configured value
        until the pipeline exists."""
        getter = getattr(self, "_active_backend_getter", None)
        if getter:
            try:
                active = getter()
                if active:
                    mismatch = (self._backend, active) if active != self._backend else None
                    if mismatch and mismatch != getattr(self, "_backend_mismatch_logged", None):
                        logger.warning("BirdNET configured for %s but running on %s", *mismatch)
                    self._backend_mismatch_logged = mismatch
                    return active
            except Exception:
                pass
        return self._backend

    def _heartbeat(self) -> bool:
        """Send heartbeat. Returns True if server has a new config for us."""
        try:
            import requests
            # Resolve CA bundle (certifi cacert.pem can go missing after Python upgrades)
            try:
                import certifi as _c; import os as _o; _ca = _c.where()
                _verify = _ca if _o.path.exists(_ca) else "/etc/ssl/certs/ca-certificates.crt"
            except Exception:
                _verify = "/etc/ssl/certs/ca-certificates.crt"
            local_ip = _get_local_lan_ip()
            payload = {
                "status": "online",
                "config_applied_version": self._applied_version,
                "mic_count": self._mic_count,
                "coral_present": self._coral,
                "coral_form_factor": self._coral_form,
                "coral_model_present": self._coral_model,
                "birdnet_backend": self._effective_backend(),
            }
            if local_ip:
                payload["local_ip"] = local_ip
            _ts_mgr = getattr(self, "_tailscale_manager", None)
            if _ts_mgr is not None:
                _ts_ip = _ts_mgr.get_ip()
                if _ts_ip:
                    payload["tailscale_ip"] = _ts_ip
            try:
                import shutil
                free = shutil.disk_usage(
                    self._base_config.get("recording", {}).get("output_dir", "/")
                ).free / (1024 ** 3)
                payload["disk_free_gb"] = round(free, 2)
            except Exception:
                pass
            try:
                with open("/sys/class/thermal/thermal_zone0/temp") as f:
                    payload["cpu_temp_c"] = round(int(f.read().strip()) / 1000, 1)
            except Exception:
                pass
            if self._bat_status_getter:
                try:
                    bat_status = self._bat_status_getter()
                    if bat_status:
                        payload["bat_status"] = bat_status
                except Exception:
                    pass

            resp = requests.post(
                f"{self.server_url}/api/v1/devices/{self._device_id}/heartbeat",
                json=payload,
                headers={"X-API-Key": self.api_key},
                timeout=10,
                verify=_verify,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("config_update_available", False)
            else:
                logger.debug("Heartbeat HTTP %d", resp.status_code)
                return False
        except Exception as e:
            logger.debug("Heartbeat error: %s", e)
            return False

    # ── Config fetch + apply ───────────────────────────────────────────────────

    def _fetch_and_apply_config(self) -> None:
        try:
            import requests
            # Resolve CA bundle (certifi cacert.pem can go missing after Python upgrades)
            try:
                import certifi as _c; import os as _o; _ca = _c.where()
                _verify = _ca if _o.path.exists(_ca) else "/etc/ssl/certs/ca-certificates.crt"
            except Exception:
                _verify = "/etc/ssl/certs/ca-certificates.crt"
            resp = requests.get(
                f"{self.server_url}/api/v1/devices/{self._device_id}/config",
                headers={"X-API-Key": self.api_key},
                timeout=10,
                verify=_verify,
            )
            if resp.status_code == 200:
                data = resp.json()
                new_version = data.get("config_version", 0)
                managed = data.get("managed_config", {})

                if new_version != self._applied_version:
                    logger.info(
                        "Config update available: server v%d, applied v%d — fetching...",
                        new_version, self._applied_version,
                    )
                    with self._lock:
                        self._managed_config = managed
                        self._server_config_version = new_version
                    self._apply_config(new_version)
            else:
                # Reported directly: "Config pending" kept reappearing on
                # the server after being dismissed — that dismiss only
                # updates the SERVER's own bookkeeping and is explicit
                # about not surviving a real still-pending state (see its
                # own confirmation dialog), so the real question is why
                # the device wasn't actually catching up on its own. This
                # was logged at debug — invisible without verbose logging
                # — so a persistent fetch failure here (network hiccup,
                # auth issue, server-side error) could silently prevent
                # every poll from ever applying the new config, forever,
                # with nothing in the normal logs to show why. Promoted
                # to warning so a real recurring failure is visible
                # instead of looking identical to "just hasn't polled
                # yet."
                logger.warning("Config poll HTTP %d — config_applied_version will stay stale until this succeeds", resp.status_code)
        except Exception as e:
            logger.warning("Config poll error (will retry on next cycle): %s", e)

    def _apply_config(self, version: int) -> None:
        """Merge managed config onto base and call the update callback."""
        merged = self.get_merged_config()

        # Update local backend tracker from merged config
        new_backend = merged.get("detection", {}).get("birdnet", {}).get("backend", "cpu")
        if new_backend != self._backend:
            logger.info(
                "Backend changed by server config: %s → %s",
                self._backend, new_backend,
            )
            self._backend = new_backend

        det = merged.get("detection", {})
        bn  = det.get("birdnet", {})
        rec = merged.get("recording", {})

        # Reported directly: this line used to log unconditionally, BEFORE
        # the callback below ever ran — so a real callback failure still
        # printed "✅ Applied" immediately followed by an ERROR for the
        # exact same version, which reads as a contradiction and made a
        # genuine, self-healing retry (fails at startup before BirdWatcher
        # exists, succeeds moments later) look like a stuck loop instead.
        # Moved inside the try below, after _applied_version is actually
        # set, so it only ever logs on real success. Also now names
        # self.server_url — this class only ever represents ONE target
        # (the primary; see the class's own docstring on why secondary
        # targets never call this at all), but nothing in the message
        # said WHICH configured server that was, and a device with
        # multiple targets configured has no other way to tell from the
        # log alone.
        def _log_applied():
            logger.info(
                "✅ Applied server config v%d [%s]: "
                "backend=%s lat=%s lon=%s cooldown=%ss dur=%ss conf=%s",
                version,
                self.server_url,
                self._backend,
                bn.get("latitude")  or "unset",
                bn.get("longitude") or "unset",
                det.get("cooldown_seconds", "?"),
                rec.get("duration_seconds", "?"),
                bn.get("min_confidence", "?"),
            )

        # Was set unconditionally at the top of this function, before the
        # callback below ever ran — meaning a callback failure still left
        # this reporting "applied" to the server on the next heartbeat,
        # even though the live pipeline (gain, mics, detection settings)
        # never actually picked up the change. Only mark it applied once
        # the callback itself has actually succeeded — a real failure
        # here should keep showing Pending on the server (accurate)
        # rather than silently claiming success.
        _save_effective_config(merged)
        if self._on_config_update:
            try:
                self._on_config_update(merged)
                self._applied_version = version
                _log_applied()
            except Exception as e:
                logger.error("Config update callback error [%s]: %s", self.server_url, e)
        else:
            self._applied_version = version
            _log_applied()

