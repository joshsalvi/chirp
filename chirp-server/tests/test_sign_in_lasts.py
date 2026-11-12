"""Sign-ins last 30 days and renew while in use."""
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_renew_gives_thirty_days():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import auth
    from app.database import SessionLocal, get_db, init_db
    from app.models import User
    init_db()
    db = SessionLocal()
    name = f"renew{uuid.uuid4().hex[:6]}"
    db.add(User(username=name, hashed_pw="x", role="viewer", active=True)); db.commit(); db.close()
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1/auth")
    c = TestClient(app)
    old = auth.create_access_token({"sub": name, "role": "viewer"}, expires_minutes=60)
    r = c.post("/api/v1/auth/me/renew", headers={"Authorization": "Bearer " + old})
    assert r.status_code == 200
    p = auth.verify_token(r.json()["access_token"])
    assert p["sub"] == name and abs(p["exp"] - (time.time() + auth.REMEMBER_DAYS * 86400)) < 120
    lite = auth.create_access_token({"sub": name, "scope": "lite"}, expires_minutes=60)
    assert c.post("/api/v1/auth/me/renew", headers={"Authorization": "Bearer " + lite}).status_code == 401
