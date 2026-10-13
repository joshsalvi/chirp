#!/usr/bin/env python3
"""
Chirp iOS re-sign service (optional; compose profile "ios-resign").

Apps signed with a free Apple ID stop opening after 7 days. This keeps
Chirp working on your iPhones without the Mac: every few minutes it lists
the iPhones netmuxd can see on the network, and re-signs and reinstalls
build/App.ipa (copied here from the Mac's build-ios.sh) on any that are
due, using AltServer-Linux and the anisette container for Apple sign-in.

When Apple asks for a two-factor code, the service waits for one: it asks
Chirp to email the admin a link to this page (port 8099), where the code is
typed in. The page also shows each phone's status and has a Re-sign now
button.

Environment (see README.md):
  APPLE_ID, APPLE_PASSWORD        the Apple ID the app is signed with
  RESIGN_EVERY_DAYS (5)           re-sign when this long since the last one
  RESIGN_POLL_MINUTES (5)         how often to look for phones
  RESIGN_DEVICES ("")             comma list of names or UDIDs; empty = all
  RESIGN_IPA (/ipa/App.ipa)
  RESIGN_CODE_WAIT_MINUTES (15)   how long to wait for a 2FA code
  RESIGN_PORT (8099), RESIGN_WEB_TOKEN ("")  page port; token required if set
  ALTSERVER_ANISETTE_SERVER (http://127.0.0.1:6969)
  CHIRP_URL, CHIRP_DEVICE_API_KEY  where to report events (emails the admin)
"""
import html
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DATA = os.environ.get("RESIGN_DATA", "/data")
STATE_PATH = os.path.join(DATA, "state.json")
IPA = os.environ.get("RESIGN_IPA", "/ipa/App.ipa")
APPLE_ID = os.environ.get("APPLE_ID", "")
APPLE_PASSWORD = os.environ.get("APPLE_PASSWORD", "")
EVERY_DAYS = min(6.5, max(0.5, float(os.environ.get("RESIGN_EVERY_DAYS", "5") or 5)))   # a free profile lasts 7 days
POLL_MIN = float(os.environ.get("RESIGN_POLL_MINUTES", "5") or 5)
DEVICES = {d.strip().lower() for d in os.environ.get("RESIGN_DEVICES", "").split(",") if d.strip()}
CODE_WAIT_MIN = float(os.environ.get("RESIGN_CODE_WAIT_MINUTES", "15") or 15)
PORT = int(os.environ.get("RESIGN_PORT", "8099") or 8099)
WEB_TOKEN = os.environ.get("RESIGN_WEB_TOKEN", "")
ALTSERVER = os.environ.get("ALTSERVER_BIN", "/usr/local/bin/AltServer")
NETMUXD = os.environ.get("NETMUXD_BIN", "/usr/local/bin/netmuxd")
CHIRP_URL = os.environ.get("CHIRP_URL", "").rstrip("/")
CHIRP_KEY = os.environ.get("CHIRP_DEVICE_API_KEY", "")
PUBLIC_URL = os.environ.get("RESIGN_PUBLIC_URL", "")      # link put in emails
SIGN_TIMEOUT_S = 20 * 60
# AltServer signs a free-account app as <bundle id>.<team id>. The Mac
# (build-ios.sh, shared signing) builds under that ID too, so both install
# the same app; the IPA's ID is set back to the plain one before AltServer
# adds the team ID again.
BUNDLE_ID = os.environ.get("RESIGN_BUNDLE_ID", "")
_TEAM_SUFFIX = re.compile(r"^(.+)\.[A-Z0-9]{10}$")
# Phones reached by IP instead of LAN discovery (mDNS doesn't cross a VPN):
# "UDID=100.64.0.7,UDID2=100.64.0.8", typically their Tailscale addresses.
EXTRA_DEVICES = dict(
    tuple(x.strip() for x in item.split("=", 1))
    for item in os.environ.get("RESIGN_EXTRA_DEVICES", "").split(",") if "=" in item)

TWOFA_RE = re.compile(r"(verification code|two[- ]factor|2fa|enter (the )?code)", re.I)
FAIL_RE = re.compile(r"(error|failed|exception|could not)", re.I)
SUCCESS_RE = re.compile(r"(Installation Succeeded|was successfully installed)", re.I)

_lock = threading.Lock()
_code_event = threading.Event()
_code_value = {"code": None}
_wake = threading.Event()
_busy = {"udid": None}


def now():
    return datetime.now(timezone.utc)


def load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {"devices": {}, "log": [], "waiting_for_code": False}


STATE = load_state()


def save_state():
    os.makedirs(DATA, exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(STATE, f, indent=1, default=str)
    os.replace(tmp, STATE_PATH)


def log(msg):
    line = f"{now().strftime('%Y-%m-%d %H:%M:%S')}Z {msg}"
    print(line, flush=True)
    with _lock:
        STATE.setdefault("log", []).append(line)
        STATE["log"] = STATE["log"][-400:]
        save_state()


def report(event, **info):
    """Tell Chirp (it emails the admin). Best effort."""
    if not (CHIRP_URL and CHIRP_KEY):
        return
    body = json.dumps({"event": event, "page": PUBLIC_URL, **info}).encode()
    req = urllib.request.Request(f"{CHIRP_URL}/api/v1/ios-resign/event", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "X-API-Key": CHIRP_KEY})
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:
        print(f"report {event} failed: {e}", flush=True)


# ── devices ────────────────────────────────────────────────────────────────

def add_by_ip(udid: str, ip: str, sock_path: str = "/var/run/usbmuxd") -> bool:
    """Tell netmuxd about a phone at a known IP (its AddDevice extension to
    the usbmuxd protocol), for phones on Tailscale or another VPN."""
    import plistlib
    import socket
    import struct
    body = plistlib.dumps({"MessageType": "AddDevice", "ConnectionType": "Network",
                           "ServiceName": "_apple-mobdev2._tcp.local",
                           "IPAddress": ip, "DeviceID": udid})
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as so:
            so.settimeout(10)
            so.connect(sock_path)
            so.sendall(struct.pack("<IIII", 16 + len(body), 1, 8, 1) + body)
            try:
                so.recv(4096)
            except socket.timeout:
                pass
        return True
    except OSError as e:
        print(f"AddDevice {udid} at {ip} failed: {e}", flush=True)
        return False


def network_devices():
    """{udid: name} for phones netmuxd sees on the network."""
    for udid, ip in EXTRA_DEVICES.items():
        add_by_ip(udid, ip)
    try:
        out = subprocess.run(["idevice_id", "-n"], capture_output=True, text=True, timeout=30).stdout
    except Exception as e:
        log(f"idevice_id failed: {e}")
        return {}
    found = {}
    for udid in {l.strip().split()[0] for l in out.splitlines() if l.strip()}:
        name = udid
        try:
            r = subprocess.run(["ideviceinfo", "-n", "-u", udid, "-k", "DeviceName"],
                               capture_output=True, text=True, timeout=20)
            if r.returncode == 0 and r.stdout.strip():
                name = r.stdout.strip()
        except Exception:
            pass
        found[udid] = name
    return found


def wanted(udid, name):
    return not DEVICES or udid.lower() in DEVICES or name.lower() in DEVICES


def is_due(dev):
    last = dev.get("last_signed")
    if not last:
        return True
    try:
        t = datetime.fromisoformat(last)
    except ValueError:
        return True
    return now() - t >= timedelta(days=EVERY_DAYS)


# ── signing ────────────────────────────────────────────────────────────────

def sign(udid, name):
    if not (APPLE_ID and APPLE_PASSWORD):
        log("APPLE_ID / APPLE_PASSWORD not set; nothing signed")
        return False
    if not os.path.isfile(IPA):
        log(f"No IPA at {IPA}. Copy build/App.ipa from the Mac (./build-ios.sh --archive).")
        return False
    if not os.path.isfile(ALTSERVER):
        log(f"AltServer binary missing at {ALTSERVER}")
        return False
    _busy["udid"] = udid
    log(f"Re-signing Chirp on {name} ({udid})")
    env = dict(os.environ)
    env.setdefault("ALTSERVER_ANISETTE_SERVER", "http://127.0.0.1:6969")
    try:
        ipa = prepare_ipa(IPA)
    except Exception as e:
        log(f"Couldn't read {IPA}: {e}")
        _busy["udid"] = None
        return False
    proc = subprocess.Popen([ALTSERVER, "-u", udid, "-a", APPLE_ID, "-p", APPLE_PASSWORD, ipa],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, env=env, cwd=DATA)
    started = time.time()
    tail = []
    asked = False
    seen_ok = False
    buf = ""
    fd = proc.stdout.fileno()
    import select

    def handle(line):
        nonlocal seen_ok
        if APPLE_PASSWORD and APPLE_PASSWORD in line:
            line = line.replace(APPLE_PASSWORD, "********")
        tail.append(line)
        del tail[:-40]
        print(f"  [AltServer] {line}", flush=True)
        if SUCCESS_RE.search(line):
            seen_ok = True

    try:
        # Read raw chunks: the two-factor prompt has no newline after it.
        while True:
            if time.time() - started > SIGN_TIMEOUT_S:
                log("AltServer took over 20 minutes; stopping it")
                proc.kill()
                break
            r, _, _ = select.select([fd], [], [], 1.0)
            if not r:
                if proc.poll() is not None:
                    break
                continue
            chunk = os.read(fd, 4096).decode(errors="replace")
            if not chunk:
                break
            buf += chunk
            *lines, buf = buf.split("\n")
            for line in lines:
                handle(line.rstrip())
            if not asked and TWOFA_RE.search(buf + "\n".join(lines[-2:])):
                asked = True
                if buf.strip():
                    handle(buf.strip())
                    buf = ""
                code = wait_for_code(name)
                if code is None:
                    log("No two-factor code entered in time; stopping this attempt")
                    proc.kill()
                    break
                proc.stdin.write(code + "\n")
                proc.stdin.flush()
        if buf.strip():
            handle(buf.strip())
        rc = proc.wait(timeout=60)
    except Exception as e:
        rc = -1
        tail.append(str(e))
    finally:
        _busy["udid"] = None
        with _lock:
            STATE["waiting_for_code"] = False
    ok = seen_ok or (rc == 0 and not any(FAIL_RE.search(l) for l in tail[-5:]))
    with _lock:
        dev = STATE["devices"].setdefault(udid, {"name": name})
        dev["last_attempt"] = now().isoformat()
        dev["last_result"] = "ok" if ok else f"failed (exit {rc})"
        if ok:
            dev["last_signed"] = now().isoformat()
            dev["last_error"] = ""
        else:
            dev["last_error"] = next((l for l in reversed(tail) if FAIL_RE.search(l)), tail[-1] if tail else "")
        save_state()
    log(f"{name}: {'signed and installed' if ok else 'failed: ' + dev['last_error']}")
    report("signed" if ok else "failed", device=name, error="" if ok else dev["last_error"])
    return ok


def prepare_ipa(src: str) -> str:
    """The IPA to give AltServer: src, or a copy with the bundle ID set back
    to the plain one (RESIGN_BUNDLE_ID, or the ID minus a team-ID suffix)."""
    import plistlib
    import zipfile
    if not zipfile.is_zipfile(src):
        return src            # AltServer reports what's wrong with it
    os.makedirs(DATA, exist_ok=True)
    with zipfile.ZipFile(src) as z:
        names = [n for n in z.namelist()
                 if re.fullmatch(r"Payload/[^/]+\.app/Info\.plist", n)]
        if not names:
            return src
        info = plistlib.loads(z.read(names[0]))
        cur = info.get("CFBundleIdentifier", "")
        m = _TEAM_SUFFIX.match(cur)
        want = BUNDLE_ID or (m.group(1) if m else cur)
        if not want or want == cur:
            return src
        info["CFBundleIdentifier"] = want
        out = os.path.join(DATA, "App-resign.ipa")
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as w:
            for item in z.infolist():
                data = plistlib.dumps(info, fmt=plistlib.FMT_BINARY) if item.filename == names[0] else z.read(item)
                w.writestr(item, data)
    log(f"Bundle ID {cur} → {want} for AltServer (it adds the team ID back)")
    return out


def wait_for_code(name):
    _code_event.clear()
    _code_value["code"] = None
    with _lock:
        STATE["waiting_for_code"] = True
        STATE["code_requested_at"] = now().isoformat()
        save_state()
    log(f"Apple asked for a two-factor code (signing {name}); enter it on this page")
    report("needs_code", device=name)
    if _code_event.wait(CODE_WAIT_MIN * 60):
        return _code_value["code"]
    return None


def loop():
    time.sleep(10)
    while True:
        try:
            devs = network_devices()
            seen = now().isoformat()
            with _lock:
                for udid, name in devs.items():
                    d = STATE["devices"].setdefault(udid, {"name": name})
                    d["name"], d["last_seen"] = name, seen
                save_state()
            for udid, name in devs.items():
                if not wanted(udid, name):
                    continue
                d = STATE["devices"].get(udid, {})
                if d.get("force") or is_due(d):
                    with _lock:
                        d.pop("force", None)
                    sign(udid, name)
        except Exception as e:
            log(f"loop error: {e}")
        _wake.wait(POLL_MIN * 60)
        _wake.clear()


# ── netmuxd ────────────────────────────────────────────────────────────────

def run_netmuxd():
    while True:
        if not os.path.isfile(NETMUXD):
            log(f"netmuxd missing at {NETMUXD}; phones can't be found")
            return
        log("Starting netmuxd")
        p = subprocess.Popen([NETMUXD], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in p.stdout:
            print(f"  [netmuxd] {line.rstrip()}", flush=True)
        log(f"netmuxd exited ({p.wait()}); restarting in 10 s")
        time.sleep(10)


# ── web page ───────────────────────────────────────────────────────────────

def page(msg=""):
    rows = []
    for udid, d in sorted(STATE.get("devices", {}).items(), key=lambda kv: kv[1].get("name", "")):
        due = "now"
        if d.get("last_signed"):
            nxt = datetime.fromisoformat(d["last_signed"]) + timedelta(days=EVERY_DAYS)
            due = nxt.strftime("%a %b %-d, %H:%M UTC") if nxt > now() else "now"
        busy = " (signing…)" if _busy["udid"] == udid else ""
        rows.append(
            "<tr>"
            f"<td><b>{html.escape(d.get('name', udid))}</b><br><small>{html.escape(udid)}</small></td>"
            f"<td>{html.escape((d.get('last_signed') or 'never')[:16].replace('T', ' '))}</td>"
            f"<td>{html.escape(due)}</td>"
            f"<td>{html.escape(d.get('last_result', '') + busy)}<br><small>{html.escape(d.get('last_error', ''))}</small></td>"
            f"<td><form method=post action='sign'><input type=hidden name=udid value='{html.escape(udid)}'>"
            f"{tokfield()}<button>Re-sign now</button></form></td></tr>")
    code_form = ""
    if STATE.get("waiting_for_code"):
        code_form = (f"<div class=code><b>Apple sent a two-factor code to your devices.</b> Enter it within "
                     f"{CODE_WAIT_MIN:.0f} minutes:<form method=post action='code'>{tokfield()}"
                     "<input name=code inputmode=numeric autocomplete=one-time-code pattern='[0-9]{6}' required "
                     "placeholder='123456'> <button>Send code</button></form></div>")
    problems = []
    if not (APPLE_ID and APPLE_PASSWORD):
        problems.append("APPLE_ID and APPLE_PASSWORD aren't set in the stack's .env.")
    if not os.path.isfile(IPA):
        problems.append(f"No app at {html.escape(IPA)}: copy build/App.ipa from the Mac.")
    lockdown = "/var/lib/lockdown"
    if not (os.path.isdir(lockdown) and any(f.endswith(".plist") and f != "SystemConfiguration.plist"
                                             for f in os.listdir(lockdown))):
        problems.append("No pairing records in /var/lib/lockdown: see README (pair each iPhone once).")
    logs = "\n".join(html.escape(l) for l in STATE.get("log", [])[-60:])
    return f"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Chirp iOS re-sign</title><style>
body{{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;background:#0a160c;color:#e8efe8;margin:0;padding:20px}}
main{{max-width:860px;margin:auto}} table{{width:100%;border-collapse:collapse;margin:12px 0}}
td,th{{text-align:left;padding:8px;border-bottom:1px solid #22382a;vertical-align:top}} small{{color:#9db5a2}}
button{{background:#ea580c;color:#fff;border:0;border-radius:8px;padding:8px 12px;font-weight:600}}
input{{font-size:20px;padding:8px;border-radius:8px;border:1px solid #3a5a42;width:9em;letter-spacing:.2em}}
.code{{background:#3b1d0a;border:1px solid #ea580c;border-radius:12px;padding:14px;margin:12px 0}}
.warn{{background:#2a2410;border-radius:10px;padding:10px 14px;color:#fde68a}} pre{{background:#06100a;padding:12px;border-radius:10px;overflow:auto;font-size:12px;max-height:420px}}
</style></head><body><main>
<h2>Chirp iOS re-sign</h2>
<p><small>Re-signs every {EVERY_DAYS:g} days when a phone is on the network · checks every {POLL_MIN:g} min ·
Apple ID {html.escape(APPLE_ID or 'not set')}</small></p>
{''.join(f'<p class=warn>{p}</p>' for p in problems)}
{f'<p class=warn>{html.escape(msg)}</p>' if msg else ''}
{code_form}
<table><tr><th>iPhone</th><th>Last signed</th><th>Next</th><th>Result</th><th></th></tr>
{''.join(rows) or '<tr><td colspan=5><small>No iPhones seen yet. They need Wi-Fi sync on and a pairing record (README).</small></td></tr>'}
</table><h3>Log</h3><pre>{logs}</pre></main></body></html>"""


def tokfield():
    return f"<input type=hidden name=token value='{html.escape(WEB_TOKEN)}'>" if WEB_TOKEN else ""


class Handler(BaseHTTPRequestHandler):
    def _ok_token(self, params):
        return not WEB_TOKEN or params.get("token", [""])[0] == WEB_TOKEN

    def _send(self, body, status=200, ctype="text/html; charset=utf-8"):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if not self._ok_token(q):
            return self._send("Add ?token=… (RESIGN_WEB_TOKEN)", 403, "text/plain")
        if u.path.rstrip("/") == "/status":
            return self._send(json.dumps(STATE, default=str), ctype="application/json")
        self._send(page())

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        q = urllib.parse.parse_qs(self.rfile.read(n).decode())
        if not self._ok_token(q):
            return self._send("Wrong token", 403, "text/plain")
        path = urllib.parse.urlparse(self.path).path.rstrip("/")
        msg = ""
        if path.endswith("/code"):
            code = re.sub(r"\D", "", q.get("code", [""])[0])
            if len(code) == 6 and STATE.get("waiting_for_code"):
                _code_value["code"] = code
                _code_event.set()
                msg = "Code sent to AltServer."
            else:
                msg = "Enter the 6-digit code while a request is waiting."
        elif path.endswith("/sign"):
            udid = q.get("udid", [""])[0]
            with _lock:
                if udid in STATE.get("devices", {}):
                    STATE["devices"][udid]["force"] = True
                    save_state()
            _wake.set()
            msg = "Re-sign queued; it starts within a few seconds if the phone is on the network."
        self._send(page(msg))

    def log_message(self, *a):
        pass


def main():
    os.makedirs(DATA, exist_ok=True)
    STATE["waiting_for_code"] = False
    save_state()
    threading.Thread(target=run_netmuxd, daemon=True).start()
    threading.Thread(target=loop, daemon=True).start()
    log(f"Re-sign service on port {PORT}; IPA {IPA}; every {EVERY_DAYS:g} days")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


def pair():
    """One-off: pair an iPhone plugged into this server's USB port (see
    README). netmuxd talks to USB directly; the pairing record lands in
    /var/lib/lockdown, which is kept in appdata."""
    p = subprocess.Popen([NETMUXD], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        print("Waiting for an iPhone on USB (unlock it)...", flush=True)
        udid = None
        for _ in range(120):
            out = subprocess.run(["idevice_id", "-l"], capture_output=True, text=True).stdout.split()
            if out:
                udid = out[0]
                break
            time.sleep(1)
        if not udid:
            print("No iPhone found on USB. Is the container started with the USB devices (README)?")
            return 1
        print(f"Found {udid}. Tap Trust on the iPhone and enter its passcode.", flush=True)
        for _ in range(60):
            r = subprocess.run(["idevicepair", "-u", udid, "pair"], capture_output=True, text=True)
            print(r.stdout.strip() or r.stderr.strip(), flush=True)
            if r.returncode == 0:
                v = subprocess.run(["idevicepair", "-u", udid, "validate"], capture_output=True, text=True)
                print(v.stdout.strip(), flush=True)
                print("Paired. Turn on Wi-Fi sync for this phone once (Finder or Xcode on the Mac: "
                      "\"Show this iPhone when on Wi-Fi\") if it isn't already, then unplug it.")
                return 0
            time.sleep(3)
        return 1
    finally:
        p.terminate()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "devices":
        print(json.dumps(network_devices(), indent=1))
    elif cmd == "pair":
        sys.exit(pair())
    else:
        main()
