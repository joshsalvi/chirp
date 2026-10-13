"""
Registry models — the only new database schema this whole design adds.
Every other model (Recording, Detection, BirdProfile, the per-instance
User, all 16 of chirp-server's real existing tables) is completely
unmodified, living inside each instance's own separate database.

See registry_db.py for why this is a fully separate engine/session from
the per-instance database.py, and ARCHITECTURE.md for the full design.
"""
import uuid
import secrets
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, Integer, ForeignKey, Float, Text
from sqlalchemy.orm import relationship
from .registry_db import RegistryBase


def new_uuid():
    return str(uuid.uuid4())


def new_invite_code():
    # 8 real random alphanumeric characters, uppercase — short enough to
    # read aloud or type by hand, long enough (36^8 ≈ 2.8 trillion) that
    # guessing one isn't a real concern for something an admin is meant
    # to share deliberately, not something exposed to brute-forcing (the
    # join endpoint also rate-limits, same reasoning as login).
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I — avoids read-aloud ambiguity
    return "".join(secrets.choice(alphabet) for _ in range(8))


class Instance(RegistryBase):
    """
    One real location — one real, separate SQLite database file. Created
    either by an admin standing up the first location, or self-service
    by any authenticated user adding a new one of their own (see
    ARCHITECTURE.md's "Creating and joining instances").
    """
    __tablename__ = "instances"

    id = Column(String, primary_key=True, default=new_uuid)
    name = Column(String, nullable=False)                    # display name, e.g. "Natick Backyard"
    location_name = Column(String, nullable=True)             # matches chirp-server's own AppSettings.location_name
    db_filename = Column(String, nullable=False, unique=True)  # relative filename under the instances/ dir — deliberately not a full path stored in the DB, so the data directory can be relocated without a migration
    invite_code = Column(String, nullable=False, unique=True, default=new_invite_code, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by_user_id = Column(String, ForeignKey("global_users.id"), nullable=True)

    memberships = relationship("Membership", back_populates="instance", cascade="all, delete-orphan")


class GlobalUser(RegistryBase):
    """
    The real login identity — one account, not one per instance. What
    "a single login, switch between locations" actually means
    underneath. Deliberately minimal: this is NOT where profile fields,
    notification prefs, or iNaturalist tokens live — those stay exactly
    where they already are today, on each instance's own local (and
    completely unmodified) User row, since that's what all of
    chirp-server's existing, real code already reads from.
    """
    __tablename__ = "global_users"

    id = Column(String, primary_key=True, default=new_uuid)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, nullable=True)
    hashed_pw = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    active = Column(Boolean, default=True)
    # Server-wide super-admin — sees and manages every instance and every
    # global account on this server, not just their own memberships.
    # Deliberately separate from any per-instance "admin" role (Membership
    # .role): being the admin of one location says nothing about anyone
    # else's location. Bootstrapped via CHIRP_GLOBAL_ADMIN_USERNAME (see
    # main.py's startup) rather than requiring direct database access to
    # set the first one — ongoing changes after that go through the
    # panel itself (an existing global admin can promote/demote others).
    is_global_admin = Column(Boolean, default=False)

    memberships = relationship("Membership", back_populates="user", cascade="all, delete-orphan")


class Membership(RegistryBase):
    """
    The real join table: which real login can reach which real
    instance, and what role they hold THERE specifically — matches
    chirp-server's own existing admin/submitter/viewer roles, but scoped
    per-instance, since being an admin of one location shouldn't imply
    anything about a different one the same person also happens to
    belong to.
    """
    __tablename__ = "memberships"

    id = Column(String, primary_key=True, default=new_uuid)
    user_id = Column(String, ForeignKey("global_users.id"), nullable=False, index=True)
    instance_id = Column(String, ForeignKey("instances.id"), nullable=False, index=True)
    role = Column(String, default="viewer")  # "admin" | "submitter" | "viewer" — same real values as chirp-server's own User.role
    joined_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("GlobalUser", back_populates="memberships")
    instance = relationship("Instance", back_populates="memberships")


class RegistrySettings(RegistryBase):
    """
    Server-wide settings that genuinely apply to the whole container,
    not any one instance — the opposite of AppSettings, which is
    deliberately per-instance (one row per location's own database).
    Singleton, id always 1, same convention as AppSettings itself.

    First (and so far only) use: Tailscale/Headscale. One Tailscale
    identity per container is shared by every instance it hosts — there
    is no meaningful answer to "which instance's Tailscale settings"
    the way there is for, say, eBird API keys, so this can't live in
    AppSettings the way chirp-server's own equivalent does. Configured
    from Global Admin only (not any individual instance's own Settings
    page, which only shows read-only status) — see admin_panel.py.
    """
    __tablename__ = "registry_settings"

    id = Column(Integer, primary_key=True, default=1)
    tailscale_enabled = Column(Boolean, default=False)
    tailscale_auth_key = Column(String, nullable=True)
    tailscale_login_server = Column(String, nullable=True)
    tailscale_hostname = Column(String, nullable=True)

    # Basic Auth in front of the bundled Headscale's own public helper
    # pages (/apple, /windows, /linux — setup instructions, no login of
    # Headscale's own) — pushed live to Caddy's admin API on every
    # change (see app/services/caddy_config_manager.py), not read by
    # Caddy directly; this table is Chirp's own record of the current
    # setting, not Caddy's. password_hash is bcrypt, never the
    # plaintext — see caddy_config_manager.py for why Python's bcrypt
    # output is safe to hand to Caddy's own Go bcrypt verification.
    headscale_basic_auth_enabled = Column(Boolean, default=False)
    headscale_basic_auth_username = Column(String, nullable=True)
    headscale_basic_auth_password_hash = Column(String, nullable=True)


class SiteRequest(RegistryBase):
    """A request from the public About page (api/site_requests.py), approved
    or denied in Global Admin → Requests.
    kind "hosted": a site on this server for a station the person builds;
      approval creates the account, the site and a device key.
    kind "relay": a self-hosted Chirp server that wants iPhone pushes;
      approval issues a push relay token (RelayServer).
    Either way the setup instructions are emailed to the requester."""
    __tablename__ = "site_requests"

    id = Column(String, primary_key=True, default=new_uuid)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    status = Column(String, default="pending", index=True)   # pending | approved | denied
    kind = Column(String, default="hosted")                   # hosted | relay
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    username = Column(String, nullable=True)                  # hosted only
    hashed_pw = Column(String, nullable=True)                 # hosted only; chosen at request time, becomes the account's password
    site_name = Column(String, nullable=False)
    server_url = Column(String, nullable=True)                # relay only: the self-hosted server's address
    location_name = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    timezone = Column(String, nullable=True)
    hardware = Column(Text, nullable=True)                    # what they're building (free text)
    message = Column(Text, nullable=True)
    ip = Column(String, nullable=True)
    decided_at = Column(DateTime, nullable=True)
    decided_by = Column(String, nullable=True)                # global admin username
    deny_reason = Column(Text, nullable=True)
    instance_id = Column(String, nullable=True)
    relay_server_id = Column(String, nullable=True)
    emailed_at = Column(DateTime, nullable=True)


class RelayServer(RegistryBase):
    """A self-hosted Chirp server allowed to send iPhone pushes through this
    server's APNs key (api/push_relay.py). Only a hash of its token is kept."""
    __tablename__ = "relay_servers"

    id = Column(String, primary_key=True, default=new_uuid)
    created_at = Column(DateTime, default=datetime.utcnow)
    name = Column(String, nullable=False)
    contact_email = Column(String, nullable=True)
    server_url = Column(String, nullable=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    active = Column(Boolean, default=True)
    last_used_at = Column(DateTime, nullable=True)
    sent_count = Column(Integer, default=0)

