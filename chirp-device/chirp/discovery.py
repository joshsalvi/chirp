"""
Chirp Device — mDNS/Zeroconf Auto-Discovery

Announces the chirp-device presence on the local network so the Chirp Server
can find Raspberry Pi devices automatically via Settings → Devices → Discover.

Uses the _chirp._tcp service type so the server's avahi-browse scan finds it.
Also announces _ssh._tcp so the Push Credentials flow can locate the SSH port.

Requires: python-zeroconf  (installed by install.sh)
  pip install zeroconf

If zeroconf is unavailable, discovery silently falls back to ARP-table
scanning on the server side (Raspberry Pi MAC prefix detection).
"""

import logging
import socket
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class DeviceDiscovery:
    """
    Advertises this device on the local network via mDNS so the Chirp Server
    can discover it without manual IP configuration.

    Announced services:
      _chirp._tcp  port 80   — chirp-device health/status endpoint (if running)
      _ssh._tcp    port 22   — SSH for Push Credentials flow

    TXT records carry chirp-specific metadata:
      version    chirp-device software version
      platform   "Raspberry Pi 5 Model B Rev 1.0" etc.
      coral      "m2_pcie" | "usb" | "none"
      backend    "cpu" | "coral"
      paired     "true" | "false"  (updated when pairing state changes)
    """

    SERVICE_TYPE = "_chirp._tcp.local."
    SSH_SERVICE_TYPE = "_ssh._tcp.local."
    CHIRP_PORT = 8765   # Chirp server port — we'll re-use for health check if possible
    SSH_PORT = 22

    def __init__(self, config: dict, coral_form: str = "", is_paired: bool = False):
        self._config = config
        self._coral_form = coral_form
        self._is_paired = is_paired
        self._backend = config.get("detection", {}).get("birdnet", {}).get("backend", "cpu")

        self._zc = None
        self._info = None
        self._ssh_info = None
        self._registered = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    # ── Public API ──────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Register mDNS services. Returns True if successful."""
        try:
            from zeroconf import Zeroconf, ServiceInfo
        except ImportError:
            logger.info(
                "python-zeroconf not installed — mDNS discovery unavailable. "
                "Server will use ARP-table fallback for discovery. "
                "Install with: pip install zeroconf"
            )
            return False

        try:
            hostname = socket.gethostname()
            local_ip = self._get_local_ip()
            if not local_ip:
                logger.warning("Could not determine local IP — mDNS discovery disabled")
                return False

            ip_bytes = socket.inet_aton(local_ip)

            self._zc = Zeroconf()

            # _chirp._tcp service
            txt = {
                b"version": b"1.1.0",
                b"platform": _get_platform_short().encode(),
                b"coral": (self._coral_form or b"none") if isinstance(self._coral_form, bytes)
                          else (self._coral_form or "none").encode(),
                b"backend": self._backend.encode(),
                b"paired": b"true" if self._is_paired else b"false",
                b"hostname": hostname.encode(),
            }

            self._info = ServiceInfo(
                type_=self.SERVICE_TYPE,
                name=f"Chirp-{hostname}.{self.SERVICE_TYPE}",
                addresses=[ip_bytes],
                port=self.SSH_PORT,    # Port points to SSH for push-credentials flow
                properties=txt,
                server=f"{hostname}.local.",
            )

            # _ssh._tcp service (standard; helps the server's SSH discovery)
            self._ssh_info = ServiceInfo(
                type_=self.SSH_SERVICE_TYPE,
                name=f"{hostname}.{self.SSH_SERVICE_TYPE}",
                addresses=[ip_bytes],
                port=self.SSH_PORT,
                properties={b"chirp-device": b"true"},
                server=f"{hostname}.local.",
            )

            self._zc.register_service(self._info)
            self._zc.register_service(self._ssh_info)
            self._registered = True

            logger.info(
                "mDNS discovery active: %s @ %s (coral=%s backend=%s)",
                hostname, local_ip, self._coral_form or "none", self._backend,
            )

            # Background thread to periodically refresh TXT records
            # (e.g. paired state changes after first sync)
            self._thread = threading.Thread(
                target=self._refresh_loop, name="mDNS-refresh", daemon=True
            )
            self._thread.start()
            return True

        except Exception as e:
            # Log with type so empty-string exceptions are still identifiable
            logger.warning(
                "mDNS registration failed (%s: %s) — server ARP scan will find device instead",
                type(e).__name__, e or "(no detail)",
            )
            return False

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self._zc and self._registered:
            try:
                # Real fix for a confirmed "coroutine 'Zeroconf.
                # async_unregister_service' was never awaited" RuntimeWarning
                # at shutdown: close() already automatically unregisters
                # every service registered on this instance internally
                # (confirmed directly from zeroconf's own source —
                # Zeroconf.close() calls self.unregister_all_services()
                # itself when it's safe to do so), via a plain synchronous
                # path. The explicit unregister_service() calls that used to
                # be here instead go through unregister_service()'s own
                # async-coroutine-based path (it wraps and awaits
                # async_unregister_service via an internal helper), which
                # could race with close() tearing down this same instance's
                # event loop immediately afterward — the most likely real
                # source of the warning. Trusting close()'s own built-in
                # cleanup avoids that race entirely rather than working
                # around it.
                self._zc.close()
            except Exception:
                pass

    def update_paired_state(self, paired: bool) -> None:
        """Call this when pairing state changes to update TXT record."""
        with self._lock:
            self._is_paired = paired
        if self._registered and self._info and self._zc:
            try:
                self._info.properties[b"paired"] = b"true" if paired else b"false"
                self._zc.update_service(self._info)
                logger.debug("mDNS TXT updated: paired=%s", paired)
            except Exception as e:
                logger.debug("mDNS TXT update error: %s", e)

    def update_backend(self, backend: str) -> None:
        """Call when inference backend changes (e.g. server pushes coral config)."""
        with self._lock:
            self._backend = backend
        if self._registered and self._info and self._zc:
            try:
                self._info.properties[b"backend"] = backend.encode()
                self._zc.update_service(self._info)
            except Exception:
                pass

    # ── Internals ────────────────────────────────────────────────────────────

    def _refresh_loop(self) -> None:
        """Re-register service every 5 minutes to ensure TTL doesn't expire."""
        while not self._stop_event.is_set():
            self._stop_event.wait(300)  # 5 minutes
            if self._stop_event.is_set():
                break
            if self._registered and self._info and self._zc:
                try:
                    self._zc.update_service(self._info)
                except Exception as e:
                    logger.debug("mDNS refresh error: %s", e)

    @staticmethod
    def _get_local_ip() -> Optional[str]:
        """Get the primary local network IP (not 127.0.0.1)."""
        # Try connecting to a known address to determine outbound interface
        for target in ("8.8.8.8", "1.1.1.1"):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(1)
                s.connect((target, 80))
                ip = s.getsockname()[0]
                s.close()
                if ip and not ip.startswith("127."):
                    return ip
            except Exception:
                pass
        # Fallback: hostname resolution
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return None


def _get_platform_short() -> str:
    """Return a short platform string for mDNS TXT records."""
    try:
        with open("/proc/device-tree/model", "r") as f:
            m = f.read().strip().replace("\x00", "")
            # Shorten "Raspberry Pi 5 Model B Rev 1.0" → "RPi5"
            if "Raspberry Pi 5" in m:
                return "RPi5"
            elif "Raspberry Pi 4" in m:
                return "RPi4"
            elif "Raspberry Pi" in m:
                return "RPi"
            return m[:16]
    except Exception:
        import platform
        return platform.machine()[:16]
