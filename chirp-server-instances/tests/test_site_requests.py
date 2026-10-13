"""Site requests from /about and the push relay: request, approve, email, relay."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture()
def api(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.registry_db import init_registry_db
    from app.registry_models import GlobalUser
    from app.api import site_requests, push_relay, admin_panel
    from app.services import platform_mail
    init_registry_db()
    site_requests._recent.clear()
    mails = []
    monkeypatch.setattr(platform_mail, "send_platform_email",
                        lambda to, subject, *a, **k: mails.append((to, subject, a[3])) or True)
    monkeypatch.setattr(platform_mail, "public_url", lambda request=None: "https://chirp.test")
    app = FastAPI()
    app.include_router(site_requests.router, prefix="/api/v1/site-requests")
    app.include_router(site_requests.admin_router, prefix="/api/v1/admin/site-requests")
    app.include_router(push_relay.router, prefix="/api/v1/push-relay")
    app.include_router(push_relay.admin_router, prefix="/api/v1/admin/relay-servers")
    app.dependency_overrides[admin_panel.get_current_global_admin] = \
        lambda: GlobalUser(id="admin", username="boss", hashed_pw="x", is_global_admin=True)
    return TestClient(app), mails


HOSTED = {"kind": "hosted", "full_name": "Ada Lovelace", "email": "ada@example.com", "site_name": "Ada's Yard",
          "username": "ada_yard", "password": "birdsong8", "location_name": "Ithaca, NY",
          "latitude": 42.44, "longitude": -76.5, "timezone": "America/New_York", "hardware": "Pi 5 + ReSpeaker"}


def test_hosted_request_approve_creates_site_and_emails_setup(api):
    from sqlalchemy.orm import sessionmaker
    from app.api.auth import _get_crypt
    from app.instance_registry import get_engine_for_instance
    from app.models import AppSettings, User
    from app.registry_db import RegistrySessionLocal
    from app.registry_models import GlobalUser, Instance, Membership
    c, mails = api
    assert c.post("/api/v1/site-requests", json={**HOSTED, "email": "nope"}).status_code == 400
    assert c.post("/api/v1/site-requests", json={**HOSTED, "password": "short"}).status_code == 400
    r = c.post("/api/v1/site-requests", json=HOSTED)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert c.post("/api/v1/site-requests", json=HOSTED).status_code == 409          # username held by pending request
    pending = c.get("/api/v1/admin/site-requests?status=pending").json()
    assert [p["id"] for p in pending] == [rid] and "hashed_pw" not in pending[0] and "ip" not in pending[0]
    mails.clear()

    r = c.post(f"/api/v1/admin/site-requests/{rid}/approve")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "approved" and out["email_sent"] and out["instance_id"]
    to, subject, text = mails[0]
    assert to == "ada@example.com" and "ready" in subject
    assert "https://chirp.test/api/v1/recordings/upload" in text and "api_key: \"chirp-" in text
    assert c.post(f"/api/v1/admin/site-requests/{rid}/approve").status_code == 409

    reg = RegistrySessionLocal()
    try:
        gu = reg.query(GlobalUser).filter(GlobalUser.username == "ada_yard").one()
        assert _get_crypt().verify("birdsong8", gu.hashed_pw)
        inst = reg.query(Instance).filter(Instance.id == out["instance_id"]).one()
        assert inst.name == "Ada's Yard" and inst.invite_code in text
        assert reg.query(Membership).filter_by(user_id=gu.id, instance_id=inst.id, role="admin").count() == 1
        db = sessionmaker(bind=get_engine_for_instance(inst.db_filename))()
        try:
            s = db.query(AppSettings).first()
            assert (s.latitude, s.longitude, s.timezone, s.server_url) == (42.44, -76.5, "America/New_York", "https://chirp.test")
            key = s.device_api_keys[0]["key"]
            assert key in text and s.auth_enabled
            assert db.query(User).filter(User.username == "ada_yard", User.role == "admin").count() == 1
        finally:
            db.close()
    finally:
        reg.close()
    from app.instance_registry import _find_instance_for_device_key
    assert _find_instance_for_device_key(key).id == out["instance_id"]


def test_honeypot_deny_and_rate_limit(api):
    c, mails = api
    assert c.post("/api/v1/site-requests", json={**HOSTED, "username": "bot_1", "website": "x"}).json() == {"ok": True}
    r = c.post("/api/v1/site-requests", json={**HOSTED, "username": "deny_me"})
    rid = r.json()["id"]
    mails.clear()
    out = c.post(f"/api/v1/admin/site-requests/{rid}/deny", json={"reason": "Outside our area for now."}).json()
    assert out["status"] == "denied" and mails and "Outside our area" in mails[0][2]
    for i in range(4):                       # 5 an hour per address, invalid ones included
        c.post("/api/v1/site-requests", json={**HOSTED, "username": f"rl_{i}", "email": "x"})
    assert c.post("/api/v1/site-requests", json={**HOSTED, "username": "rl_x"}).status_code == 429


def test_relay_request_token_and_send(api, monkeypatch):
    from app.services import apns_push
    c, mails = api
    bad = {"kind": "relay", "full_name": "Bo", "email": "bo@example.com", "site_name": "Bo's server"}
    assert c.post("/api/v1/site-requests", json=bad).status_code == 400              # needs server address
    rid = c.post("/api/v1/site-requests", json={**bad, "server_url": "https://bo.example.com/"}).json()["id"]
    mails.clear()
    out = c.post(f"/api/v1/admin/site-requests/{rid}/approve").json()
    assert out["relay_server_id"] and mails
    token = next(w for w in mails[0][2].split() if w.startswith("chirprelay_"))

    body = {"device_token": "ab" * 32, "payload": {"aps": {"alert": {"title": "t", "body": "b"}}}, "server": "https://bo.example.com"}
    monkeypatch.setattr(apns_push, "platform_credentials", lambda: None)
    assert c.post("/api/v1/push-relay/send", json=body, headers={"Authorization": f"Bearer {token}"}).status_code == 503
    sent = []
    monkeypatch.setattr(apns_push, "platform_credentials", lambda: {"team_id": "T", "key_id": "K", "bundle_id": "b", "auth_key": "k"})
    monkeypatch.setattr(apns_push, "deliver", lambda creds, tok, payload: sent.append(payload) or (True, None, None))
    assert c.post("/api/v1/push-relay/send", json=body).status_code == 401
    assert c.post("/api/v1/push-relay/send", json=body, headers={"Authorization": "Bearer chirprelay_wrong"}).status_code == 401
    r = c.post("/api/v1/push-relay/send", json=body, headers={"Authorization": f"Bearer {token}"})
    assert r.json() == {"ok": True, "error": None, "dead": None} and sent[0]["server"] == "https://bo.example.com"
    assert c.post("/api/v1/push-relay/send", json={**body, "device_token": "zz"},
                  headers={"Authorization": f"Bearer {token}"}).status_code == 400

    relays = c.get("/api/v1/admin/relay-servers").json()
    row = next(s for s in relays["servers"] if s["id"] == out["relay_server_id"])
    assert row["sent_count"] == 1 and "token_hash" not in row
    c.patch(f"/api/v1/admin/relay-servers/{row['id']}", json={"active": False})
    assert c.post("/api/v1/push-relay/send", json=body, headers={"Authorization": f"Bearer {token}"}).status_code == 401
    made = c.post("/api/v1/admin/relay-servers", json={"name": "Manual"}).json()
    assert made["token"].startswith("chirprelay_")


def test_push_route_order(monkeypatch):
    from types import SimpleNamespace as NS
    from app.services import apns_push
    site = NS(apns_team_id="T", apns_key_id="K", apns_bundle_id="b", apns_auth_key="k", apns_production=True,
              push_relay_token=None, push_relay_url=None)
    bare = NS(apns_team_id=None, apns_key_id=None, apns_bundle_id=None, apns_auth_key=None,
              push_relay_token=" chirprelay_x ", push_relay_url=None)
    monkeypatch.setattr(apns_push, "platform_credentials", lambda: None)
    assert apns_push.push_route(site) == "site"
    assert apns_push.push_route(bare) == "relay"
    assert apns_push._relay(bare) == ("https://ourchirp.com", "chirprelay_x")
    monkeypatch.setattr(apns_push, "platform_credentials", lambda: {"team_id": "P"})
    assert apns_push.push_route(bare) == "server"
