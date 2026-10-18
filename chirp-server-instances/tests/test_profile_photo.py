"""Uploaded profile photos are served at /auth/me/photo/{user id}{.ext}."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_profile_photo_served(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import auth
    from app.config import settings as cfg
    monkeypatch.setattr(cfg, "data_dir", str(tmp_path))
    os.makedirs(tmp_path / "user_photos")
    uid = "eb79b771-c42f-46dd-ab90-1e1022cb5644"
    (tmp_path / "user_photos" / f"{uid}_photo.jpeg").write_bytes(b"\xff\xd8\xffjpeg")
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1/auth")
    c = TestClient(app)
    r = c.get(f"/api/v1/auth/me/photo/{uid}.jpeg?v=1")
    assert r.status_code == 200 and r.content.startswith(b"\xff\xd8\xff")
    assert c.get(f"/api/v1/auth/me/photo/{uid}.png").status_code == 200   # any saved extension
    assert c.get("/api/v1/auth/me/photo/..%2Fsecret.jpeg").status_code == 404
    assert c.get("/api/v1/auth/me/photo/nobody.jpg").status_code == 404
