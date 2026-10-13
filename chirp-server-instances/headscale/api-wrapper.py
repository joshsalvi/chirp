#!/usr/bin/env python3
"""
A small, dependency-free (stdlib only — no pip install needed) HTTP
wrapper around headscale's own CLI, running as a second process
inside this same container alongside `headscale serve` itself.

Why this exists, not a direct call to headscale's gRPC admin API:
confirmed directly, the hard way — the gRPC listener genuinely only
speaks gRPC (HTTP/2 + protobuf framing), not a REST/JSON gateway the
way some other Go services bundle on the same port. A plain HTTP/1.1
request to it fails with "illegal request line", a Go HTTP/2 server's
response to a client that isn't actually speaking its protocol. Headscale
does NOT bundle a grpc-gateway translation layer — confirmed against its
own documentation, which describes that port specifically as "used for
controlling a headscale server remotely with the CLI". Standing up a
real gRPC client from Python needs generated protobuf/grpc stubs
matching headscale's own .proto schema (a real new dependency,
grpcio + grpcio-tools, version-pinned to this exact headscale release)
for the sake of one read-only, already-solved-by-the-CLI endpoint — not
worth it. The CLI itself is the officially supported, always-correct
interface; this just puts a thin HTTP face on it.

Auth: reuses the same /shared/apikey file entrypoint.sh already
generates via `headscale apikeys create` — not because this wrapper
calls headscale's own API with it (it doesn't; it shells out to the
CLI directly, which talks to headscale over its local unix_socket, no
network auth needed within the same trust boundary), but as a
convenient, already-provisioned shared secret between this wrapper and
chirp-server-instances, so the loopback-only port still isn't a fully
open, unauthenticated read endpoint.

Known CLI gotcha, defended against below: `--output=json` (the `=`
form) has a documented bug where an update-nag banner ("An updated
version of Headscale has been found...") gets prepended to stdout and
breaks JSON parsing. `--output json` (space form) avoids the argument-
parsing side of that bug, but this still locates the actual JSON start
in stdout defensively rather than assuming the whole output is clean —
belt and suspenders, since this couldn't be verified against a live
instance before shipping.
"""
import http.server
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time

# 0.0.0.0, not 127.0.0.1 — the exact same lesson already learned the
# hard way for headscale's own grpc_listen_addr (see config.yaml's
# history): Docker's port-forwarding reaches a container via its
# external network interface, never via the container's OWN loopback,
# so a service bound to 127.0.0.1 INSIDE a container is completely
# unreachable through `ports:` publishing regardless of what the
# host-side mapping says — this is exactly what produced a real
# "Connection reset by peer" (Docker's proxy accepts the connection on
# the host side, then finds nothing to hand it to inside). Safety
# still comes entirely from the HOST-side mapping in docker-compose.yml
# being 127.0.0.1:50444:50444, not 0.0.0.0:50444:50444 — binding wide
# open inside the container is safe precisely because the host only
# ever exposes that to its own loopback.
LISTEN_ADDR = ("0.0.0.0", 50444)
API_KEY_FILE = "/shared/apikey"

# Watchdog: headscale 0.23.0 can keep serving clients while its admin
# socket stops answering, so every CLI command fails with "Could not
# connect: context deadline exceeded" until headscale restarts (seen
# 2026-10-11 after three days up). Every WATCH_EVERY_S this asks the
# CLI for the user list; after WATCH_FAILURES failures in a row it stops
# headscale, entrypoint.sh exits, and Docker's restart policy brings the
# container back (clients reconnect within seconds).
WATCH_EVERY_S = 300
WATCH_FAILURES = 2
CLI_TIMEOUT_S = 15


def _log(msg):
    print(f"[api-wrapper] {msg}", file=sys.stderr, flush=True)


def _cli(*args):
    """Run a headscale CLI command. Returns (ok, output)."""
    try:
        r = subprocess.run(["headscale", *args], capture_output=True, text=True,
                           timeout=CLI_TIMEOUT_S, env={**os.environ, "HEADSCALE_CLI_TIMEOUT": "10s"})
    except subprocess.TimeoutExpired:
        return False, "headscale CLI timed out"
    except Exception as e:
        return False, f"failed to run headscale CLI: {e}"
    return r.returncode == 0, (r.stdout if r.returncode == 0 else (r.stderr or r.stdout))


def _watchdog():
    pid = int(os.environ.get("HEADSCALE_PID") or 0)
    failures = 0
    while True:
        time.sleep(WATCH_EVERY_S)
        ok, out = _cli("users", "list", "--output", "json")
        if ok:
            failures = 0
            continue
        failures += 1
        _log(f"admin socket check failed ({failures}/{WATCH_FAILURES}): {out.strip()[-200:]}")
        if failures >= WATCH_FAILURES and pid:
            _log(f"headscale's admin socket isn't answering; stopping headscale (pid {pid}) so the container restarts")
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception as e:
                _log(f"could not stop headscale: {e}")
            return


def _read_api_key():
    try:
        with open(API_KEY_FILE) as f:
            key = f.read().strip()
        return key or None
    except Exception:
        return None


def _extract_json(raw: str):
    """Find and parse the first JSON array/object in stdout, tolerating
    any stray banner text before it (see module docstring)."""
    m = re.search(r"[\[{]", raw)
    if not m:
        raise ValueError("no JSON found in headscale CLI output")
    return json.loads(raw[m.start():])


class Handler(http.server.BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/nodes":
            self._send_json(404, {"error": "not found"})
            return

        expected_key = _read_api_key()
        auth = self.headers.get("Authorization", "")
        if not expected_key or auth != f"Bearer {expected_key}":
            self._send_json(401, {"error": "unauthorized"})
            return

        ok, out = _cli("nodes", "list", "--output", "json")
        if not ok:
            if "deadline exceeded" in out or "timed out" in out:
                out = ("headscale isn't answering its admin socket; it restarts itself within "
                       f"{WATCH_EVERY_S * WATCH_FAILURES // 60} minutes ({out.strip()[-120:]})")
            self._send_json(503, {"error": out[:500]})
            return

        try:
            nodes = _extract_json(out)
        except Exception as e:
            self._send_json(500, {"error": f"could not parse headscale CLI output: {e}"})
            return

        self._send_json(200, {"nodes": nodes})

    def log_message(self, format, *args):
        # Keep this container's own logs focused on headscale itself,
        # not every poll from Global Admin's Network tab.
        pass


if __name__ == "__main__":
    threading.Thread(target=_watchdog, daemon=True, name="watchdog").start()
    # Threaded, so one slow CLI call doesn't hold up the next request.
    server = http.server.ThreadingHTTPServer(LISTEN_ADDR, Handler)
    server.serve_forever()
