"""0.5.12.z: Apple Watch sign-in only runs Live Detect and can't mint another."""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_watch_paths():
    from app.main import watch_may_use as ok
    assert ok("/api/v1/live-detect/analyze")
    assert ok("/api/v1/auth/me")
    for p in ["/api/v1/recordings", "/api/v1/live-detect/save-session", "/api/v1/auth/watch-token",
              "/api/v1/settings", "/api/v1/auth/me/profile", "/api/v1/live-detect/analyze/x"]:
        assert not ok(p), p


def test_watch_token_claims():
    from fastapi import HTTPException
    from app.api.auth import create_access_token, verify_token, watch_token
    user = object()  # any signed-in user
    phone = create_access_token({"sub": "josh", "global_user_id": "g1", "active_instance_id": "i1",
                                 "role": "admin", "extra": 1})
    out = watch_token(token=phone, current_user=user)
    claims = verify_token(out["access_token"])
    assert claims["scope"] == "watch" and claims["sub"] == "josh"
    assert claims["active_instance_id"] == "i1" and "extra" not in claims
    assert claims["exp"] - time.time() > 29 * 86400
    with pytest.raises(HTTPException) as e:
        watch_token(token=out["access_token"], current_user=user)
    assert e.value.status_code == 403
    assert watch_token(token=None, current_user=None)["access_token"] is None
