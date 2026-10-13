"""
Push relay: self-hosted Chirp servers send iPhone notifications through
this server, which signs them with the server-wide APNs key (CHIRP_APNS_*).
Apple only delivers pushes for the Chirp app when they are signed with
the app's key, so a server someone else runs can't send them directly.

  POST   /api/v1/push-relay/send           Bearer <relay token>; public path
  GET    /api/v1/admin/relay-servers       global admin
  POST   /api/v1/admin/relay-servers       global admin; returns the token once
  PATCH  /api/v1/admin/relay-servers/{id}  global admin; {active}
  DELETE /api/v1/admin/relay-servers/{id}  global admin

Only a SHA-256 hash of each token is stored. The relay never keeps device
tokens or message text; it forwards and answers whether the token is dead
so the sending server can drop it.
"""
import hashlib
import logging
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..registry_db import RegistrySessionLocal
from ..registry_models import GlobalUser, RelayServer
from .admin_panel import get_current_global_admin

logger = logging.getLogger("chirp.push_relay")
router = APIRouter(tags=["push-relay"])
admin_router = APIRouter(tags=["admin"])

TOKEN_PREFIX = "chirprelay_"
RATE_PER_HOUR = 600
_sent = defaultdict(deque)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(reg, name: str, contact_email: Optional[str] = None, server_url: Optional[str] = None):
    """Creates a RelayServer; returns (row, token). The token is shown once."""
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    row = RelayServer(name=name[:80], contact_email=contact_email, server_url=server_url, token_hash=_hash(token))
    reg.add(row)
    reg.flush()
    return row, token


class RelaySendIn(BaseModel):
    device_token: str
    payload: dict
    server: Optional[str] = None


@router.post("/send")
def relay_send(body: RelaySendIn, request: Request):
    from ..services.apns_push import deliver, platform_credentials
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not token.startswith(TOKEN_PREFIX):
        raise HTTPException(401, "Relay token required")
    creds = platform_credentials()
    if not creds:
        raise HTTPException(503, "This server has no APNs key set up for relaying.")
    if not (8 <= len(body.device_token) <= 200) or not all(c in "0123456789abcdefABCDEF" for c in body.device_token):
        raise HTTPException(400, "Invalid device token")
    payload = body.payload if isinstance(body.payload, dict) else {}
    aps = payload.get("aps") if isinstance(payload.get("aps"), dict) else None
    if not aps or len(str(payload)) > 3500:
        raise HTTPException(400, "Payload must be an APNs alert under 4 KB")
    if body.server:
        payload["server"] = body.server[:200]

    reg = RegistrySessionLocal()
    try:
        row = reg.query(RelayServer).filter(RelayServer.token_hash == _hash(token)).first()
        if not row or not row.active:
            raise HTTPException(401, "Relay token not recognized or revoked")
        q, now = _sent[row.id], time.time()
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= RATE_PER_HOUR:
            raise HTTPException(429, f"Relay limit is {RATE_PER_HOUR} pushes an hour")
        q.append(now)
        ok, detail, dead = deliver(creds, body.device_token, payload)
        row.last_used_at = datetime.utcnow()
        if ok:
            row.sent_count = (row.sent_count or 0) + 1
        reg.commit()
        return {"ok": ok, "error": detail, "dead": dead}
    finally:
        reg.close()


# ── Admin ────────────────────────────────────────────────────────────────

def _out(r: RelayServer) -> dict:
    return {"id": r.id, "name": r.name, "contact_email": r.contact_email, "server_url": r.server_url,
            "created_at": r.created_at, "active": r.active, "last_used_at": r.last_used_at,
            "sent_count": r.sent_count or 0}


@admin_router.get("")
def list_relays(admin: GlobalUser = Depends(get_current_global_admin)):
    from ..services.apns_push import platform_credentials
    reg = RegistrySessionLocal()
    try:
        rows = reg.query(RelayServer).order_by(RelayServer.created_at.desc()).all()
        return {"apns_ready": platform_credentials() is not None, "servers": [_out(r) for r in rows]}
    finally:
        reg.close()


class RelayIn(BaseModel):
    name: str
    contact_email: Optional[str] = None
    server_url: Optional[str] = None


@admin_router.post("", status_code=201)
def create_relay(body: RelayIn, admin: GlobalUser = Depends(get_current_global_admin)):
    if not body.name.strip():
        raise HTTPException(400, "Name required")
    reg = RegistrySessionLocal()
    try:
        row, token = issue_token(reg, body.name.strip(), (body.contact_email or "").strip() or None,
                                 (body.server_url or "").strip() or None)
        reg.commit()
        return {**_out(row), "token": token}
    finally:
        reg.close()


class RelayPatch(BaseModel):
    active: bool


@admin_router.patch("/{relay_id}")
def update_relay(relay_id: str, body: RelayPatch, admin: GlobalUser = Depends(get_current_global_admin)):
    reg = RegistrySessionLocal()
    try:
        row = reg.query(RelayServer).filter(RelayServer.id == relay_id).first()
        if not row:
            raise HTTPException(404, "Relay server not found")
        row.active = body.active
        reg.commit()
        return _out(row)
    finally:
        reg.close()


@admin_router.delete("/{relay_id}", status_code=204)
def delete_relay(relay_id: str, admin: GlobalUser = Depends(get_current_global_admin)):
    reg = RegistrySessionLocal()
    try:
        row = reg.query(RelayServer).filter(RelayServer.id == relay_id).first()
        if not row:
            raise HTTPException(404, "Relay server not found")
        reg.delete(row)
        reg.commit()
    finally:
        reg.close()
