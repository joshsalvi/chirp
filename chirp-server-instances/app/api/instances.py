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
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from typing import Optional, List

from ..registry_db import RegistrySessionLocal
from ..registry_models import Instance, GlobalUser, Membership
from ..instance_registry import new_db_filename, provision_instance_database, provision_instance_database_from_import
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


def provision_location(reg_db, user: GlobalUser, name: str, location_name: Optional[str] = None,
                       admin_username: Optional[str] = None) -> Instance:
    """A new, empty location owned by `user`: its own database, an admin
    Membership and the synced local admin User row that the instance's
    own code reads (current user, ownership, notification prefs). Used
    by self-service create and by approving a location request
    (website/site_requests.py). Commits."""
    from sqlalchemy.orm import sessionmaker
    from ..instance_registry import get_engine_for_instance
    from ..models import AppSettings, User

    db_filename = new_db_filename(user.id)
    instance = Instance(name=name, location_name=location_name,
                        db_filename=db_filename, created_by_user_id=user.id)
    reg_db.add(instance)
    reg_db.commit()
    reg_db.refresh(instance)

    provision_instance_database(db_filename)

    reg_db.add(Membership(user_id=user.id, instance_id=instance.id, role="admin"))
    reg_db.commit()

    inst_db = sessionmaker(bind=get_engine_for_instance(db_filename))()
    try:
        inst_db.add(User(username=admin_username or user.username, email=user.email,
                         hashed_pw=user.hashed_pw,   # same password as the account
                         role="admin"))
        if location_name:
            s = inst_db.query(AppSettings).filter(AppSettings.id == 1).first()
            if s and not s.location_name:
                s.location_name = location_name
        inst_db.commit()
    finally:
        inst_db.close()
    logger.info("Created instance %s (%s) for user %s", instance.id, instance.name, user.username)
    return instance


def location_approval_required(user: Optional[GlobalUser] = None) -> bool:
    """On ourchirp.com new locations wait for a global admin (Requests tab)
    unless that's switched off; joining with an invite code stays instant.
    Self-hosted servers have no Requests tab, so they never wait.
    Global admins never wait."""
    from ..website import HOSTS_WEBSITE
    from ..registry_models import RegistrySettings
    if not HOSTS_WEBSITE or (user is not None and user.is_global_admin):
        return False
    reg_db = RegistrySessionLocal()
    try:
        s = reg_db.query(RegistrySettings).filter(RegistrySettings.id == 1).first()
        return not (s and s.location_approval is False)
    finally:
        reg_db.close()


MAX_PENDING_LOCATIONS = 3


@router.post("/create")
def create_instance(body: CreateInstanceRequest, request: Request, user: GlobalUser = Depends(get_current_global_user)):
    """
    "Add a location". Where new locations need approval, this files a
    location request instead and returns {"pending": true, ...}; the
    person sees it waiting on their location screen and is emailed when
    it's approved. Otherwise it provisions the location right away and
    returns a token with it already active.
    """
    name = (body.name or "").strip()[:80]
    if not name:
        raise HTTPException(400, "Give the location a name.")
    location_name = (body.location_name or "").strip()[:120] or None

    if location_approval_required(user):
        from ..registry_models import SiteRequest
        reg_db = RegistrySessionLocal()
        try:
            mine = reg_db.query(SiteRequest).filter(SiteRequest.kind == "location", SiteRequest.user_id == user.id,
                                                    SiteRequest.status == "pending")
            if mine.count() >= MAX_PENDING_LOCATIONS:
                raise HTTPException(429, "You have locations waiting for approval already. You'll hear back soon.")
            row = SiteRequest(kind="location", user_id=user.id, username=user.username,
                              full_name=user.username, email=user.email or "",
                              site_name=name, location_name=location_name)
            reg_db.add(row)
            reg_db.commit()
            reg_db.refresh(row)
            _notify_admins_of_location(row, request)
            logger.info("Location request %s (%s) from %s", row.id, name, user.username)
            return {"pending": True, "request": location_request_out(row)}
        finally:
            reg_db.close()

    reg_db = RegistrySessionLocal()
    try:
        instance = provision_location(reg_db, user, name, location_name, body.admin_username)
        token = create_access_token({
            "sub": user.username, "global_user_id": user.id,
            "active_instance_id": instance.id,
        })
        return {"access_token": token, "token_type": "bearer"}
    finally:
        reg_db.close()


def _notify_admins_of_location(row, request: Request):
    """Emails the global admins that a location is waiting in Requests."""
    from html import escape
    try:
        from ..services.platform_mail import global_admin_emails, public_url, send_platform_email
        to = global_admin_emails()
        if not to:
            return
        base = public_url(request)
        place = f" ({row.location_name})" if row.location_name else ""
        who = row.username + (f", {row.email}" if row.email else "")
        send_platform_email(to, f"Chirp: {row.username} requests a new location", "New location request",
                            f"{row.username} requests a new location",
                            f"<p>{escape(who)} asks for <b>{escape(row.site_name)}</b>{escape(place)}.</p>",
                            f"{who} asks for {row.site_name}{place}.\n\nReview: {base}/global-admin",
                            cta_url=f"{base}/global-admin", cta_label="Review request", server_url=base)
    except Exception as e:
        logger.warning("Location request %s: admin notice failed: %s", row.id, e)


def location_request_out(r) -> dict:
    return {"id": r.id, "name": r.site_name, "location_name": r.location_name, "status": r.status,
            "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
            "decided_at": r.decided_at.isoformat() + "Z" if r.decided_at else None,
            "deny_reason": r.deny_reason}


@router.get("/requests")
def my_location_requests(user: GlobalUser = Depends(get_current_global_user)):
    """The caller's location requests from the last 30 days, for the
    location screen, plus whether new locations need approval here."""
    from datetime import timedelta
    from ..registry_models import SiteRequest
    reg_db = RegistrySessionLocal()
    try:
        rows = (reg_db.query(SiteRequest)
                .filter(SiteRequest.kind == "location", SiteRequest.user_id == user.id,
                        SiteRequest.created_at >= datetime.utcnow() - timedelta(days=30))
                .order_by(SiteRequest.created_at.desc()).all())
        return {"approval_required": location_approval_required(user),
                "has_email": bool(user.email),
                "requests": [location_request_out(r) for r in rows if r.status != "approved"]}
    finally:
        reg_db.close()


@router.delete("/requests/{request_id}", status_code=204)
def cancel_location_request(request_id: str, user: GlobalUser = Depends(get_current_global_user)):
    """Withdraws one of the caller's own pending requests, or clears a denied one from their list."""
    from ..registry_models import SiteRequest
    reg_db = RegistrySessionLocal()
    try:
        row = reg_db.query(SiteRequest).filter(SiteRequest.id == request_id, SiteRequest.kind == "location",
                                               SiteRequest.user_id == user.id).first()
        if not row:
            raise HTTPException(404, "Request not found")
        if row.status == "approved":
            raise HTTPException(409, "That location is already set up.")
        reg_db.delete(row)
        reg_db.commit()
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

    if location_approval_required(user):
        raise HTTPException(403, "New locations here need approval. Request one with New Location; "
                                 "once it's ready, restore your database in Settings → Backup.")

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
            db_filename = new_db_filename(user.id)
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


# Wrong invite codes per account in the last hour (guessing one is the only
# way into a site without being asked).
_bad_invites: dict = {}


@router.post("/join", response_model=TokenOut)
def join_instance(body: JoinInstanceRequest, user: GlobalUser = Depends(get_current_global_user)):
    from ..models import User

    reg_db = RegistrySessionLocal()
    try:
        import time as _t
        now = _t.time()
        tries = [x for x in _bad_invites.get(user.id, []) if now - x < 3600]
        if len(tries) >= 20:
            raise HTTPException(status_code=429, detail="Too many invalid invite codes. Try again in an hour.")
        instance = reg_db.query(Instance).filter(Instance.invite_code == body.invite_code.strip().upper()).first()
        if not instance:
            _bad_invites[user.id] = tries + [now]
            from ..security import note
            note("bad_invite", "", user.username[:40])
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
