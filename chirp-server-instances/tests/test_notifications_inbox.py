"""0.5.11.a: Notifications inbox and APNs environment fallback."""
import sys
import types

try:
    import pywebpush  # noqa: F401
except ImportError:            # the server image has it; a bare test machine may not
    _m = types.ModuleType("pywebpush")
    _m.webpush = lambda *a, **k: None
    class WebPushException(Exception):
        pass
    _m.WebPushException = WebPushException
    sys.modules["pywebpush"] = _m


def _db():
    from app.database import SessionLocal
    return SessionLocal()


def test_sent_push_lands_in_inbox(client):
    from app.services.push_notifications import send_push_to_all
    client.delete("/api/v1/notifications")
    db = _db()
    try:
        send_push_to_all(db, "New bird: Wood Thrush", "Detected at 91% confidence", url="/", tag="new-bird")
    finally:
        db.close()
    r = client.get("/api/v1/notifications").json()
    assert r["unread"] >= 1
    first = r["items"][0]
    assert first["title"] == "New bird: Wood Thrush" and first["kind"] == "new-bird" and not first["read"]
    assert client.get("/api/v1/notifications/unread").json()["unread"] == r["unread"]
    assert client.post(f"/api/v1/notifications/{first['id']}/read").json()["unread"] == r["unread"] - 1
    client.post("/api/v1/notifications/read-all")
    assert client.get("/api/v1/notifications/unread").json()["unread"] == 0
    assert client.delete("/api/v1/notifications").json()["deleted"] >= 1
    assert client.get("/api/v1/notifications").json()["items"] == []


def test_test_native_without_phone_still_records(client):
    client.delete("/api/v1/notifications")
    r = client.post("/api/v1/push/test-native")
    assert r.status_code == 404
    items = client.get("/api/v1/notifications").json()["items"]
    assert items and items[0]["kind"] == "test"


class _Resp:
    def __init__(self, code, reason=""):
        self.status_code = code
        self._r = reason
        self.text = reason

    def json(self):
        return {"reason": self._r}


def _fake_client(answers, seen):
    class C:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, **k):
            seen.append(url.split("/")[2])
            return answers[url.split("/")[2]]
    return C


def _setup(db, production=True):
    import uuid
    from app.models import AppSettings, ApnsDeviceToken
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    s.apns_team_id, s.apns_key_id, s.apns_bundle_id, s.apns_auth_key = "T", "K", "com.x", "pem"
    s.apns_production = production
    tok = "ab" * 32
    db.query(ApnsDeviceToken).filter(ApnsDeviceToken.device_token == tok).delete()
    db.add(ApnsDeviceToken(id=str(uuid.uuid4()), device_token=tok))
    db.commit()
    return tok


def test_apns_tries_other_environment(client, monkeypatch):
    from app.services import apns_push
    from app.models import ApnsDeviceToken
    monkeypatch.setattr(apns_push, "_get_apns_jwt", lambda *a: "jwt")
    db = _db()
    try:
        tok = _setup(db, production=True)
        seen = []
        monkeypatch.setattr(apns_push.httpx, "Client", _fake_client(
            {"api.push.apple.com": _Resp(400, "BadDeviceToken"), "api.sandbox.push.apple.com": _Resp(200)}, seen))
        assert apns_push.send_apns_push(db, tok, "t", "b")
        assert seen == ["api.push.apple.com", "api.sandbox.push.apple.com"]
        assert db.query(ApnsDeviceToken).filter(ApnsDeviceToken.device_token == tok).count() == 1

        seen.clear()
        monkeypatch.setattr(apns_push.httpx, "Client", _fake_client(
            {"api.push.apple.com": _Resp(400, "BadDeviceToken"), "api.sandbox.push.apple.com": _Resp(400, "BadDeviceToken")}, seen))
        assert not apns_push.send_apns_push(db, tok, "t", "b")
        assert db.query(ApnsDeviceToken).filter(ApnsDeviceToken.device_token == tok).count() == 0
    finally:
        from app.models import AppSettings
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        s.apns_team_id = s.apns_key_id = s.apns_bundle_id = s.apns_auth_key = None
        db.commit()
        db.close()


def test_apns_token_is_es256_with_installed_libraries():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    import jwt
    from app.services import apns_push
    apns_push._jwt_cache.clear()
    k = ec.generate_private_key(ec.SECP256R1())
    pem = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                          serialization.NoEncryption()).decode()
    tok = apns_push._get_apns_jwt("TEAM123456", "KEY1234567", pem + "\n")
    assert jwt.get_unverified_header(tok)["kid"] == "KEY1234567"
    pub = k.public_key().public_bytes(serialization.Encoding.PEM,
                                      serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    assert jwt.decode(tok, pub, algorithms=["ES256"])["iss"] == "TEAM123456"
