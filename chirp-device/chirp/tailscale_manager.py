"""
Tailscale/Headscale integration for chirp-device.

Gives the device a second, stable IP reachable across networks — not
just on whichever local LAN it happens to share with the server —
without needing any change to how server_sync.py's own heartbeat or
the server's SSH terminal work otherwise; this module's only job is
producing that one extra IP string.

install.sh installs the tailscale CLIENT unconditionally (it's inert
until actually configured and connected), but never authenticates or
connects it — that only ever happens here, driven entirely by
config.yaml's own tailscale: section, since only the person running
this device actually has the auth key (and, for a self-hosted
Headscale instance instead of Tailscale's own cloud service, the
login_server URL) needed to do that safely.

Headscale itself is a SERVER — a self-hosted, open-source alternative
to Tailscale's own coordination service — and does NOT belong here.
It runs once, centrally, wherever it's deployed (e.g. alongside
chirp-server-instances on the same machine); this module is the
CLIENT side only, exactly like the plain `tailscale` CLI would be if
you configured it by hand yourself.
"""
import logging
import os
import shutil
import subprocess
import threading
import time
from typing import Optional

logger = logging.getLogger("chirp.tailscale")


class TailscaleManager:
    """
    Started once at daemon startup if tailscale.enabled is true.
    Brings the connection up in a background thread (tailscale up can
    block for several seconds on first auth), then periodically
    refreshes the cached IP so get_ip() is always a fast, non-blocking
    call for server_sync.py's own heartbeat loop to read.
    """

    REFRESH_INTERVAL_SECONDS = 120

    def __init__(self, config: dict):
        ts_cfg = (config or {}).get("tailscale", {}) or {}
        self.enabled: bool = ts_cfg.get("enabled", False)
        self.auth_key: str = ts_cfg.get("auth_key", "")
        self.login_server: str = ts_cfg.get("login_server", "")  # empty → Tailscale's own cloud
        self.hostname: str = ts_cfg.get("hostname", "")  # empty → let tailscale pick (usually the system hostname)
        self._cached_ip: Optional[str] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._binary = shutil.which("tailscale")

    def start(self) -> None:
        if not self.enabled:
            return
        if not self._binary:
            logger.warning(
                "tailscale.enabled is true but the tailscale binary isn't installed — "
                "re-run install.sh, or install manually: https://tailscale.com/download"
            )
            return
        if not self.auth_key or "PLACEHOLDER" in self.auth_key:
            logger.warning("tailscale.enabled is true but auth_key looks unset — skipping. Generate one from your Tailscale/Headscale admin console.")
            return
        self._thread = threading.Thread(target=self._run, name="TailscaleManager", daemon=True)
        self._thread.start()
        logger.info(
            "TailscaleManager started (login_server=%s)",
            self.login_server or "tailscale.com (default cloud service)",
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def get_ip(self) -> Optional[str]:
        """Non-blocking — returns whatever was cached by the last refresh, or None if not yet connected."""
        return self._cached_ip

    def _run(self) -> None:
        self._ensure_up()
        while not self._stop_event.is_set():
            self._refresh_ip()
            self._stop_event.wait(self.REFRESH_INTERVAL_SECONDS)

    def _ensure_up(self) -> None:
        """
        Idempotent — safe to call on every startup even if already
        connected (tailscale up is itself idempotent: re-running it
        against an already-authenticated node is a fast no-op, not a
        re-auth). Runs synchronously in this manager's own background
        thread, never the main startup path, since first-time auth can
        take several seconds and nothing else needs to block on it.
        """
        cmd = [self._binary, "up", "--accept-routes"]
        if self.login_server:
            cmd.append(f"--login-server={self.login_server}")
        if self.auth_key:
            cmd.append(f"--authkey={self.auth_key}")
        if self.hostname:
            cmd.append(f"--hostname={self.hostname}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                stderr = result.stderr.strip()[:500]
                if "Access denied" in stderr or "checkprefs" in stderr:
                    # Found the hard way: tailscaled only lets root (or
                    # an explicitly granted "operator") control it, and
                    # this runs as whatever unprivileged user
                    # chirp-device's own service runs as. install.sh
                    # now grants operator permission automatically for
                    # a fresh Tailscale install — this is for anyone
                    # who installed the client before that existed, or
                    # installed it manually outside install.sh.
                    logger.warning(
                        "tailscale up failed: access denied — this user isn't a tailscale "
                        "operator yet. Fix with: sudo tailscale set --operator=%s (one-time, "
                        "then restart chirp-device)", os.environ.get("USER", "<this user>")
                    )
                else:
                    logger.warning("tailscale up failed (exit %d): %s", result.returncode, stderr)
            else:
                logger.info("tailscale up succeeded")
        except subprocess.TimeoutExpired:
            logger.warning("tailscale up timed out after 60s — will retry on next refresh cycle")
        except Exception as e:
            logger.warning("tailscale up raised an exception: %s", e)

    def _refresh_ip(self) -> None:
        try:
            result = subprocess.run([self._binary, "ip", "-4"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                ip = result.stdout.strip().splitlines()[0].strip() if result.stdout.strip() else ""
                if ip and ip != self._cached_ip:
                    logger.info("Tailscale IP: %s", ip)
                self._cached_ip = ip or None
            else:
                # Not yet connected/authenticated (e.g. auth key expired,
                # awaiting manual approval on the admin console) — not
                # fatal, just means get_ip() keeps returning None until
                # it resolves. Re-attempt bringing the connection up,
                # in case this is a transient/recoverable failure.
                self._cached_ip = None
                self._ensure_up()
        except Exception as e:
            logger.debug("tailscale ip check failed: %s", e)
