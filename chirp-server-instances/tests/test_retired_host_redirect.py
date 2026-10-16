"""Retired hostnames redirect to the new address; API calls get 410."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_retired_host_redirect(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    monkeypatch.setattr(main, "_REDIRECT_HOSTS", {"old.example.com"})
    monkeypatch.setattr(main, "_REDIRECT_TO", "https://new.example.com")
    c = TestClient(main.app, follow_redirects=False)
    old = {"host": "old.example.com"}

    r = c.get("/recordings/abc?x=1", headers=old)
    assert r.status_code == 301 and r.headers["location"] == "https://new.example.com/recordings/abc?x=1"
    r = c.post("/api/v1/recordings/upload", headers=old)
    assert r.status_code == 410 and r.json()["moved_to"] == "https://new.example.com"
    r = c.get("/api/v1/health", headers={"host": "old.example.com:443"})
    assert r.status_code == 301
    # other hostnames (the LAN address) are untouched
    assert c.get("/api/v1/health", headers={"host": "192.168.1.224:8765"}).status_code == 200


def test_off_when_unset(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    monkeypatch.setattr(main, "_REDIRECT_HOSTS", set())
    c = TestClient(main.app, follow_redirects=False)
    assert c.get("/api/v1/health", headers={"host": "old.example.com"}).status_code == 200
