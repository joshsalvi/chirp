"""
Bluetooth setup mode for a brand-new Pi with no network connection yet.

Starts a temporary BLE peripheral ("Chirp Setup") the phone app can
discover and use to read nearby WiFi networks, write chosen credentials,
and watch connection status. Stops advertising once actually online —
a one-time bridge, not something that runs alongside normal operation.

NOT validated against real Bluetooth hardware. Follows bluezero's
documented API and the current nmcli/NetworkManager approach for
Raspberry Pi OS Bookworm+ (which replaced wpa_supplicant), but BLE
peripheral behavior is finicky in practice and needs real-device testing.

Requires: `pip install bluezero` and BlueZ (present by default on
Raspberry Pi OS).
"""

import json
import logging
import subprocess
import threading
import time

logger = logging.getLogger("chirp.ble_setup")

# Custom UUIDs for this service — not a standard Bluetooth SIG service,
# since "here's a list of WiFi networks, write me credentials" isn't a
# defined GATT profile. Generated once and fixed here; the app needs the
# exact same values to find and talk to this service.
SETUP_SERVICE_UUID = "7e9a9a00-9d1c-4a3a-8f5e-9b6c7d8e9f01"
NETWORKS_CHAR_UUID = "7e9a9a01-9d1c-4a3a-8f5e-9b6c7d8e9f01"
CREDENTIALS_CHAR_UUID = "7e9a9a02-9d1c-4a3a-8f5e-9b6c7d8e9f01"
STATUS_CHAR_UUID = "7e9a9a03-9d1c-4a3a-8f5e-9b6c7d8e9f01"

DEVICE_LOCAL_NAME = "Chirp Setup"


def is_online(timeout: float = 3.0) -> bool:
    """
    True if this Pi currently has a working network connection. Checked
    via NetworkManager's own connection state rather than trying to reach
    the internet directly, since a device can be legitimately connected
    to a LAN without outbound internet access, and this only cares about
    "does it have a network," not "can it reach Chirp's server."
    """
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "STATE", "general", "status"],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.returncode == 0 and "connected" in result.stdout.strip().lower()
    except Exception as e:
        logger.debug("is_online check failed: %s", e)
        return False


def _scan_networks(timeout: float = 10.0):
    """Returns a list of nearby SSIDs, strongest signal first, deduplicated
    (the same network is often visible on multiple channels/APs)."""
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "SSID,SIGNAL", "device", "wifi", "list", "--rescan", "yes"],
            capture_output=True, text=True, timeout=timeout,
        )
        seen = {}
        for line in result.stdout.strip().split("\n"):
            if not line or ":" not in line:
                continue
            # nmcli terse output escapes ':' inside the SSID as '\:', so a
            # plain split(":") would break on any SSID containing a colon
            parts = line.rsplit(":", 1)
            if len(parts) != 2:
                continue
            ssid, signal = parts[0].replace("\\:", ":"), parts[1]
            if not ssid:
                continue  # hidden network, nothing useful to show
            try:
                signal_val = int(signal)
            except ValueError:
                signal_val = 0
            if ssid not in seen or signal_val > seen[ssid]:
                seen[ssid] = signal_val
        return sorted(seen.keys(), key=lambda s: -seen[s])
    except Exception as e:
        logger.warning("WiFi scan failed: %s", e)
        return []


def _connect_to_network(ssid: str, password: str, timeout: float = 25.0) -> tuple:
    """Attempts the connection via nmcli, the documented, current way to
    do this on Bookworm and later. Returns (success, message)."""
    try:
        result = subprocess.run(
            ["nmcli", "device", "wifi", "connect", ssid, "password", password],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0:
            return True, "connected"
        return False, (result.stderr or result.stdout or "connection failed").strip()[:200]
    except subprocess.TimeoutExpired:
        return False, "timed out"
    except Exception as e:
        return False, str(e)[:200]


class BleSetupMode:
    """
    Owns the BLE peripheral's lifetime. Call start() once network
    connectivity is confirmed missing; it blocks (on its own thread)
    until either credentials are successfully applied or stop() is
    called externally (e.g. by a timeout in the caller).
    """

    def __init__(self):
        self._peripheral = None
        self._status = "idle"
        self._stop_event = threading.Event()
        self._thread = None

    def _set_status(self, status: str):
        self._status = status
        logger.info("BLE setup status: %s", status)
        if self._peripheral is not None:
            try:
                # bluezero's notify pattern — update the stored value,
                # then push it. Exact call shape may need adjustment once
                # tested against a real bluezero install.
                self._peripheral.update_value(SETUP_SERVICE_UUID, STATUS_CHAR_UUID, list(status.encode("utf-8")))
            except Exception as e:
                logger.debug("Status notify failed (non-fatal): %s", e)

    def _read_networks(self):
        networks = _scan_networks()
        return list(json.dumps(networks[:20]).encode("utf-8"))  # cap at 20 — a long list adds nothing on a small phone screen

    def _read_status(self):
        return list(self._status.encode("utf-8"))

    def _write_credentials(self, value, options=None):
        try:
            raw = bytes(value).decode("utf-8")
            payload = json.loads(raw)
            ssid = payload.get("ssid", "").strip()
            password = payload.get("password", "")
        except Exception as e:
            logger.warning("BLE setup: malformed credentials payload: %s", e)
            self._set_status("failed: malformed request")
            return

        if not ssid:
            self._set_status("failed: no network name given")
            return

        self._set_status("connecting")
        ok, detail = _connect_to_network(ssid, password)
        if ok:
            self._set_status("connected")
            # Give the caller a moment to see the "connected" status over
            # BLE before this tears itself down.
            threading.Timer(3.0, self.stop).start()
        else:
            self._set_status(f"failed: {detail}")

    def start(self):
        if self._thread is not None:
            return  # already running
        self._thread = threading.Thread(target=self._run, daemon=True, name="ble-setup")
        self._thread.start()

    def _run(self):
        try:
            from bluezero import peripheral
        except ImportError:
            logger.error(
                "BLE setup mode requires the 'bluezero' package — install with "
                "'pip install bluezero' (and ensure bluez itself is installed and "
                "bluetoothd is running). Skipping BLE setup entirely for this run."
            )
            return

        try:
            self._peripheral = peripheral.Peripheral(local_name=DEVICE_LOCAL_NAME)
            self._peripheral.add_service(srv_id=1, uuid=SETUP_SERVICE_UUID, primary=True)
            self._peripheral.add_characteristic(
                srv_id=1, chr_id=1, uuid=NETWORKS_CHAR_UUID,
                value=[], notifying=False, flags=["read"],
                read_callback=self._read_networks,
            )
            self._peripheral.add_characteristic(
                srv_id=1, chr_id=2, uuid=CREDENTIALS_CHAR_UUID,
                value=[], notifying=False, flags=["write"],
                write_callback=self._write_credentials,
            )
            self._peripheral.add_characteristic(
                srv_id=1, chr_id=3, uuid=STATUS_CHAR_UUID,
                value=list(b"idle"), notifying=True, flags=["read", "notify"],
                read_callback=self._read_status,
            )
            logger.info("BLE setup mode: advertising as '%s' — waiting for the app to connect", DEVICE_LOCAL_NAME)
            self._peripheral.publish()  # blocks until stop() tears down the underlying event loop
        except Exception as e:
            logger.error("BLE setup mode failed to start: %s", e)

    def stop(self):
        self._stop_event.set()
        if self._peripheral is not None:
            try:
                self._peripheral.stop_advertising()
            except Exception:
                pass


def run_setup_if_needed(max_wait_seconds: float = 600.0) -> bool:
    """
    Called once at startup, before anything else. If the Pi already has a
    network connection, this is a fast no-op — returns immediately.
    Otherwise starts BLE setup mode and waits (checking periodically)
    until either connectivity is established or max_wait_seconds elapses,
    at which point it gives up and returns False so the caller can decide
    what to do next (retry later, log a persistent warning, etc.) rather
    than blocking forever with the rest of Chirp never starting at all.
    """
    if is_online():
        return True

    logger.info("No network connection detected — starting BLE setup mode")
    setup = BleSetupMode()
    setup.start()

    waited = 0.0
    check_interval = 5.0
    while waited < max_wait_seconds:
        time.sleep(check_interval)
        waited += check_interval
        if is_online():
            logger.info("Network connection established after BLE setup — continuing startup")
            setup.stop()
            return True

    logger.warning(
        "BLE setup mode timed out after %.0fs with no network connection established. "
        "Chirp will keep running but recordings won't upload until it's connected — "
        "restart the service once WiFi is configured (via the app, or manually with "
        "nmcli/nmtui) to try again.",
        max_wait_seconds,
    )
    setup.stop()
    return False
