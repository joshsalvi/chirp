"""New locations on ourchirp.com wait for a global admin; invite codes stay instant."""
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture()
def env(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app import website
    from app.api import admin_panel, instances
    from app.registry_db import RegistrySessionLocal, init_registry_db
    from app.registry_models import GlobalUser, RegistrySettings
    from app.services import platform_mail
    from app.website import site_requests
    init_registry_db()
    monkeypatch.setattr(website, "HOSTS_WEBSITE", True)
    mails = []
    monkeypatch.setattr(platform_mail, "send_platform_email",
                        lambda to, subject, *a, **k: mails.append((to, subject, a[3])) or True)
    monkeypatch.setattr(platform_mail, "public_url", lambda request=None: "https://chirp.test")
    monkeypatch.setattr(platform_mail, "global_admin_emails", lambda: ["boss@example.com"])

    reg = RegistrySessionLocal()
    s = reg.query(RegistrySettings).filter(RegistrySettings.id == 1).first()
    if s:
        s.location_approval = None                          # default: on
    tag = uuid.uuid4().hex[:8]
    user = GlobalUser(id=f"u-{tag}", username=f"chloe{tag}", email=f"chloe{tag}@example.com", hashed_pw="x")
    reg.add(user)
    reg.commit()
    uid, uname, email = user.id, user.username, user.email
    reg.close()

    who = {"user": None}

    def current():
        r = RegistrySessionLocal()
        try:
            u = r.query(GlobalUser).filter(GlobalUser.id == who["user"]).first()
            r.expunge(u)
            return u
        finally:
            r.close()

    app = FastAPI()
    app.include_router(instances.router, prefix="/api/v1/instances")
    app.include_router(site_requests.admin_router, prefix="/api/v1/admin/site-requests")
    app.dependency_overrides[instances.get_current_global_user] = current
    app.dependency_overrides[admin_panel.get_current_global_admin] = \
        lambda: GlobalUser(id="admin", username="boss", hashed_pw="x", is_global_admin=True)
    who["user"] = uid
    return TestClient(app), mails, {"id": uid, "username": uname, "email": email}, who


def test_location_waits_for_approval(env):
    from app.registry_db import RegistrySessionLocal
    from app.registry_models import Membership
    c, mails, user, _ = env

    r = c.post("/api/v1/instances/create", json={"name": "Chloe's porch", "location_name": "Clinton, MS"})
    assert r.status_code == 200 and r.json()["pending"] is True and "access_token" not in r.json()
    assert any("new location" in m[1] for m in mails)           # admins hear about it
    mine = c.get("/api/v1/instances/requests").json()
    assert mine["approval_required"] and mine["has_email"]
    req = mine["requests"][0]
    assert req["name"] == "Chloe's porch" and req["status"] == "pending"
    assert c.get("/api/v1/instances").json() == []               # nothing yet

    # Import is the other way to make a location: it waits too.
    assert c.post("/api/v1/instances/import", data={"name": "x"},
                  files={"file": ("a.db", b"x")}).status_code == 403

    row = [x for x in c.get("/api/v1/admin/site-requests?status=pending").json() if x["id"] == req["id"]][0]
    assert row["kind"] == "location" and row["user_id"] == user["id"]
    out = c.post(f"/api/v1/admin/site-requests/{req['id']}/approve").json()
    assert out["status"] == "approved" and out["instance_id"] and out["email_sent"]
    assert mails[-1][0] == user["email"] and "ready" in mails[-1][1]

    reg = RegistrySessionLocal()
    try:
        m = reg.query(Membership).filter(Membership.user_id == user["id"], Membership.instance_id == out["instance_id"]).first()
        assert m and m.role == "admin"
    finally:
        reg.close()
    listed = c.get("/api/v1/instances").json()
    assert [i["name"] for i in listed] == ["Chloe's porch"] and listed[0]["location_name"] == "Clinton, MS"
    assert c.get("/api/v1/instances/requests").json()["requests"] == []   # approved ones leave the list


def test_deny_cancel_limit_and_switch_off(env):
    c, mails, user, _ = env
    a = c.post("/api/v1/instances/create", json={"name": "One"}).json()["request"]
    c.post("/api/v1/instances/create", json={"name": "Two"})
    c.post("/api/v1/instances/create", json={"name": "Three"})
    assert c.post("/api/v1/instances/create", json={"name": "Four"}).status_code == 429
    assert c.post("/api/v1/instances/create", json={"name": "  "}).status_code == 400

    d = c.post(f"/api/v1/admin/site-requests/{a['id']}/deny", json={"reason": "Duplicate of your yard."}).json()
    assert d["status"] == "denied" and d["email_sent"] and "Join with Code" in mails[-1][2]
    denied = [r for r in c.get("/api/v1/instances/requests").json()["requests"] if r["id"] == a["id"]][0]
    assert denied["status"] == "denied" and denied["deny_reason"] == "Duplicate of your yard."
    for r in c.get("/api/v1/instances/requests").json()["requests"]:
        assert c.delete(f"/api/v1/instances/requests/{r['id']}").status_code == 204
    assert c.get("/api/v1/instances/requests").json()["requests"] == []
    assert c.delete("/api/v1/instances/requests/nope").status_code == 404

    assert c.get("/api/v1/admin/site-requests/settings").json() == {"location_approval": True}
    assert c.put("/api/v1/admin/site-requests/settings", json={"location_approval": False}).json() == {"location_approval": False}
    r = c.post("/api/v1/instances/create", json={"name": "Instant"}).json()
    assert r.get("access_token") and "pending" not in r
    assert c.get("/api/v1/instances/requests").json()["approval_required"] is False
    c.put("/api/v1/admin/site-requests/settings", json={"location_approval": True})


def test_global_admin_and_self_hosted_skip_approval(env, monkeypatch):
    from app import website
    from app.registry_db import RegistrySessionLocal
    from app.registry_models import GlobalUser
    c, _, user, who = env
    reg = RegistrySessionLocal()
    reg.query(GlobalUser).filter(GlobalUser.id == user["id"]).update({"is_global_admin": True})
    reg.commit()
    reg.close()
    assert c.post("/api/v1/instances/create", json={"name": "Mine"}).json().get("access_token")
    reg = RegistrySessionLocal()
    reg.query(GlobalUser).filter(GlobalUser.id == user["id"]).update({"is_global_admin": False})
    reg.commit()
    reg.close()
    monkeypatch.setattr(website, "HOSTS_WEBSITE", False)
    assert c.post("/api/v1/instances/create", json={"name": "Self-hosted"}).json().get("access_token")
