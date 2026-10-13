"""
Which address the server uses to reach a device (SSH, logs, Listen, mic
levels), and how to get there over Tailscale.

Per-device `connect_via`:
  auto       Tailscale when the server is on the tailnet and the device has
             reported a Tailscale IP, otherwise the LAN IP. The other address
             is the fallback where a caller can retry (SSH terminal).
  lan        LAN IP only.
  tailscale  Tailscale IP only.

Reaching a Tailscale IP: with kernel TUN (docker-compose gives the container
/dev/net/tun + NET_ADMIN) the OS routes 100.x directly. If tailscaled fell
back to userspace networking there is no tailscale0 interface, so traffic
goes through tailscaled's SOCKS5 (localhost:1055) and HTTP (localhost:1056)
proxies, which tailscale_manager starts with the daemon.

`python -m app.services.device_net HOST PORT` relays stdin/stdout through
the SOCKS5 proxy; it's the ssh ProxyCommand for subprocess ssh calls.
"""
from __future__ import annotations

import ipaddress
import os
import socket
import struct
import sys
from typing import List, Optional

SOCKS5_ADDR = ("127.0.0.1", 1055)
HTTP_PROXY_URL = "http://127.0.0.1:1056"
VALID_VIA = ("auto", "lan", "tailscale")

_TAILNET_V4 = ipaddress.ip_network("100.64.0.0/10")
_TAILNET_V6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")

_ts_manager = None


def set_tailscale_manager(mgr) -> None:
    global _ts_manager
    _ts_manager = mgr


def _tailscale_iface() -> bool:
    return os.path.exists("/sys/class/net/tailscale0")


_proxy_probe = {"t": 0.0, "ok": False}


def _proxy_up() -> bool:
    """tailscaled's SOCKS5 proxy is listening (cached 30 s)."""
    import time as _t
    now = _t.monotonic()
    if now - _proxy_probe["t"] < 30:
        return _proxy_probe["ok"]
    try:
        socket.create_connection(SOCKS5_ADDR, timeout=0.5).close()
        ok = True
    except OSError:
        ok = False
    _proxy_probe.update(t=now, ok=ok)
    return ok


def server_on_tailnet() -> bool:
    """Server can reach tailnet IPs: its tailscaled reports connected, the
    host (network_mode: host) has a tailscale0 interface, or tailscaled's
    SOCKS5 proxy is up (a daemon the manager lost track of still routes)."""
    try:
        if _ts_manager is not None and _ts_manager.is_connected():
            return True
    except Exception:
        pass
    return _tailscale_iface() or _proxy_up()


def is_tailnet(host: Optional[str]) -> bool:
    try:
        ip = ipaddress.ip_address((host or "").strip("[]"))
    except ValueError:
        return False
    return ip in (_TAILNET_V4 if ip.version == 4 else _TAILNET_V6)


def needs_proxy(host: Optional[str]) -> bool:
    """Tailnet address with no kernel route (userspace tailscaled)."""
    return is_tailnet(host) and not _tailscale_iface()


def _clean_lan(dev) -> Optional[str]:
    raw = (getattr(dev, "ip_address", None) or "").strip()
    if not raw:
        return None
    if raw.startswith("::ffff:"):
        raw = raw[7:]
    return raw


def candidates(dev, via: Optional[str] = None) -> List[str]:
    """Addresses to try, best first. `via` overrides the device setting
    ("local" is accepted as an alias for "lan")."""
    pref = (via or getattr(dev, "connect_via", None) or "auto").lower()
    if pref == "local":
        pref = "lan"
    lan = _clean_lan(dev)
    ts = (getattr(dev, "tailscale_ip", None) or "").strip() or None
    if pref == "lan":
        order = [lan]
    elif pref == "tailscale":
        order = [ts]
    elif ts and server_on_tailnet():
        order = [ts, lan]
    else:
        order = [lan, ts if server_on_tailnet() else None]
    out: List[str] = []
    for h in order:
        if h and h not in out:
            out.append(h)
    return out


def device_address(dev, via: Optional[str] = None) -> Optional[str]:
    c = candidates(dev, via)
    return c[0] if c else None


def via_label(host: Optional[str]) -> str:
    return "Tailscale" if is_tailnet(host) else "LAN"


# ── Proxy plumbing ───────────────────────────────────────────────────────────

def socks5_connect(host: str, port: int, timeout: float = 10.0) -> socket.socket:
    """CONNECT through tailscaled's SOCKS5 proxy (no auth)."""
    s = socket.create_connection(SOCKS5_ADDR, timeout=timeout)
    try:
        s.sendall(b"\x05\x01\x00")
        if s.recv(2) != b"\x05\x00":
            raise OSError("SOCKS5 proxy refused the greeting")
        ip = ipaddress.ip_address(host.strip("[]"))
        atyp, addr = (b"\x01", ip.packed) if ip.version == 4 else (b"\x04", ip.packed)
        s.sendall(b"\x05\x01\x00" + atyp + addr + struct.pack(">H", port))
        hdr = _recv_exact(s, 4)
        if hdr[1] != 0:
            raise OSError(f"SOCKS5 connect to {host}:{port} failed (code {hdr[1]})")
        atyp_r = hdr[3]
        bound = 4 if atyp_r == 1 else 16 if atyp_r == 4 else _recv_exact(s, 1)[0]
        _recv_exact(s, bound + 2)          # bound address + port
        s.settimeout(None)
        return s
    except Exception:
        s.close()
        raise


def _recv_exact(s: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise OSError("SOCKS5 proxy closed the connection")
        buf += chunk
    return buf


def paramiko_sock(host: str, port: int = 22, timeout: float = 10.0):
    """`sock=` for paramiko.SSHClient.connect: a proxied socket when needed,
    else None (paramiko connects directly)."""
    return socks5_connect(host, port, timeout) if needs_proxy(host) else None


def httpx_kwargs(host: str) -> dict:
    return {"proxy": HTTP_PROXY_URL} if needs_proxy(host) else {}


def ssh_opts(host: str) -> List[str]:
    """Extra args for a subprocess `ssh` so it reaches a tailnet host."""
    if not needs_proxy(host):
        return []
    return ["-o", f"ProxyCommand={sys.executable} -m app.services.device_net %h %p"]


def _relay(host: str, port: int) -> int:
    import selectors
    s = socks5_connect(host, port)
    sel = selectors.DefaultSelector()
    sel.register(sys.stdin.buffer, selectors.EVENT_READ)
    sel.register(s, selectors.EVENT_READ)
    out = sys.stdout.buffer
    while True:
        for key, _ in sel.select():
            if key.fileobj is s:
                data = s.recv(65536)
                if not data:
                    return 0
                out.write(data)
                out.flush()
            else:
                data = os.read(sys.stdin.fileno(), 65536)
                if not data:
                    s.shutdown(socket.SHUT_WR)
                    sel.unregister(sys.stdin.buffer)
                    continue
                s.sendall(data)


if __name__ == "__main__":
    sys.exit(_relay(sys.argv[1], int(sys.argv[2])))
