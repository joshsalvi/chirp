"""
Tailscale/Headscale integration for this SERVER container.

The counterpart to chirp-device's own tailscale_manager.py — that one
gives a Pi a second, stable IP reachable off its local network; this
one does the same thing for the server itself, which previously had no
Tailscale awareness at all. A device could already be reached over
Tailscale from the server's own SSH terminal, but the server's own web
UI could only ever be reached however the local network/reverse proxy/
tunnel already exposed it — this closes that gap, the same way, using
the same proven logic (deliberately mirrored, not reinvented).

The Dockerfile installs the tailscale CLIENT unconditionally (inert
until configured and connected, same reasoning as chirp-device's own
install.sh); this module is what actually authenticates and connects
it, driven entirely by the tailscale_* Settings fields (env-driven,
same as secret_key/admin_password), since only the person running this
server actually has the real auth key needed to do that safely.

Headscale itself is a SERVER — a separate, self-hosted, open-source
alternative to Tailscale's own coordination service — and does NOT
belong here; if self-hosting one, point tailscale_login_server at it.
This module is the CLIENT side only, same as chirp-device's.
"""
import logging
import os
import shutil
import subprocess
import threading
import time
from typing import Optional

logger = logging.getLogger("chirp.tailscale")


def _tailscaled_pids(state_dir: str) -> list:
    """PIDs of tailscaled processes using this container's state dir (no ps
    in the image, so read /proc)."""
    pids = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as f:
                argv = f.read().split(b"\0")
        except OSError:
            continue
        if argv and os.path.basename(argv[0].decode(errors="replace")) == "tailscaled" \
                and any(state_dir.encode() in a for a in argv):
            pids.append(int(entry))
    return pids


def _stop_pids(pids: list, wait_s: float = 5.0) -> None:
    import signal
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.time() + wait_s
    while time.time() < deadline and any(os.path.exists(f"/proc/{p}") for p in pids):
        time.sleep(0.2)
    for pid in pids:
        if os.path.exists(f"/proc/{pid}"):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass


class TailscaleManager:
    """
    Started once at server startup if settings.tailscale_enabled is
    true. Brings the connection up in a background thread (tailscale up
    can block for several seconds on first auth), then periodically
    refreshes the cached IP so get_ip()/is_connected() are always fast,
    non-blocking calls for a status endpoint to read.
    """

    REFRESH_INTERVAL_SECONDS = 120

    def __init__(self, settings):
        self.enabled: bool = bool(getattr(settings, "tailscale_enabled", False))
        self.auth_key: str = getattr(settings, "tailscale_auth_key", "") or ""
        self.login_server: str = getattr(settings, "tailscale_login_server", "") or ""
        self.hostname: str = getattr(settings, "tailscale_hostname", "") or ""
        self._cached_ip: Optional[str] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._binary = shutil.which("tailscale")
        self._daemon_proc: Optional[subprocess.Popen] = None

    def start(self, wait_for_first_connect: bool = False) -> None:
        """
        wait_for_first_connect=True runs the first `tailscale up` + IP
        check synchronously, in the calling thread, before handing off
        to the periodic background refresh — used by reconfigure()
        (i.e. the "Save & Connect" button), where the caller is a live
        API request and the whole point is giving the person an
        immediate, accurate answer rather than "enabled" with no way to
        know yet whether it actually connected. Plain server-boot start()
        deliberately stays non-blocking (the default): a slow or
        misconfigured Tailscale shouldn't delay the rest of the app
        coming up.
        """
        if not self.enabled:
            return
        if not self._binary:
            logger.warning(
                "CHIRP_TAILSCALE_ENABLED is true but the tailscale binary isn't installed in this image — "
                "rebuild from the current Dockerfile, or install manually: https://tailscale.com/download"
            )
            return
        if not self.auth_key:
            logger.warning("CHIRP_TAILSCALE_ENABLED is true but CHIRP_TAILSCALE_AUTH_KEY isn't set — skipping. Generate one from your Tailscale/Headscale admin console.")
            return
        skip_first_connect = False
        if wait_for_first_connect:
            self._ensure_up()
            self._refresh_ip()
            skip_first_connect = True
        self._thread = threading.Thread(target=self._run, name="TailscaleManager", args=(skip_first_connect,), daemon=True)
        self._thread.start()
        logger.info(
            "Server-side TailscaleManager started (login_server=%s)",
            self.login_server or "tailscale.com (default cloud service)",
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def reconfigure(self, enabled: bool, auth_key: str = "", login_server: str = "", hostname: str = "") -> dict:
        """
        Applies a new config live — from Settings → Server Network's own
        "Save & Connect" button, or Global Admin's equivalent — without
        needing a container restart, which is the whole point of making
        this a Settings toggle instead of only an env var: the person
        just pasted in a real auth key and wants it to work right now.

        Safe to call whether currently running or not: stops any
        existing background thread first (a no-op if none is running),
        applies the new values, then starts fresh if the new config is
        enabled. Returns the resulting status() so the caller (the API
        endpoint) can hand it straight back to the frontend without a
        second round-trip.
        """
        self.stop()
        self._stop_event = threading.Event()
        self.enabled = bool(enabled)
        self.auth_key = auth_key or ""
        self.login_server = login_server or ""
        self.hostname = hostname or ""
        self._binary = shutil.which("tailscale")
        if self.enabled:
            self.start(wait_for_first_connect=True)
        else:
            self._cached_ip = None
        return self.status()

    def get_ip(self) -> Optional[str]:
        """Non-blocking — returns whatever was cached by the last refresh, or None if not yet connected."""
        return self._cached_ip

    def is_connected(self) -> bool:
        return self._cached_ip is not None

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "binary_installed": bool(self._binary),
            "connected": self.is_connected(),
            "ip": self._cached_ip,
            "login_server": self.login_server or None,
        }

    def _run(self, skip_first_connect: bool = False) -> None:
        if not skip_first_connect:
            self._ensure_up()
        while not self._stop_event.is_set():
            self._refresh_ip()
            self._stop_event.wait(self.REFRESH_INTERVAL_SECONDS)

    def _ensure_daemon_running(self, force_userspace: bool = False) -> None:
        """
        Real gap found and fixed: `tailscale up` only ever talks to an
        already-running `tailscaled` background daemon. On a normal
        Linux host (chirp-device's own Pi), installing the tailscale
        package via apt also starts that daemon automatically, through
        systemd — which is exactly why chirp-device's own
        TailscaleManager never needed to start it itself. This
        container has no systemd or any init system at all (PID 1 is
        this Python process), so the daemon package got installed by
        the Dockerfile but the daemon itself was never actually
        running — every `tailscale up` call was failing silently
        against a socket that didn't exist, which is why Settings
        could show "enabled" forever without ever reaching "connected".

        Started here instead, once, idempotently (checked via its own
        socket file so a second call is a harmless no-op). Prefers the
        real kernel TUN device docker-compose.yml grants (NET_ADMIN +
        /dev/net/tun) over slower userspace networking — but found the
        hard way that granting the capability in docker-compose.yml
        doesn't guarantee it's actually in effect for a given running
        container (Unraid's Compose Manager, a stale container that
        needs a full recreate not just a rebuild, a host-level
        restriction — several real causes, no way to tell which from
        here). So this doesn't just check whether /dev/net/tun exists
        as a path (it did, and kernel mode still failed with
        "tstun.New(...): operation not permitted") — force_userspace=True
        forces the fallback regardless, and _ensure_up automatically
        retries with it once if a kernel-mode attempt's own log shows
        that exact permission failure. Userspace networking needs no
        special capabilities at all, at a modest throughput cost that's
        irrelevant for what this server actually sends over it
        (coordination traffic, SSH forwarding — not raw throughput).

        State/socket live under /app/data, not /var/run or /var/lib —
        found the hard way: this container drops from root to an
        unprivileged user (via gosu, in docker-entrypoint.sh) before
        this code ever runs, so it can't create directories under
        /var/run at all ("Permission denied"). /app/data is already
        that same unprivileged user's own directory (it's what every
        recording/database write in this whole app already uses), so
        no root access is needed for any of this.

        Tracks its own child process (self._daemon_proc) rather than
        only checking for the socket file — found the hard way, again:
        without this, a call that arrives while a just-launched daemon
        is still mid-startup (socket not created yet) would conclude
        "no daemon running" and launch a SECOND one, which then fights
        the first for the same TUN device and neither ever comes up
        cleanly. stdout/stderr are captured to a log file instead of
        discarded, and surfaced on the next connection failure — a
        daemon that starts but can't actually initialize (TUN
        permission issue, a stale lock from a previous crash, etc.)
        used to fail completely silently.
        """
        state_dir = "/app/data/.tailscale"
        socket_path = self._TAILSCALE_SOCKET
        if self._daemon_proc is not None and self._daemon_proc.poll() is None:
            return  # already launched and still alive — nothing to do
        if self._socket_responds():
            return
        # A tailscaled we can't talk to (its socket was removed, or it
        # never finished starting) still holds the state file and the
        # 1055/1056 proxy ports, so a second daemon can't start. Stop it
        # and start one clean daemon.
        stale = _tailscaled_pids(state_dir)
        if stale:
            logger.warning("Stopping unreachable tailscaled pid(s) %s before starting a fresh one", stale)
            _stop_pids(stale)
        try:
            os.remove(socket_path)
        except OSError:
            pass
        os.makedirs(state_dir, exist_ok=True)
        tailscaled = shutil.which("tailscaled")
        if not tailscaled:
            logger.warning("tailscaled binary not found alongside tailscale — was the image built from the current Dockerfile?")
            return
        # Once kernel TUN has failed with a permission error, later restarts
        # go straight to userspace (marker file; removed by a container
        # rebuild that wipes it, or by hand).
        no_tun_marker = f"{state_dir}/kernel-tun-blocked"
        if not force_userspace and os.path.exists(no_tun_marker):
            force_userspace = True
        tun_mode = "userspace-networking" if (force_userspace or not os.path.exists("/dev/net/tun")) else None
        cmd = [
            tailscaled,
            f"--state={state_dir}/tailscaled.state",
            f"--socket={socket_path}",
            # Local proxies so the server can reach devices' Tailscale IPs
            # even in userspace mode (no tailscale0 route); see device_net.py.
            "--socks5-server=127.0.0.1:1055",
            "--outbound-http-proxy-listen=127.0.0.1:1056",
        ]
        if tun_mode:
            cmd.append(f"--tun={tun_mode}")
            if not force_userspace:
                logger.warning("/dev/net/tun not available — falling back to userspace networking (slower, but functional). Check docker-compose.yml's devices: entry if this is unexpected.")
        log_path = f"{state_dir}/tailscaled.log"
        try:
            log_f = open(log_path, "ab")
            self._daemon_proc = subprocess.Popen(cmd, stdout=log_f, stderr=log_f)
            logger.info("Started tailscaled (%s), pid=%d, log=%s", "kernel TUN" if not tun_mode else "userspace networking", self._daemon_proc.pid, log_path)
        except Exception as e:
            logger.warning("Failed to start tailscaled: %s", e)
            return
        # Give it a moment to create its socket AND accept on it before the
        # immediately-following `tailscale up` call tries to use it.
        for _ in range(40):
            if self._socket_responds():
                break
            if self._daemon_proc.poll() is not None:
                # Exited already — dead on arrival. Surface its own log
                # tail directly rather than making the person go dig
                # for it themselves, and — if this was a kernel-TUN
                # attempt that died specifically from a permission
                # problem creating the interface — retry once, forced
                # into userspace networking, instead of leaving it
                # permanently broken.
                tail = self._read_daemon_tail(log_path)
                logger.warning("tailscaled exited immediately after starting — its own log:\n%s", tail)
                if not force_userspace and tail and ("operation not permitted" in tail or "tstun.New" in tail):
                    logger.warning("Kernel TUN creation failed with a permission error — retrying once with userspace networking instead.")
                    try:
                        open(no_tun_marker, "w").write(time.strftime("%Y-%m-%dT%H:%M:%S"))
                    except OSError:
                        pass
                    self._daemon_proc = None
                    self._ensure_daemon_running(force_userspace=True)
                break
            time.sleep(0.25)

    def _read_daemon_tail(self, log_path: str, lines: int = 15) -> str:
        try:
            with open(log_path, "rb") as f:
                tail = f.read()[-4000:].decode("utf-8", errors="replace")
            return "\n".join(tail.splitlines()[-lines:])
        except Exception:
            return ""

    def _log_daemon_tail(self, log_path: str, lines: int = 15) -> None:
        tail = self._read_daemon_tail(log_path, lines)
        if tail:
            logger.warning("tailscaled's own recent log:\n%s", tail)

    _TAILSCALE_SOCKET = "/app/data/.tailscale/tailscaled.sock"

    def _socket_responds(self) -> bool:
        """The daemon's local API socket exists and accepts a connection."""
        import socket as _socket
        if not os.path.exists(self._TAILSCALE_SOCKET):
            return False
        s = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        s.settimeout(1.0)
        try:
            s.connect(self._TAILSCALE_SOCKET)
            return True
        except OSError:
            return False
        finally:
            s.close()

    def _ensure_up(self) -> None:
        """
        Idempotent — safe to call on every startup even if already
        connected (tailscale up is itself idempotent: re-running it
        against an already-authenticated node is a fast no-op, not a
        re-auth). Runs synchronously in this manager's own background
        thread, never the main startup path, since first-time auth can
        take several seconds and nothing else needs to block on it.
        """
        self._ensure_daemon_running()
        cmd = [self._binary, f"--socket={self._TAILSCALE_SOCKET}", "up", "--accept-routes"]
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
                logger.warning("tailscale up failed (exit %d): %s", result.returncode, stderr)
                if "doesn't appear to be running" in stderr or "connect to local tailscaled" in stderr:
                    # Nothing healthy behind the socket. Don't delete the
                    # socket here: removing it while the daemon is alive
                    # orphans that daemon (it keeps the state file and
                    # proxy ports, so every later start fails). The next
                    # _ensure_daemon_running() stops it and starts clean.
                    self._daemon_proc = None
                    self._log_daemon_tail("/app/data/.tailscale/tailscaled.log")
            else:
                logger.info("tailscale up succeeded")
        except subprocess.TimeoutExpired:
            logger.warning("tailscale up timed out after 60s — will retry on next refresh cycle")
            # The daemon itself didn't crash here (that's the branch
            # above, via _ensure_daemon_running's own dead-on-arrival
            # check) — it's still running, just never finished the
            # actual coordination handshake within 60s. That daemon's
            # own ongoing log is the only place that's visible (stuck
            # on DERP, a slow/blocked path to login_server, something
            # about the auth key) — surfaced here since this is exactly
            # the moment that log actually has something useful in it.
            self._log_daemon_tail("/app/data/.tailscale/tailscaled.log", lines=25)
        except Exception as e:
            logger.warning("tailscale up raised an exception: %s", e)

    def _refresh_ip(self) -> None:
        try:
            result = subprocess.run([self._binary, f"--socket={self._TAILSCALE_SOCKET}", "ip", "-4"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                ip = result.stdout.strip().splitlines()[0].strip() if result.stdout.strip() else ""
                if ip and ip != self._cached_ip:
                    logger.info("Server Tailscale IP: %s", ip)
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
