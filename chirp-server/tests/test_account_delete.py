"""0.5.11.d: people can delete their account in the app."""
import uuid


def _local_user(db, username, role="viewer", pw="secret-pw"):
    from app.api.auth import _get_crypt
    from app.models import User
    u = User(id=str(uuid.uuid4()), username=username, hashed_pw=_get_crypt().hash(pw), role=role, active=True)
    db.add(u)
    db.commit()
    return u


def test_purge_removes_personal_rows_only(client):
    from app.database import SessionLocal
    from app.api.auth import purge_local_user
    from app.models import Comment, InboxNotification, User
    db = SessionLocal()
    try:
        u = _local_user(db, "leaver-" + uuid.uuid4().hex[:6])
        db.add(InboxNotification(user_id=u.id, title="New bird: Wren"))
        db.add(Comment(author=u.username, body="mine"))
        db.add(Comment(author="someone-else", body="theirs"))
        db.commit()
        purge_local_user(db, u)
        assert db.query(User).filter(User.username == u.username).count() == 0
        assert db.query(InboxNotification).filter(InboxNotification.user_id == u.id).count() == 0
        assert db.query(Comment).filter(Comment.author == u.username).count() == 0
        assert db.query(Comment).filter(Comment.author == "someone-else").count() >= 1
    finally:
        db.close()


def test_delete_endpoint_checks_password_and_deletes(client):
    from app.api.auth import create_access_token
    from app.database import SessionLocal
    from app.models import User
    name = "deleteme-" + uuid.uuid4().hex[:6]
    db = SessionLocal()
    try:
        _local_user(db, name)
    finally:
        db.close()
    try:   # instances fork: the sign-in identity lives in the registry
        from app.registry_db import RegistrySessionLocal, init_registry_db
        init_registry_db()
        from app.registry_models import GlobalUser
        from app.api.auth import _get_crypt
        reg = RegistrySessionLocal()
        reg.add(GlobalUser(username=name, hashed_pw=_get_crypt().hash("secret-pw")))
        reg.commit(); reg.close()
    except ImportError:
        GlobalUser = None
    h = {"Authorization": "Bearer " + create_access_token({"sub": name, "role": "viewer"})}
    assert client.post("/api/v1/auth/me/delete", json={"password": "wrong"}, headers=h).status_code == 403
    r = client.post("/api/v1/auth/me/delete", json={"password": "secret-pw"}, headers=h)
    assert r.status_code == 200, r.text
    if GlobalUser is not None:
        reg = RegistrySessionLocal()
        assert reg.query(GlobalUser).filter(GlobalUser.username == name).count() == 0
        reg.close()
    else:
        db = SessionLocal()
        assert db.query(User).filter(User.username == name).count() == 0
        db.close()
