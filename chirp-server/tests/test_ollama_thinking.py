"""
Ollama: a thinking model that spends its whole answer on reasoning gets
asked again with thinking off; every request carries num_ctx.

    python3 -m pytest -q tests/test_ollama_thinking.py
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services import ai_providers  # noqa: E402

CFG = json.dumps({"base_url": "http://ollama:11434", "model": "gemma4:12b"})


class _Resp:
    status_code = 200
    text = ""

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


def _fake_post(answers, calls):
    def post(url, json=None, timeout=None, headers=None):
        calls.append(json)
        return _Resp(answers.pop(0))
    return post


def test_vision_asks_without_thinking(monkeypatch):
    """AI Second Opinion asks for a direct answer (0.5.10.m): reasoning was
    most of the wait."""
    calls = []
    answers = [{"message": {"content": "CONSISTENT\n\n**Blue Jay** (likelihood 80%) ok.\n\n**Overall:** fine."}}]
    monkeypatch.setattr(ai_providers.httpx, "post", _fake_post(answers, calls))
    out = ai_providers.call_vision_completion("ollama", CFG, "sys", "user", b"png", "image/png")
    assert out.startswith("CONSISTENT")
    assert len(calls) == 1 and calls[0]["think"] is False
    assert calls[0]["options"]["num_ctx"] == ai_providers.OLLAMA_NUM_CTX


def test_vision_retries_without_thinking_when_allowed(monkeypatch):
    calls = []
    answers = [{"message": {"content": "", "thinking": "hmm " * 500}},
               {"message": {"content": "CONSISTENT\n\n**Blue Jay** (likelihood 80%) ok.\n\n**Overall:** fine."}}]
    monkeypatch.setattr(ai_providers, "OLLAMA_VISION_THINK", True)
    monkeypatch.setattr(ai_providers.httpx, "post", _fake_post(answers, calls))
    out = ai_providers.call_vision_completion("ollama", CFG, "sys", "user", b"png", "image/png")
    assert out.startswith("CONSISTENT")
    assert len(calls) == 2 and "think" not in calls[0] and calls[1]["think"] is False
    assert all(c["options"]["num_ctx"] == ai_providers.OLLAMA_NUM_CTX for c in calls)


def test_vision_old_ollama_without_think_option(monkeypatch):
    calls = []

    class _Bad(_Resp):
        status_code = 400
        text = 'json: unknown field "think"'

    seq = [_Bad({}), _Resp({"message": {"content": "UNCERTAIN\n\n**Overall:** can't tell."}})]

    def post(url, json=None, timeout=None, headers=None):
        calls.append(dict(json))
        return seq.pop(0)
    monkeypatch.setattr(ai_providers.httpx, "post", post)
    out = ai_providers.call_vision_completion("ollama", CFG, "sys", "user", b"png", "image/png")
    assert out.startswith("UNCERTAIN") and len(calls) == 2 and "think" not in calls[1]


def test_warm_ollama(monkeypatch):
    class _Ps(_Resp):
        pass
    monkeypatch.setattr(ai_providers.httpx, "get",
                        lambda url, timeout=None, headers=None: _Ps({"models": [{"name": "gemma4:12b"}]}))
    assert ai_providers.warm_ollama(json.loads(CFG)) == "loaded"
    posted = []
    monkeypatch.setattr(ai_providers.httpx, "get", lambda url, timeout=None, headers=None: _Ps({"models": []}))
    monkeypatch.setattr(ai_providers.httpx, "post", lambda url, json=None, timeout=None, headers=None: posted.append(json))
    assert ai_providers.warm_ollama(json.loads(CFG)) == "loading"
    import time
    for _ in range(50):
        if posted:
            break
        time.sleep(0.01)
    assert posted and posted[0]["model"] == "gemma4:12b" and "prompt" not in posted[0]


def test_chat_retries_then_explains(monkeypatch):
    calls = []
    answers = [{"message": {"content": "", "thinking": "x"}}, {"message": {"content": "", "thinking": "y"}}]
    monkeypatch.setattr(ai_providers.httpx, "post", _fake_post(answers, calls))
    with pytest.raises(RuntimeError, match="non-thinking model"):
        ai_providers.call_chat_completion("ollama", CFG, "sys", "user")
    assert len(calls) == 2


def test_no_retry_when_answered(monkeypatch):
    calls = []
    monkeypatch.setattr(ai_providers.httpx, "post",
                        _fake_post([{"message": {"content": "hello", "thinking": "x"}}], calls))
    assert ai_providers.call_chat_completion("ollama", CFG, "sys", "user") == "hello"
    assert len(calls) == 1
