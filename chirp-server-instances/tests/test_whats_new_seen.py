"""0.5.16.s: the What's New version a user dismissed never goes backwards,
so an older copy of the app can't bring a newer popup back."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_version_key_order():
    from app.api.auth import _version_key as k
    assert k("0.5.16.r") > k("0.5.16.q") > k("0.5.16.b") > k("0.5.15.z")
    assert k("0.5.16.aa") > k("0.5.16.z")
    assert k("0.5.17") > k("0.5.16.zz")
    assert k("garbage") < k("0.0.0.a")


def test_seen_version_never_goes_backwards():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import auth
    from app.database import SessionLocal, init_db
    from app.models import User
    init_db()
    db = SessionLocal()
    db.query(User).filter(User.username == "wn-test").delete()
    db.add(User(username="wn-test", hashed_pw="x", role="viewer"))
    db.commit(); db.close()
    app = FastAPI(); app.include_router(auth.router, prefix="/api/v1/auth")
    c = TestClient(app)
    h = {"Authorization": "Bearer " + auth.create_access_token({"sub": "wn-test"})}

    def seen():
        s = SessionLocal()
        try:
            return s.query(User).filter(User.username == "wn-test").first().last_seen_whats_new_version
        finally:
            s.close()
    try:
        for sent, want in [("0.5.16.q", "0.5.16.q"), ("0.5.16.r", "0.5.16.r"),
                           ("0.5.16.n", "0.5.16.r"), ("0.5.16.r", "0.5.16.r"), ("0.5.17.a", "0.5.17.a")]:
            assert c.put("/api/v1/auth/me/profile", json={"last_seen_whats_new_version": sent}, headers=h).status_code == 200
            assert seen() == want, (sent, seen())
    finally:
        db = SessionLocal(); db.query(User).filter(User.username == "wn-test").delete(); db.commit(); db.close()
