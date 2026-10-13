"""
Global admin panel — server-wide management of every instance and every
global account on this server, for whoever holds is_global_admin=True
on their GlobalUser row (see registry_models.py and main.py's own
bootstrap comment for how the first one gets set).

Deliberately its own registry-only router, same reasoning as
instances.py: this is registry-level data, not instance-scoped, so
these endpoints never use the (overridden) Depends(get_db) and instead
open their own registry session directly.

This fills a real gap in the original multi-instance design: before
this, the only way to add someone to an instance was self-service via
invite code (always as a viewer, with no way to promote them
afterward), and there was no view of the server as a whole — GET
/instances is deliberately scoped to the caller's own memberships only.
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List

from ..registry_db import RegistrySessionLocal
from ..registry_models import Instance, GlobalUser, Membership, RegistrySettings
from .instances import get_current_global_user

logger = logging.getLogger("chirp.admin_panel")
router = APIRouter(tags=["admin"])

VALID_ROLES = {"admin", "submitter", "viewer"}


def get_current_global_admin(user: GlobalUser = Depends(get_current_global_user)) -> GlobalUser:
    """
    Same shape as chirp-server's own require_admin, one layer up: not
    just authenticated, but specifically a server-wide admin. A 403
    here (not 404) is deliberate — the panel's existence isn't a
    secret worth hiding, only access to it is being denied.
    """
    if not user.is_global_admin:
        raise HTTPException(status_code=403, detail="Global admin access required")
    return user


# ── Overview ─────────────────────────────────────────────────────────────

class OverviewOut(BaseModel):
    total_instances: int
    total_users: int
    total_global_admins: int


@router.get("/overview", response_model=OverviewOut)
def get_overview(admin: GlobalUser = Depends(get_current_global_admin)):
    reg_db = RegistrySessionLocal()
    try:
        return OverviewOut(
            total_instances=reg_db.query(Instance).count(),
            total_users=reg_db.query(GlobalUser).count(),
            total_global_admins=reg_db.query(GlobalUser).filter(GlobalUser.is_global_admin == True).count(),  # noqa: E712
        )
    finally:
        reg_db.close()


# ── Instances ────────────────────────────────────────────────────────────

class AdminInstanceOut(BaseModel):
    id: str
    name: str
    location_name: Optional[str]
    invite_code: str
    created_at: datetime
    created_by_username: Optional[str]
    member_count: int


@router.get("/instances", response_model=List[AdminInstanceOut])
def list_all_instances(admin: GlobalUser = Depends(get_current_global_admin)):
    """Every instance on this server, regardless of the caller's own memberships."""
    reg_db = RegistrySessionLocal()
    try:
        out = []
        for inst in reg_db.query(Instance).order_by(Instance.created_at.desc()).all():
            creator = reg_db.query(GlobalUser).filter(GlobalUser.id == inst.created_by_user_id).first() if inst.created_by_user_id else None
            member_count = reg_db.query(Membership).filter(Membership.instance_id == inst.id).count()
            out.append(AdminInstanceOut(
                id=inst.id, name=inst.name, location_name=inst.location_name,
                invite_code=inst.invite_code, created_at=inst.created_at,
                created_by_username=creator.username if creator else None,
                member_count=member_count,
            ))
        return out
    finally:
        reg_db.close()


class MembershipOut(BaseModel):
    membership_id: str
    user_id: str
    username: str
    email: Optional[str]
    role: str
    joined_at: datetime


@router.get("/instances/{instance_id}/members", response_model=List[MembershipOut])
def list_instance_members(instance_id: str, admin: GlobalUser = Depends(get_current_global_admin)):
    reg_db = RegistrySessionLocal()
    try:
        instance = reg_db.query(Instance).filter(Instance.id == instance_id).first()
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        out = []
        for m in reg_db.query(Membership).filter(Membership.instance_id == instance_id).all():
            out.append(MembershipOut(
                membership_id=m.id, user_id=m.user_id, username=m.user.username,
                email=m.user.email, role=m.role, joined_at=m.joined_at,
            ))
        return out
    finally:
        reg_db.close()


class AddMemberRequest(BaseModel):
    username: str
    role: str = "viewer"
    member_password: str  # the per-instance User row still needs its own hashed_pw, same as the self-service join flow


@router.post("/instances/{instance_id}/members", response_model=MembershipOut, status_code=201)
def add_member_to_instance(instance_id: str, body: AddMemberRequest, admin: GlobalUser = Depends(get_current_global_admin)):
    """
    The direct, admin-initiated equivalent of the self-service invite-
    code join flow — same underlying steps (Membership + a synced local
    User row in that instance's own database), but for an admin adding
    someone by username directly, and with a real choice of role
    instead of always defaulting to viewer.
    """
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(sorted(VALID_ROLES))}")

    reg_db = RegistrySessionLocal()
    try:
        instance = reg_db.query(Instance).filter(Instance.id == instance_id).first()
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        target = reg_db.query(GlobalUser).filter(GlobalUser.username == body.username).first()
        if not target:
            raise HTTPException(status_code=404, detail=f"No global account found for username '{body.username}'")
        existing = reg_db.query(Membership).filter(
            Membership.user_id == target.id, Membership.instance_id == instance_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"{body.username} is already a member of this instance")

        membership = Membership(user_id=target.id, instance_id=instance_id, role=body.role)
        reg_db.add(membership)
        reg_db.commit()
        reg_db.refresh(membership)

        from ..instance_registry import get_engine_for_instance
        from ..models import User
        from sqlalchemy.orm import sessionmaker
        from .auth import _get_crypt
        engine = get_engine_for_instance(instance.db_filename)
        InstanceSession = sessionmaker(bind=engine)
        inst_db = InstanceSession()
        try:
            crypt = _get_crypt()
            local_user = User(
                username=target.username, email=target.email,
                hashed_pw=crypt.hash(body.member_password), role=body.role,
            )
            inst_db.add(local_user)
            inst_db.commit()
        finally:
            inst_db.close()

        logger.info("Global admin %s added %s to instance %s as %s", admin.username, target.username, instance_id, body.role)
        return MembershipOut(
            membership_id=membership.id, user_id=target.id, username=target.username,
            email=target.email, role=membership.role, joined_at=membership.joined_at,
        )
    finally:
        reg_db.close()


class UpdateMembershipRequest(BaseModel):
    role: str


@router.patch("/memberships/{membership_id}", response_model=MembershipOut)
def update_membership_role(membership_id: str, body: UpdateMembershipRequest, admin: GlobalUser = Depends(get_current_global_admin)):
    """
    Changes BOTH the registry's own Membership.role and that instance's
    local User.role — these are two separate columns in two separate
    databases that started out matching (both set the same way at
    join/add time) but nothing kept them in sync afterward, since no
    endpoint before this one could change either after creation. Left
    to drift, that's exactly the kind of two-sources-of-truth bug that
    surfaces much later as "why does the panel say admin but the
    instance itself still treats them as a viewer."
    """
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(sorted(VALID_ROLES))}")

    reg_db = RegistrySessionLocal()
    try:
        membership = reg_db.query(Membership).filter(Membership.id == membership_id).first()
        if not membership:
            raise HTTPException(status_code=404, detail="Membership not found")
        instance = reg_db.query(Instance).filter(Instance.id == membership.instance_id).first()
        target = reg_db.query(GlobalUser).filter(GlobalUser.id == membership.user_id).first()

        membership.role = body.role
        reg_db.commit()

        from ..instance_registry import get_engine_for_instance
        from ..models import User
        from sqlalchemy.orm import sessionmaker
        engine = get_engine_for_instance(instance.db_filename)
        InstanceSession = sessionmaker(bind=engine)
        inst_db = InstanceSession()
        try:
            local_user = inst_db.query(User).filter(User.username == target.username).first()
            if local_user:
                local_user.role = body.role
                inst_db.commit()
        finally:
            inst_db.close()

        logger.info("Global admin %s changed %s's role on instance %s to %s", admin.username, target.username, instance.id, body.role)
        return MembershipOut(
            membership_id=membership.id, user_id=target.id, username=target.username,
            email=target.email, role=membership.role, joined_at=membership.joined_at,
        )
    finally:
        reg_db.close()


@router.delete("/memberships/{membership_id}")
def remove_membership(membership_id: str, admin: GlobalUser = Depends(get_current_global_admin)):
    """
    Removes access to this instance going forward (deletes the registry
    Membership, so the person can no longer switch into it) but
    deliberately leaves that instance's own local User row alone —
    anything they submitted there (notes, comments, upload attribution)
    stays correctly attributed to a real user rather than becoming an
    orphaned reference. This is a real, permanent revoke of the person's
    ability to reach that instance, not a soft/reversible flag — re-
    adding them later requires a fresh add-member call.
    """
    reg_db = RegistrySessionLocal()
    try:
        membership = reg_db.query(Membership).filter(Membership.id == membership_id).first()
        if not membership:
            raise HTTPException(status_code=404, detail="Membership not found")
        username = membership.user.username
        instance_id = membership.instance_id
        reg_db.delete(membership)
        reg_db.commit()
        logger.info("Global admin %s removed %s from instance %s", admin.username, username, instance_id)
        return {"ok": True}
    finally:
        reg_db.close()


@router.delete("/instances/{instance_id}")
def delete_instance(instance_id: str, admin: GlobalUser = Depends(get_current_global_admin)):
    """
    Deletes the instance's registry row and every membership pointing
    at it (cascade, per the model's own relationship) — deliberately
    does NOT delete the instance's actual .db file on disk. Recordings,
    detections, a whole location's history living in that file is real
    data nobody should lose to one accidental click in a panel;
    removing the registry entry only means nobody can reach it through
    the app anymore. An admin who genuinely wants the file gone too can
    still do that directly on the server, a deliberately separate and
    harder-to-do-by-accident step.
    """
    reg_db = RegistrySessionLocal()
    try:
        instance = reg_db.query(Instance).filter(Instance.id == instance_id).first()
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        name = instance.name
        db_filename = instance.db_filename
        reg_db.delete(instance)
        reg_db.commit()
        logger.info("Global admin %s deleted instance %s (%s) — database file %s left on disk untouched", admin.username, name, instance_id, db_filename)
        return {"ok": True, "note": f"Registry entry removed. The instance's database file ({db_filename}) was left on disk."}
    finally:
        reg_db.close()


# ── Users ────────────────────────────────────────────────────────────────

class AdminUserOut(BaseModel):
    id: str
    username: str
    email: Optional[str]
    active: bool
    is_global_admin: bool
    created_at: datetime
    last_login: Optional[datetime]
    instance_count: int


@router.get("/users", response_model=List[AdminUserOut])
def list_all_users(admin: GlobalUser = Depends(get_current_global_admin)):
    reg_db = RegistrySessionLocal()
    try:
        out = []
        for u in reg_db.query(GlobalUser).order_by(GlobalUser.created_at.desc()).all():
            instance_count = reg_db.query(Membership).filter(Membership.user_id == u.id).count()
            out.append(AdminUserOut(
                id=u.id, username=u.username, email=u.email, active=u.active,
                is_global_admin=u.is_global_admin, created_at=u.created_at,
                last_login=u.last_login, instance_count=instance_count,
            ))
        return out
    finally:
        reg_db.close()


class UpdateUserRequest(BaseModel):
    active: Optional[bool] = None
    is_global_admin: Optional[bool] = None


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(user_id: str, body: UpdateUserRequest, admin: GlobalUser = Depends(get_current_global_admin)):
    reg_db = RegistrySessionLocal()
    try:
        target = reg_db.query(GlobalUser).filter(GlobalUser.id == user_id).first()
        if not target:
            raise HTTPException(status_code=404, detail="User not found")

        # Same "can't demote the last admin" protection chirp-server's own
        # require_admin role-change endpoint already has, one level up —
        # applies to both losing global-admin status and being deactivated,
        # since either one would leave the server with zero people able to
        # reach this panel at all.
        would_remove_admin_access = (
            (body.is_global_admin is False and target.is_global_admin) or
            (body.active is False and target.is_global_admin)
        )
        if would_remove_admin_access:
            remaining = reg_db.query(GlobalUser).filter(
                GlobalUser.is_global_admin == True, GlobalUser.active == True, GlobalUser.id != target.id  # noqa: E712
            ).count()
            if remaining == 0:
                raise HTTPException(status_code=400, detail="Cannot remove the last global admin's access")

        if body.active is not None:
            target.active = body.active
        if body.is_global_admin is not None:
            target.is_global_admin = body.is_global_admin
        reg_db.commit()

        logger.info("Global admin %s updated user %s: active=%s is_global_admin=%s", admin.username, target.username, target.active, target.is_global_admin)
        instance_count = reg_db.query(Membership).filter(Membership.user_id == target.id).count()
        return AdminUserOut(
            id=target.id, username=target.username, email=target.email, active=target.active,
            is_global_admin=target.is_global_admin, created_at=target.created_at,
            last_login=target.last_login, instance_count=instance_count,
        )
    finally:
        reg_db.close()


@router.get("/tailscale-status")
def get_tailscale_status(request: Request, admin: GlobalUser = Depends(get_current_global_admin)):
    """
    Same status shape as chirp-server's own /settings/tailscale-status —
    read-only, sourced from the already-running TailscaleManager on
    app.state (see main.py's own startup wiring). Global-admin only,
    since this is server-wide, not any one instance's business.
    """
    mgr = request.app.state.tailscale_manager if hasattr(request.app.state, "tailscale_manager") else None
    if mgr is None:
        return {"enabled": False, "binary_installed": False, "connected": False, "ip": None, "login_server": None}
    return mgr.status()


@router.get("/headscale-nodes")
def get_headscale_nodes(admin: GlobalUser = Depends(get_current_global_admin)):
    """
    Who's actually connected to the bundled self-hosted Headscale
    server right now — every node it knows about, online/offline,
    last seen, assigned tailnet IPs. Only meaningful when using the
    bundled Headscale (not a real Tailscale.com account); see
    headscale_admin_client.py's own docstring for the full reasoning
    on reachability and auth. Global-admin only, matching the
    tailscale-status endpoint above — this is server-wide infrastructure,
    not any one instance's own data.
    """
    from ..services.headscale_admin_client import get_nodes
    try:
        return get_nodes()
    except Exception as e:
        # get_nodes() itself is documented "never raises", but this is
        # the last line of defense anyway — a "who's connected" panel
        # failing should never turn into a 500 for the whole admin
        # page. Reported directly, with a real 500 traced to a gap in
        # that promise (see headscale_admin_client.py's own history).
        logger.warning("Unexpected error getting Headscale nodes: %s", e)
        return {"available": True, "nodes": [], "error": str(e)}


class TailscaleConfigBody(BaseModel):
    enabled: bool = False
    auth_key: Optional[str] = None
    login_server: Optional[str] = ""
    hostname: Optional[str] = ""


@router.post("/tailscale-config")
def save_tailscale_config(body: TailscaleConfigBody, request: Request, admin: GlobalUser = Depends(get_current_global_admin)):
    """
    Global Admin's "Save & Connect" — persists to RegistrySettings (the
    server-wide singleton, not any one instance's own AppSettings — see
    that model's own docstring for why) and applies it live via
    TailscaleManager.reconfigure(), same as chirp-server's own
    equivalent endpoint. auth_key masking follows the same convention:
    a value still containing '*' (the frontend's masked placeholder
    echoed back unchanged) or a blank value both mean "keep what's
    already saved", not "clear it".
    """
    reg_db = RegistrySessionLocal()
    try:
        s = reg_db.query(RegistrySettings).filter(RegistrySettings.id == 1).first()
        if not s:
            s = RegistrySettings(id=1)
            reg_db.add(s)

        auth_key = body.auth_key
        if auth_key is not None and "*" in auth_key:
            auth_key = s.tailscale_auth_key
        elif auth_key is None or auth_key == "":
            auth_key = s.tailscale_auth_key

        s.tailscale_enabled = body.enabled
        s.tailscale_auth_key = auth_key
        s.tailscale_login_server = body.login_server or ""
        s.tailscale_hostname = body.hostname or ""
        reg_db.commit()

        mgr = request.app.state.tailscale_manager if hasattr(request.app.state, "tailscale_manager") else None
        if mgr is None:
            raise HTTPException(status_code=500, detail="Tailscale manager not available")
        if body.enabled and not auth_key:
            raise HTTPException(status_code=400, detail="An auth key is required to enable Tailscale.")
        logger.info("Global admin %s updated server-wide Tailscale config (enabled=%s)", admin.username, body.enabled)
        return mgr.reconfigure(enabled=body.enabled, auth_key=auth_key or "", login_server=s.tailscale_login_server, hostname=s.tailscale_hostname)
    finally:
        reg_db.close()


class HeadscaleBasicAuthBody(BaseModel):
    enabled: bool = False
    username: Optional[str] = None
    # Plaintext, write-only — hashed server-side below, never stored or
    # echoed back as-is. A value containing "*" (the frontend's masked
    # placeholder for "a password is already saved") or a blank value
    # both mean "keep the existing hash", matching the auth_key masking
    # convention above.
    password: Optional[str] = None


@router.get("/headscale-basic-auth")
def get_headscale_basic_auth(admin: GlobalUser = Depends(get_current_global_admin)):
    """Current state for Global Admin's Network tab — never returns the
    password hash itself, just whether one is set."""
    reg_db = RegistrySessionLocal()
    try:
        s = reg_db.query(RegistrySettings).filter(RegistrySettings.id == 1).first()
        return {
            "enabled": bool(s.headscale_basic_auth_enabled) if s else False,
            "username": (s.headscale_basic_auth_username if s else None) or "",
            "password_set": bool(s and s.headscale_basic_auth_password_hash),
        }
    finally:
        reg_db.close()


@router.post("/headscale-basic-auth")
def save_headscale_basic_auth(body: HeadscaleBasicAuthBody, admin: GlobalUser = Depends(get_current_global_admin)):
    """
    Password-protects Headscale's own public helper pages (/apple,
    /windows, /linux) via Caddy, live — no container restart, no
    manual Caddyfile editing, no `caddy hash-password` on the command
    line. See app/services/caddy_config_manager.py for exactly how
    this reaches Caddy and why it survives a restart too.
    """
    import bcrypt as _bcrypt_lib
    from ..services.caddy_config_manager import push_live_config

    reg_db = RegistrySessionLocal()
    try:
        s = reg_db.query(RegistrySettings).filter(RegistrySettings.id == 1).first()
        if not s:
            s = RegistrySettings(id=1)
            reg_db.add(s)

        password_hash = s.headscale_basic_auth_password_hash
        if body.password and "*" not in body.password:
            password_hash = _bcrypt_lib.hashpw(body.password[:72].encode(), _bcrypt_lib.gensalt()).decode()

        if body.enabled and (not body.username or not password_hash):
            raise HTTPException(status_code=400, detail="A username and password are required to enable this.")

        s.headscale_basic_auth_enabled = body.enabled
        s.headscale_basic_auth_username = body.username or ""
        s.headscale_basic_auth_password_hash = password_hash
        reg_db.commit()

        result = push_live_config(body.enabled, s.headscale_basic_auth_username, password_hash)
        if not result["ok"]:
            # The setting is still saved — Caddy just couldn't be
            # reached to apply it live right now (e.g. mid-restart).
            # Surface this clearly rather than claim success.
            raise HTTPException(
                status_code=502,
                detail=f"Saved, but couldn't push the change to Caddy live: {result['error']}. It will still take effect next time Caddy restarts.",
            )

        logger.info("Global admin %s updated Headscale Basic Auth (enabled=%s)", admin.username, body.enabled)
        return {"enabled": body.enabled, "username": s.headscale_basic_auth_username, "password_set": bool(password_hash)}
    finally:
        reg_db.close()


@router.get("/instances/{instance_id}/diagnostics")
def run_instance_diagnostics(
    instance_id: str,
    mode: str = "full",
    ssh_password: str = "",
    admin: GlobalUser = Depends(get_current_global_admin),
):
    """
    The same diagnostics engine every location's own Settings page
    already runs against itself (see diagnostics.py's _run_checks) —
    reused here directly rather than reimplemented, so results can
    never drift between "diagnostics run from inside a location" and
    "diagnostics run for that same location from Global Admin". The
    only new part is opening a SPECIFIC instance's own database on
    demand (by id, picked from a dropdown) rather than relying on
    whichever instance a request's own JWT happens to be scoped to —
    Global Admin has no such scoping by design, since it manages every
    instance, not one.
    """
    from ..instance_registry import _get_instance_by_id, get_engine_for_instance
    from sqlalchemy.orm import sessionmaker
    from .diagnostics import _run_checks

    instance = _get_instance_by_id(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    engine = get_engine_for_instance(instance.db_filename)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        result = _run_checks(db, mode=mode, ssh_password=ssh_password)
        logger.info("Global admin %s ran '%s' diagnostics for instance %s (%s)", admin.username, mode, instance.id, instance.name)
        return result
    finally:
        db.close()
