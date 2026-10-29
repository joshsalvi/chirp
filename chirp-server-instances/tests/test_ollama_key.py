"""
Optional Ollama API key: sent as a Bearer token on every Ollama request when
set, never otherwise; masked in settings; kept out of URLs.

    python3 -m pytest -q tests/test_ollama_key.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services import ai_providers  # noqa: E402


class _Resp:
    status_code = 200
    text = ""

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body

    def raise_for_status(self):
        pass


def test_headers_only_with_a_key():
    assert ai_providers.ollama_headers({"base_url": "x"}) == {}
    assert ai_providers.ollama_headers({"api_key": "  "}) == {}
    assert ai_providers.ollama_headers({"api_key": "k1"}) == {"Authorization": "Bearer k1"}
    assert ai_providers.ollama_headers("k2") == {"Authorization": "Bearer k2"}
    assert ai_providers.ollama_headers(None) == {}


def test_chat_and_tags_send_the_key(monkeypatch):
    seen = []
    monkeypatch.setattr(ai_providers.httpx, "post",
                        lambda url, json=None, timeout=None, headers=None: seen.append(headers) or _Resp({"message": {"content": "Fine."}}))
    monkeypatch.setattr(ai_providers.httpx, "get",
                        lambda url, timeout=None, headers=None: seen.append(headers) or _Resp({"models": [{"name": "m:latest"}]}))
    cfg = json.dumps({"base_url": "http://o", "model": "m", "api_key": "secret"})
    ai_providers.call_chat_completion("ollama", cfg, "sys", "user")
    ai_providers.test_provider_key("ollama", cfg)
    assert seen and all(h == {"Authorization": "Bearer secret"} for h in seen)

    seen.clear()
    ai_providers.call_chat_completion("ollama", json.dumps({"base_url": "http://o", "model": "m"}), "sys", "user")
    assert seen == [{}]


def test_settings_mask_save_and_feature_config(client, monkeypatch):
    from app.database import SessionLocal
    from app.models import AppSettings
    r = client.put("/api/v1/settings", json={"ollama_base_url": "http://o:11435", "ollama_model": "m",
                                             "ollama_api_key": "0123456789abcdef"})
    assert r.status_code == 200 and r.json()["ollama_api_key"] == "0123****cdef"
    assert client.get("/api/v1/settings").json()["ollama_api_key"] == "0123****cdef"
    # A masked value sent back leaves the key alone.
    client.put("/api/v1/settings", json={"ollama_api_key": "0123****cdef"})
    db = SessionLocal()
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    assert s.ollama_api_key == "0123456789abcdef"
    s.ai_feature_providers = {**(s.ai_feature_providers or {}), "daily_summary": "ollama"}
    db.commit()
    prov, cred = ai_providers.get_feature_config("daily_summary", db)
    assert prov == "ollama" and json.loads(cred)["api_key"] == "0123456789abcdef"
    db.close()

    # Models list: saved key, then an unsaved one typed into the form (body, not URL).
    from app.api import app_settings
    seen = []
    monkeypatch.setattr(app_settings.httpx, "get",
                        lambda url, headers=None, timeout=None: seen.append((url, headers)) or _Resp({"models": [{"name": "m"}]}))
    assert client.post("/api/v1/settings/ai/ollama/models", json={}).json()["models"][0]["name"] == "m"
    assert client.post("/api/v1/settings/ai/ollama/models", json={"api_key": "typed"}).status_code == 200
    assert client.get("/api/v1/settings/ai/ollama/models").status_code == 200
    assert seen[0] == ("http://o:11435/api/tags", {"Authorization": "Bearer 0123456789abcdef"})
    assert seen[1][1] == {"Authorization": "Bearer typed"} and "typed" not in seen[1][0]
    assert seen[2][1] == {"Authorization": "Bearer 0123456789abcdef"}

    # Clearing it: an empty string removes the key; requests then go without one.
    client.put("/api/v1/settings", json={"ollama_api_key": ""})
    assert not client.get("/api/v1/settings").json()["ollama_api_key"]
    seen.clear()
    client.post("/api/v1/settings/ai/ollama/models", json={})
    assert seen[0][1] == {}
