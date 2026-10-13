"""
Instance management — create a new location, join one via invite code,
switch which one is active, list the ones you belong to.

These endpoints deliberately do NOT use Depends(get_db) (which is
overridden to require an already-active instance — see
instance_registry.py) since managing instances is inherently registry-
level, not instance-scoped. Each one opens its own registry session
directly, same reasoning as auth.py's own login endpoint.
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from typing import Optional, List

from ..registry_db import RegistrySessionLocal
from ..registry_models import Instance, GlobalUser, Membership
from ..instance_registry import provision_instance_database, provision_instance_database_from_import
from .auth import create_access_token, _get_crypt, oauth2_scheme, verify_token

logger = logging.getLogger("chirp.instances")
router = APIRouter(tags=["instances"])


def backfill_memberships_for_local_users(reg_db, inst_db, instance_id: str, skip_username: Optional[str] = None) -> int:
    """
    For every real local User row in this instance's own database that
    has no corresponding registry-level Membership yet, create one —
    reusing an existing GlobalUser with the same username if one exists,
    or provisioning a new GlobalUser from the local row's own username/
    email/hashed_pw (same bcrypt scheme both tables use, so the
    person's existing password keeps working unchanged; nothing here
    resets or exposes any credential).

    Used two ways: right after POST /instances/import, for every local
    account the imported database carried over besides the importing
    admin (already handled separately, right before this is called);
    and again, once, as a startup sweep over every already-existing
    instance (see AppSettings.local_users_membership_backfilled) to fix
    up instances imported before this existed. Returns how many
    Memberships were newly created, for logging.

    Each row is handled in its own try/except so one bad/unexpected
    local row can't abort the rest of the batch.
    """
    from ..models import User

    created = 0
    for local_user in inst_db.query(User).all():
        if skip_username and local_user.username == skip_username:
            continue
        try:
            global_user = reg_db.query(GlobalUser).filter(GlobalUser.username == local_user.username).first()
            if not global_user:
                global_user = GlobalUser(
                    username=local_user.username,
                    email=local_user.email,
                    hashed_pw=local_user.hashed_pw,
                    active=bool(local_user.active),
                )
                reg_db.add(global_user)
                reg_db.commit()
                reg_db.refresh(global_user)

            existing = reg_db.query(Membership).filter(
                Membership.user_id == global_user.id, Membership.instance_id == instance_id,
            ).first()
            if not existing:
                reg_db.add(Membership(user_id=global_user.id, instance_id=instance_id, role=local_user.role))
                reg_db.commit()
                created += 1
        except Exception as e:
            reg_db.rollback()
            logger.warning("backfill_memberships_for_local_users: failed for local user %s in instance %s: %s",
                            local_user.username, instance_id, e)
    return created


def get_current_global_user(token: str = Depends(oauth2_scheme)) -> GlobalUser:
    """
    Resolves the authenticated GlobalUser purely from the JWT's own
    global_user_id claim — deliberately not going through the
    (now-overridden) get_db, or requiring an active instance to already
    be set, since these endpoints are exactly how someone gets an active
    instance in the first place.
    """
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = verify_token(token)
    if not payload or not payload.get("global_user_id"):
        raise HTTPException(status_code=401, detail="Invalid token")
    reg_db = RegistrySessionLocal()
    try:
        user = reg_db.query(GlobalUser).filter(GlobalUser.id == payload["global_user_id"]).first()
        if not user or not user.active:
            raise HTTPException(status_code=401, detail="Account not found or disabled")
        return user
    finally:
        reg_db.close()


class InstanceOut(BaseModel):
    id: str
    name: str
    location_name: Optional[str] = None
    role: str
    invite_code: Optional[str] = None  # only populated for instances the caller admins


class CreateInstanceRequest(BaseModel):
    name: str
    location_name: Optional[str] = None
    admin_username: Optional[str] = None   # defaults to the global username
    admin_password: Optional[str] = None    # ignored; the site uses the account password


class JoinInstanceRequest(BaseModel):
    invite_code: str
    member_password: Optional[str] = None  # ignored; the site uses the account password


class SwitchInstanceRequest(BaseModel):
    instance_id: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.get("", response_model=List[InstanceOut])
def list_my_instances(user: GlobalUser = Depends(get_current_global_user)):
    reg_db = RegistrySessionLocal()
    try:
        memberships = reg_db.query(Membership).filter(Membership.user_id == user.id).all()
        out = []
        for m in memberships:
            inst = m.instance
            out.append(InstanceOut(
                id=inst.id, name=inst.name, location_name=inst.location_name,
                role=m.role,
                invite_code=inst.invite_code if m.role == "admin" else None,
            ))
        return out
    finally:
        reg_db.close()


@router.post("/create", response_model=TokenOut)
def create_instance(body: CreateInstanceRequest, user: GlobalUser = Depends(get_current_global_user)):
    """
    Real self-service "add a location" — provisions a genuinely fresh
    per-instance database (the exact real chirp-server schema, via
    provision_instance_database), creates the synced local admin User
    row inside it, and a real Membership. Returns a fresh token with
    this new instance already active, so the caller lands directly in
    their new, empty instance without a separate switch step.
    """
    from ..models import User

    reg_db = RegistrySessionLocal()
    try:
        db_filename = f"{user.id[:8]}_{int(datetime.utcnow().timestamp())}.db"
        instance = Instance(name=body.name, location_name=body.location_name,
                             db_filename=db_filename, created_by_user_id=user.id)
        reg_db.add(instance)
        reg_db.commit()
        reg_db.refresh(instance)

        provision_instance_database(db_filename)

        membership = Membership(user_id=user.id, instance_id=instance.id, role="admin")
        reg_db.add(membership)
        reg_db.commit()

        # Real synced local User row — this instance's own unmodified
        # code (current-user lookups, ownership checks, notification
        # prefs) reads from here, exactly as it already does for a
        # normal single-instance chirp-server deployment.
        from ..instance_registry import get_engine_for_instance
        from sqlalchemy.orm import sessionmaker
        engine = get_engine_for_instance(db_filename)
        InstanceSession = sessionmaker(bind=engine)
        inst_db = InstanceSession()
        try:
            local_user = User(
                username=body.admin_username or user.username,
                email=user.email,
                hashed_pw=user.hashed_pw,   # same password as the account
                role="admin",
            )
            inst_db.add(local_user)
            inst_db.commit()
        finally:
            inst_db.close()

        token = create_access_token({
            "sub": user.username, "global_user_id": user.id,
            "active_instance_id": instance.id,
        })
        logger.info("Created instance %s (%s) for user %s", instance.id, instance.name, user.username)
        return TokenOut(access_token=token)
    finally:
        reg_db.close()


@router.post("/import", response_model=TokenOut)
async def import_instance(
    file: UploadFile = File(...),
    name: str = Form(...),
    location_name: Optional[str] = Form(None),
    admin_username: Optional[str] = Form(None),
    admin_password: Optional[str] = Form(None),   # ignored; the site uses the account password
    user: GlobalUser = Depends(get_current_global_user),
):
    """
    Creates a brand-new instance from an UPLOADED, already-populated
    database file (a chirp-server export, or another instance's own
    backup) instead of starting empty — a real, requested feature: let
    someone migrate an existing single-tenant chirp-server deployment's
    history into this multi-tenant fork as its own separate location,
    rather than the only two options being start over from zero, or
    overwrite an existing instance's own data via /backup/restore
    (which is what that endpoint is for — replacing one instance in
    place, not creating a new one from an import).

    Mirrors create_instance() above closely on purpose — same registry
    row, same Membership, same token shape — differing only in how the
    instance's own database file gets its first content: copied in and
    migrated from the upload, not created empty.
    """
    import os as _os
    import sqlite3 as _sqlite3
    import tempfile as _tempfile

    # Validate BEFORE touching the registry at all — same checks
    # /backup/restore already applies to an uploaded file, so an
    # invalid upload never gets as far as creating a real Instance row
    # that would then need cleaning up by hand.
    content = await file.read()
    if not content.startswith(b"SQLite format 3"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid SQLite database.")

    with _tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        conn = _sqlite3.connect(tmp_path)
        try:
            conn.execute("PRAGMA integrity_check")
            tables = {t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        finally:
            conn.close()
        if "recordings" not in tables:
            raise HTTPException(status_code=400, detail="Uploaded file does not look like a Chirp database (no recordings table).")

        reg_db = RegistrySessionLocal()
        try:
            db_filename = f"{user.id[:8]}_{int(datetime.utcnow().timestamp())}.db"
            instance = Instance(name=name, location_name=location_name,
                                 db_filename=db_filename, created_by_user_id=user.id)
            reg_db.add(instance)
            reg_db.commit()
            reg_db.refresh(instance)

            provision_instance_database_from_import(db_filename, tmp_path)

            membership = Membership(user_id=user.id, instance_id=instance.id, role="admin")
            reg_db.add(membership)
            reg_db.commit()

            # Same synced-local-User step as create_instance() above,
            # but the imported database may already have its own real
            # Users carried over from the source deployment — those
            # stay exactly as imported (this is history, not something
            # to discard). If the importing person's own chosen
            # username happens to already exist in that imported data,
            # promote that existing row to admin and set the password
            # they just supplied, rather than attempting a second INSERT
            # that would collide with the real unique constraint on
            # username.
            from ..models import User
            from ..instance_registry import get_engine_for_instance
            from sqlalchemy.orm import sessionmaker
            engine = get_engine_for_instance(db_filename)
            InstanceSession = sessionmaker(bind=engine)
            inst_db = InstanceSession()
            try:
                desired_username = admin_username or user.username
                existing_local_user = inst_db.query(User).filter(User.username == desired_username).first()
                if existing_local_user:
                    existing_local_user.hashed_pw = user.hashed_pw
                    existing_local_user.role = "admin"
                    existing_local_user.active = True
                else:
                    inst_db.add(User(
                        username=desired_username,
                        email=user.email,
                        hashed_pw=user.hashed_pw,
                        role="admin",
                    ))
                inst_db.commit()

                # Every OTHER real local account the imported database
                # carried over (the importing admin above is already
                # handled) previously got left with no Membership at
                # all — unable to actually log in via this fork's real
                # GlobalUser-based auth, and invisible to Global Admin's
                # own member list, despite still showing up on this
                # instance's local Users page. Fixed by backfilling one
                # here, at import time, for every one of them.
                backfilled = backfill_memberships_for_local_users(reg_db, inst_db, instance.id, skip_username=desired_username)
                if backfilled:
                    logger.info("Backfilled %d Membership(s) for imported local users in instance %s", backfilled, instance.id)
            finally:
                inst_db.close()

            token = create_access_token({
                "sub": user.username, "global_user_id": user.id,
                "active_instance_id": instance.id,
            })
            logger.info("Imported instance %s (%s) for user %s from an uploaded database", instance.id, instance.name, user.username)
            return TokenOut(access_token=token)
        finally:
            reg_db.close()
    finally:
        try:
            _os.remove(tmp_path)
        except OSError:
            pass


@router.post("/join", response_model=TokenOut)
def join_instance(body: JoinInstanceRequest, user: GlobalUser = Depends(get_current_global_user)):
    from ..models import User

    reg_db = RegistrySessionLocal()
    try:
        instance = reg_db.query(Instance).filter(Instance.invite_code == body.invite_code.strip().upper()).first()
        if not instance:
            raise HTTPException(status_code=404, detail="Invalid invite code.")

        existing = reg_db.query(Membership).filter(
            Membership.user_id == user.id, Membership.instance_id == instance.id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="You're already a member of this instance.")

        membership = Membership(user_id=user.id, instance_id=instance.id, role="viewer")
        reg_db.add(membership)
        reg_db.commit()

        from ..instance_registry import get_engine_for_instance
        from sqlalchemy.orm import sessionmaker
        engine = get_engine_for_instance(instance.db_filename)
        InstanceSession = sessionmaker(bind=engine)
        inst_db = InstanceSession()
        try:
            local_user = User(
                username=user.username, email=user.email,
                hashed_pw=user.hashed_pw, role="viewer",   # same password as the account
            )
            inst_db.add(local_user)
            inst_db.commit()
        finally:
            inst_db.close()

        token = create_access_token({
            "sub": user.username, "global_user_id": user.id,
            "active_instance_id": instance.id,
        })
        logger.info("User %s joined instance %s via invite code", user.username, instance.id)
        return TokenOut(access_token=token)
    finally:
        reg_db.close()


@router.post("/switch", response_model=TokenOut)
def switch_instance(body: SwitchInstanceRequest, user: GlobalUser = Depends(get_current_global_user)):
    reg_db = RegistrySessionLocal()
    try:
        membership = reg_db.query(Membership).filter(
            Membership.user_id == user.id, Membership.instance_id == body.instance_id
        ).first()
        if not membership:
            raise HTTPException(status_code=403, detail="You don't have access to that instance.")
        token = create_access_token({
            "sub": user.username, "global_user_id": user.id,
            "active_instance_id": body.instance_id,
        })
        return TokenOut(access_token=token)
    finally:
        reg_db.close()
