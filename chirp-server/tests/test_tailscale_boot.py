"""Server startup must not wait on the Tailscale/Headscale control server."""
import threading

from app.services import tailscale_manager as tm


def test_reconfigure_without_wait_does_not_connect_inline(monkeypatch):
    calls = []
    mgr = tm.TailscaleManager.__new__(tm.TailscaleManager)
    mgr._thread = None
    mgr._stop_event = threading.Event()
    mgr._cached_ip = None
    mgr._daemon_proc = None
    monkeypatch.setattr(mgr, "stop", lambda: None, raising=False)
    monkeypatch.setattr(mgr, "status", lambda: {"ok": True}, raising=False)
    monkeypatch.setattr(mgr, "_ensure_up", lambda *a, **k: calls.append("up"), raising=False)
    monkeypatch.setattr(mgr, "_refresh_ip", lambda *a, **k: calls.append("ip"), raising=False)
    started = []
    monkeypatch.setattr(tm.threading, "Thread", lambda *a, **k: type("T", (), {"start": lambda self: started.append(1)})())
    monkeypatch.setattr(tm.shutil, "which", lambda name: "/usr/bin/tailscale")

    mgr.reconfigure(enabled=True, auth_key="k", login_server="https://hs.example", wait=False)
    assert calls == []          # nothing ran in the caller's thread
    assert started == [1]       # the background loop was started

    mgr.reconfigure(enabled=True, auth_key="k", login_server="https://hs.example")
    assert calls == ["up", "ip"]  # Save & Connect still answers with the result
