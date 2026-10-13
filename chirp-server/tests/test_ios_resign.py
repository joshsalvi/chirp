"""0.5.10.m: optional iOS re-sign service (ios-resign/) and Chirp's event endpoint."""
import importlib.util
import os
import stat
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
T = os.environ["CHIRP_DATA_DIR"]


import pytest

RESIGN_PY = os.path.join(HERE, "..", "ios-resign", "resign.py")
needs_service = pytest.mark.skipif(not os.path.exists(RESIGN_PY),
                                   reason="ios-resign/ ships with chirp-server-instances only")


def load_resign(tmp, **env):
    os.environ.update({"RESIGN_DATA": os.path.join(tmp, "rs"), "APPLE_ID": "a@b.org",
                       "APPLE_PASSWORD": "pw-secret", "RESIGN_IPA": os.path.join(tmp, "App.ipa"),
                       "RESIGN_CODE_WAIT_MINUTES": "0.05", **env})
    spec = importlib.util.spec_from_file_location("resign", RESIGN_PY)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def fake_altserver(tmp, needs_code=True, rc=0):
    p = os.path.join(tmp, "AltServer")
    with open(p, "w") as f:
        f.write(f"""#!/usr/bin/env python3
import sys
print("Signing with " + " ".join(sys.argv[1:]), flush=True)
if {needs_code}:
    print("Enter two factor code: ", end="", flush=True)
    code = sys.stdin.readline().strip()
    print("got code " + code, flush=True)
    if code != "123456":
        print("error: wrong code", flush=True); sys.exit(3)
print("Installation Succeeded" if {rc} == 0 else "error: install failed", flush=True)
sys.exit({rc})
""")
    os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
    return p


@needs_service
def test_sign_with_two_factor_code():
    tmp = os.path.join(T, "resign1")
    os.makedirs(tmp, exist_ok=True)
    open(os.path.join(tmp, "App.ipa"), "wb").write(b"ipa")
    m = load_resign(tmp, ALTSERVER_BIN=fake_altserver(tmp))
    m.report = lambda *a, **k: None

    def give_code():
        for _ in range(100):
            if m.STATE.get("waiting_for_code"):
                m._code_value["code"] = "123456"
                m._code_event.set()
                return
            time.sleep(0.05)
    threading.Thread(target=give_code).start()
    assert m.sign("UDID-1", "Josh's iPhone")
    d = m.STATE["devices"]["UDID-1"]
    assert d["last_result"] == "ok" and d["last_signed"]
    assert not m.is_due(d)
    assert "pw-secret" not in "".join(m.STATE["log"])
    assert "Josh&#x27;s iPhone" in m.page()


@needs_service
def test_sign_times_out_without_code_and_reports():
    tmp = os.path.join(T, "resign2")
    os.makedirs(tmp, exist_ok=True)
    open(os.path.join(tmp, "App.ipa"), "wb").write(b"ipa")
    m = load_resign(tmp, ALTSERVER_BIN=fake_altserver(tmp))
    events = []
    m.report = lambda e, **k: events.append(e)
    assert not m.sign("UDID-2", "iPad")
    assert events == ["needs_code", "failed"]
    assert m.is_due(m.STATE["devices"]["UDID-2"])


@needs_service
def test_device_filter():
    tmp = os.path.join(T, "resign3")
    m = load_resign(tmp, RESIGN_DEVICES="Josh's iPhone, abc-udid")
    assert m.wanted("x", "josh's iphone") and m.wanted("ABC-UDID", "Other") and not m.wanted("y", "iPad")


def test_event_endpoint(client, monkeypatch):
    from app.config import settings
    r = client.post("/api/v1/ios-resign/event", json={"event": "needs_code", "device": "iPhone"})
    assert r.status_code == 401
    from app.services import email_service as es
    sent = []
    monkeypatch.setattr(es, "_get_smtp_config", lambda db: {"admin_email": "admin@x.org"})
    monkeypatch.setattr(es, "_send", lambda cfg, to, subj, html, **k: sent.append((to, subj, html)) or True)
    h = {"X-API-Key": settings.device_api_key}
    r = client.post("/api/v1/ios-resign/event", headers=h,
                    json={"event": "needs_code", "device": "iPhone", "page": "http://unraid:8099/"})
    assert r.status_code == 200, r.text
    assert r.json()["emailed"] == 1 and "code" in sent[0][1] and "http://unraid:8099/" in sent[0][2]
    r = client.post("/api/v1/ios-resign/event", headers=h, json={"event": "needs_code", "device": "iPhone"})
    assert r.json().get("throttled")
    r = client.post("/api/v1/ios-resign/event", headers=h, json={"event": "signed", "device": "iPhone"})
    assert r.json()["emailed"] == 0


@needs_service
def test_prepare_ipa_strips_team_suffix():
    import plistlib
    import zipfile
    tmp = os.path.join(T, "resign4")
    os.makedirs(tmp, exist_ok=True)
    ipa = os.path.join(tmp, "App.ipa")
    with zipfile.ZipFile(ipa, "w") as z:
        z.writestr("Payload/App.app/Info.plist",
                   plistlib.dumps({"CFBundleIdentifier": "com.joshuasalvimd.chirp.AB12CD34EF"}))
        z.writestr("Payload/App.app/App", b"binary")
    m = load_resign(tmp)
    out = m.prepare_ipa(ipa)
    assert out != ipa
    with zipfile.ZipFile(out) as z:
        assert plistlib.loads(z.read("Payload/App.app/Info.plist"))["CFBundleIdentifier"] == "com.joshuasalvimd.chirp"
        assert z.read("Payload/App.app/App") == b"binary"
    # already plain: used as is
    with zipfile.ZipFile(ipa, "w") as z:
        z.writestr("Payload/App.app/Info.plist", plistlib.dumps({"CFBundleIdentifier": "com.joshuasalvimd.chirp"}))
    assert m.prepare_ipa(ipa) == ipa


@needs_service
def test_cloudflare_setup_calls(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "cfsetup", os.path.join(HERE, "..", "ios-resign", "cloudflare_setup.py"))
    cs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cs)
    calls = []

    def fake(self, method, path, body=None):
        calls.append((method, path, body))
        if path.endswith("cfd_tunnel?name=chirp-ios-resign&is_deleted=false"):
            return []
        if method == "POST" and path.endswith("/cfd_tunnel"):
            return {"id": "tid-1"}
        if path.endswith("/token"):
            return "TOKEN123"
        if "dns_records?name=" in path or path.endswith("/access/apps"):
            return []
        return {}
    monkeypatch.setattr(cs.CF, "call", fake)
    monkeypatch.setenv("CF_API_TOKEN", "x")
    monkeypatch.setattr(sys, "argv", ["x", "--account", "A", "--zone", "Z", "--email", "j@x.org"])
    cs.main()
    paths = [(m, p) for m, p, _ in calls]
    assert ("PUT", "/accounts/A/cfd_tunnel/tid-1/configurations") in paths
    dns = next(b for m, p, b in calls if m == "POST" and p == "/zones/Z/dns_records")
    assert dns["content"] == "tid-1.cfargotunnel.com" and dns["proxied"]
    app = next(b for m, p, b in calls if m == "POST" and p == "/accounts/A/access/apps")
    assert app["domain"] == "iosresign.ourchirp.com"
    assert app["policies"][0]["include"] == [{"email": {"email": "j@x.org"}}]


@needs_service
def test_add_by_ip_packet(tmp_path):
    import plistlib
    import socket
    import struct
    sock = str(tmp_path / "mux")
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock)
    srv.listen(1)
    got = {}

    def serve():
        c, _ = srv.accept()
        hdr = c.recv(16)
        n, ver, msg, tag = struct.unpack("<IIII", hdr)
        body = b""
        while len(body) < n - 16:
            body += c.recv(4096)
        got["msg"] = (ver, msg, plistlib.loads(body))
        c.sendall(b"ok")
        c.close()
    th = threading.Thread(target=serve)
    th.start()
    m = load_resign(str(tmp_path), RESIGN_EXTRA_DEVICES="UDID-A=100.64.0.7")
    assert m.EXTRA_DEVICES == {"UDID-A": "100.64.0.7"}
    assert m.add_by_ip("UDID-A", "100.64.0.7", sock)
    th.join(5)
    ver, msg, pl = got["msg"]
    assert (ver, msg) == (1, 8) and pl["MessageType"] == "AddDevice"
    assert pl["IPAddress"] == "100.64.0.7" and pl["DeviceID"] == "UDID-A"
