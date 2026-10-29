"""Apple TV: sign-in by code and what a TV token may reach (api/tv.py)."""
import time

import pytest
from fastapi import HTTPException


class _Req:
    def __init__(self, token=None, ip="10.0.0.9"):
        self.headers = {"Authorization": "Bearer " + token} if token else {}
        self.client = type("C", (), {"host": ip})()


def _phone_token(**extra):
    from app.api.auth import create_access_token
    return create_access_token({"sub": "josh", "global_user_id": "g1", "active_instance_id": "i1",
                                "role": "admin", **extra})


def test_pair_flow_hands_out_a_tv_token_once():
    from app.api import tv
    from app.api.auth import verify_token
    start = tv.pair_start(_Req(ip="10.1.1.1"))
    assert len(start["code"]) == 6 and set(start["code"]) <= set(tv.CODE_ALPHABET)
    assert tv.pair_poll(tv.PollIn(pair_id=start["pair_id"]))["status"] == "pending"
    # lower case and a dash are fine
    code = start["code"][:3].lower() + "-" + start["code"][3:]
    assert tv.pair_approve(tv.ApproveIn(code=code), _Req(_phone_token()))["ok"]
    got = tv.pair_poll(tv.PollIn(pair_id=start["pair_id"]))
    assert got["status"] == "approved" and got["username"] == "josh"
    claims = verify_token(got["access_token"])
    assert claims["scope"] == "tv" and claims["active_instance_id"] == "i1"
    assert claims["exp"] - time.time() > 170 * 86400
    assert tv.pair_poll(tv.PollIn(pair_id=start["pair_id"]))["status"] == "expired"   # only once


def test_approve_needs_a_phone_sign_in_and_a_live_code(monkeypatch):
    from app.api import tv
    # Other tests turn sign-in off for the shared database; this checks the signed-in case.
    monkeypatch.setattr(tv, "_auth_enabled", lambda: True)
    start = tv.pair_start(_Req(ip="10.1.1.2"))
    with pytest.raises(HTTPException) as e:
        tv.pair_approve(tv.ApproveIn(code=start["code"]), _Req())
    assert e.value.status_code == 401
    for scope in ("tv", "watch"):
        with pytest.raises(HTTPException) as e:
            tv.pair_approve(tv.ApproveIn(code=start["code"]), _Req(_phone_token(scope=scope)))
        assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:
        tv.pair_approve(tv.ApproveIn(code="ZZZZZ2"), _Req(_phone_token()))
    assert e.value.status_code in (400, 404)


def test_pair_start_is_rate_limited_per_address():
    from app.api import tv
    for _ in range(tv._START_PER_IP):
        tv.pair_start(_Req(ip="10.9.9.9"))
    with pytest.raises(HTTPException) as e:
        tv.pair_start(_Req(ip="10.9.9.9"))
    assert e.value.status_code == 429


def test_tv_token_paths():
    from app.main import tv_may_use as ok, UNPROTECTED
    for m, p in [("GET", "/api/v1/tv/recent"), ("GET", "/api/v1/tv/stations"), ("GET", "/api/v1/tv/listen/d-1"),
                 ("GET", "/api/v1/recordings/statistics/digest"), ("GET", "/api/v1/recordings/statistics/daily-journal"),
                 ("GET", "/api/v1/watch/audio/ab-12"), ("GET", "/api/v1/recordings/ab-12"),
                 ("GET", "/api/v1/auth/me"), ("POST", "/api/v1/live-detect/analyze")]:
        assert ok(m, p), (m, p)
    for m, p in [("DELETE", "/api/v1/recordings/ab-12"), ("POST", "/api/v1/tv/pair/approve"),
                 ("GET", "/api/v1/settings"), ("GET", "/api/v1/users"), ("POST", "/api/v1/auth/watch-token"),
                 ("GET", "/api/v1/tv/listen/../x"), ("PATCH", "/api/v1/recordings/ab-12")]:
        assert not ok(m, p), (m, p)
    assert "/api/v1/tv/pair/start" in UNPROTECTED and "/api/v1/tv/pair/poll" in UNPROTECTED
    assert "/api/v1/tv/pair/approve" not in UNPROTECTED


def test_bird_mic_choice_matches_live_detect():
    from app.api.tv import pick_bird_mic
    assert pick_bird_mic(["AudioMoth 384kHz", "USB Mic", "ReSpeaker XVF3800"]) == "ReSpeaker XVF3800"
    assert pick_bird_mic(["AudioMoth", "USB Mic"]) == "USB Mic"
    assert pick_bird_mic(["AudioMoth"]) is None and pick_bird_mic(None) is None


def test_tv_recent_and_stations(client):
    r = client.get("/api/v1/tv/recent?limit=3")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) <= 3
    for x in rows:
        assert {"id", "species", "time", "photo_url", "has_audio"} <= set(x)
    s = client.get("/api/v1/tv/stations")
    assert s.status_code == 200 and isinstance(s.json(), list)
    assert client.get("/api/v1/tv/listen/no-such-station").status_code == 404
