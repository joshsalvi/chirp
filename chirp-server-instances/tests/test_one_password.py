"""One password per person: joining a site with an invite code needs only
the code, and a password change reaches the account and every site."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_invite_join_uses_account_password_and_changes_sync():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker
    from app.api import auth
    from app.api.auth import _get_crypt, set_account_password
    from app.instance_registry import get_engine_for_instance, provision_instance_database
    from app.models import User
    from app.registry_db import RegistrySessionLocal, init_registry_db
    from app.registry_models import GlobalUser, Instance

    init_registry_db()
    reg = RegistrySessionLocal()
    inst = Instance(name="Pond", db_filename="onepw_test.db", created_by_user_id="x")
    reg.add(inst); reg.commit(); reg.refresh(inst)
    code, dbf = inst.invite_code, inst.db_filename
    reg.close()
    provision_instance_database(dbf)

    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1/auth")
    c = TestClient(app)
    r = c.post("/api/v1/auth/register", json={"username": "wren1", "password": "songbird1", "invite_code": code})
    assert r.status_code == 201, r.text

    local = lambda: sessionmaker(bind=get_engine_for_instance(dbf))()
    db = local()
    try:
        u = db.query(User).filter(User.username == "wren1").one()
        assert _get_crypt().verify("songbird1", u.hashed_pw) and u.role == "viewer"
    finally:
        db.close()

    set_account_password("wren1", _get_crypt().hash("newsong22"))
    reg = RegistrySessionLocal()
    try:
        assert _get_crypt().verify("newsong22", reg.query(GlobalUser).filter_by(username="wren1").one().hashed_pw)
    finally:
        reg.close()
    db = local()
    try:
        assert _get_crypt().verify("newsong22", db.query(User).filter(User.username == "wren1").one().hashed_pw)
    finally:
        db.close()
