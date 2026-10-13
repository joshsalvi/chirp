"""Support / feature form: validation, honeypot, storage, admin list."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_support_form(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import admin_panel, support
    from app.registry_db import init_registry_db
    from app.registry_models import GlobalUser
    from app.services import platform_mail
    init_registry_db()
    support._recent.clear()
    mails = []
    monkeypatch.setattr(platform_mail, "global_admin_emails", lambda: ["boss@example.com"])
    monkeypatch.setattr(platform_mail, "send_platform_email", lambda to, subject, *a, **k: mails.append((to, subject, a[3])) or True)
    app = FastAPI()
    app.include_router(support.router, prefix="/api/v1/support")
    app.include_router(support.admin_router, prefix="/api/v1/admin/support")
    app.dependency_overrides[admin_panel.get_current_global_admin] = lambda: GlobalUser(id="a", username="boss", hashed_pw="x", is_global_admin=True)
    c = TestClient(app)
    assert c.post("/api/v1/support", json={"message": "hi"}).status_code == 400                       # too short
    assert c.post("/api/v1/support", json={"message": "Please add dark mode maps"}).status_code == 400  # no way to reply
    assert c.post("/api/v1/support", json={"message": "spam spam", "website": "x"}).json() == {"ok": True}
    r = c.post("/api/v1/support", json={"kind": "feature", "name": "Ada", "email": "ada@example.com",
                                        "message": "Please add a moth mode", "page": "support"})
    assert r.status_code == 201
    assert mails and mails[0][0] == ["boss@example.com"] and "feature idea" in mails[0][1] and "moth mode" in mails[0][2]
    rows = c.get("/api/v1/admin/support").json()
    mine = [m for m in rows if m["message"] == "Please add a moth mode"][0]
    assert mine["kind"] == "feature" and not mine["done"] and "ip" not in mine
    assert c.patch(f"/api/v1/admin/support/{mine['id']}", json={"done": True}).json()["done"] is True
    assert c.delete(f"/api/v1/admin/support/{mine['id']}").status_code == 204
