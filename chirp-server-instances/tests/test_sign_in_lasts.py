"""Sign-ins last 30 days and renew while in use; switching location keeps
what's left of the sign-in."""
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _app():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import auth
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1/auth")
    return TestClient(app)


def _user(active=True):
    from app.registry_db import RegistrySessionLocal, init_registry_db
    from app.registry_models import GlobalUser
    init_registry_db()
    reg = RegistrySessionLocal()
    u = GlobalUser(id=f"r-{uuid.uuid4().hex[:8]}", username=f"renew{uuid.uuid4().hex[:6]}", hashed_pw="x", active=active)
    reg.add(u); reg.commit(); reg.refresh(u); reg.expunge(u); reg.close()
    return u


def test_renew_gives_thirty_days():
    from app.api.auth import REMEMBER_DAYS, create_access_token, verify_token
    u = _user()
    old = create_access_token({"sub": u.username, "global_user_id": u.id, "active_instance_id": "i1"}, expires_minutes=60)
    r = _app().post("/api/v1/auth/me/renew", headers={"Authorization": "Bearer " + old})
    assert r.status_code == 200
    p = verify_token(r.json()["access_token"])
    assert p["active_instance_id"] == "i1" and p["sub"] == u.username
    assert abs(p["exp"] - (time.time() + REMEMBER_DAYS * 86400)) < 120


def test_renew_refuses_scoped_and_inactive():
    from app.api.auth import create_access_token
    u, off = _user(), _user(active=False)
    c = _app()
    for claims in ({"sub": u.username, "global_user_id": u.id, "scope": "lite"},
                   {"sub": u.username, "global_user_id": u.id, "scope": "demo"},
                   {"sub": off.username, "global_user_id": off.id}):
        t = create_access_token(claims, expires_minutes=60)
        assert c.post("/api/v1/auth/me/renew", headers={"Authorization": "Bearer " + t}).status_code == 401
    assert c.post("/api/v1/auth/me/renew").status_code == 401


def test_switching_keeps_the_sign_in():
    from types import SimpleNamespace
    from app.api.auth import SESSION_MINUTES, carried_minutes, create_access_token
    req = lambda t: SimpleNamespace(headers={"Authorization": "Bearer " + t})  # noqa: E731
    long = create_access_token({"sub": "x"}, expires_minutes=20 * 1440)
    assert abs(carried_minutes(req(long)) - 20 * 1440) <= 2
    short = create_access_token({"sub": "x"}, expires_minutes=30)
    assert carried_minutes(req(short)) == SESSION_MINUTES
    assert carried_minutes(None) == SESSION_MINUTES
