"""
Chirp Server — Authentication API
JWT-based auth. Enable via CHIRP_AUTH_ENABLED=true in .env.
Default admin credentials: admin / (set CHIRP_ADMIN_PASSWORD env var, default: chirp-admin).
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import User, ActivityLog
from ..services.activity_log import log_activity

logger = logging.getLogger("chirp.auth")

def _version_key(v: str) -> tuple:
    """"0.5.16.r" -> (0, 5, 16, 18); letters count like a, b, ... z, aa."""
    import re as _re
    m = _re.match(r"^(\d+)\.(\d+)\.(\d+)(?:\.([a-z]+))?$", (v or "").strip())
    if not m:
        return (-1,)
    n = 0
    for ch in m.group(4) or "":
        n = n * 26 + (ord(ch) - 96)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), n)

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


# ── Lazy imports (PyJWT/passlib only loaded if auth is enabled) ────────────────
import bcrypt as _bcrypt_lib

class _BcryptWrapper:
    """Direct bcrypt wrapper — avoids passlib version incompatibility with bcrypt 4.x.
    Hash format is identical so existing hashed passwords continue to work."""
    def hash(self, password: str) -> str:
        return _bcrypt_lib.hashpw(password[:72].encode(), _bcrypt_lib.gensalt()).decode()

    def verify(self, password: str, hashed: str) -> bool:
        try:
            return _bcrypt_lib.checkpw(password[:72].encode(), hashed.encode())
        except Exception:
            return False

_crypt_instance = _BcryptWrapper()

def _get_crypt():
    return _crypt_instance


def _get_jwt():
    # PyJWT (python-jose is unmaintained and has an unpatched critical CVE).
    # Tokens are plain HS256 either way, so ones issued before the switch
    # still verify. PyJWT warns when CHIRP_SECRET_KEY is under 32 bytes;
    # that warning would repeat on every request, so it's silenced here.
    import warnings
    import jwt
    warnings.filterwarnings("ignore", message="The HMAC key is")
    return jwt, jwt.PyJWTError


def create_access_token(data: dict, expires_minutes: int = 720) -> str:
    jwt, _ = _get_jwt()
    payload = {**data, "exp": datetime.utcnow() + timedelta(minutes=expires_minutes)}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def verify_token(token: str) -> Optional[dict]:
    jwt, JWTError = _get_jwt()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except Exception:
        return None


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Returns current user if token valid, or None if auth disabled."""
    # Always try to use the token if provided
    if token:
        payload = verify_token(token)
        if payload:
            user = db.query(User).filter(User.username == payload.get("sub")).first()
            if user and user.active:
                return user

    # Check if auth enforcement is required
    try:
        from ..models import AppSettings
        s = db.query(AppSettings).first()
        auth_on = bool(s.auth_enabled) if (s and s.auth_enabled is not None) else settings.auth_enabled
    except Exception:
        auth_on = settings.auth_enabled

    if auth_on:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return None


def require_admin(user: Optional[User] = Depends(get_current_user)):
    if user is None:
        return None   # auth disabled
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ── Startup: ensure admin user exists ────────────────────────────────────────

def ensure_default_admin(db: Session):
    """Create default admin user if none exists."""
    if not db.query(User).filter(User.role == "admin").first():
        pwd = settings.admin_password
        hashed = _get_crypt().hash(pwd)
        admin = User(
            id="admin",
            username="admin",
            email="admin@chirp.local",
            hashed_pw=hashed,
            role="admin",
        )
        db.add(admin)
        db.commit()
        logger.info("Created default admin user (username=admin)")


# ── Endpoints ─────────────────────────────────────────────────────────────────

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class UserCreate(BaseModel):
    username: str
    email: Optional[str] = None
    password: str
    role: str = "viewer"


class UserOut(BaseModel):
    id: str
    username: str
    email: Optional[str]
    role: str
    active: bool
    pending_approval: Optional[bool] = False
    created_at: datetime
    last_login: Optional[datetime]
    class Config: from_attributes = True


import time
from collections import defaultdict

# Real, in-memory brute-force protection — confirmed genuinely missing
# (activity_log.py records failed attempts for audit, but nothing
# actually blocked repeated ones). In-memory rather than a distributed
# rate limiter, deliberately: matches how this project is actually
# deployed, a single self-hosted instance, not a horizontally-scaled
# fleet where in-process state wouldn't be shared across replicas.
_failed_login_attempts: dict = defaultdict(list)  # key -> [timestamp, ...]
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300  # 5 minutes
# One address trying many user names (password spraying): 30 failures in
# 15 minutes blocks that address for every name.
_failed_by_ip: dict = defaultdict(list)
LOGIN_IP_MAX = 30
LOGIN_IP_WINDOW = 900
# Sign-up attempts from one address: 10 an hour.
_signups_by_ip: dict = defaultdict(list)
SIGNUP_IP_MAX = 10
SIGNUP_IP_WINDOW = 3600


def _note_failed_login(key: str, username: str = ""):
    ip = key.rsplit(":", 1)[-1] if ":" in key else key
    now = time.time()
    _failed_login_attempts[key].append(now)
    _failed_by_ip[ip].append(now)
    from ..security import note
    note("failed_login", ip, (username or "")[:40])


def check_signup_rate(request) -> None:
    """429 after SIGNUP_IP_MAX sign-up attempts from one address in an hour."""
    if request is None:
        return
    ip = client_address(request)
    now = time.time()
    recent = [t for t in _signups_by_ip[ip] if now - t < SIGNUP_IP_WINDOW]
    if len(recent) >= SIGNUP_IP_MAX:
        _signups_by_ip[ip] = recent
        from ..security import note
        note("signup_limited", ip)
        raise HTTPException(status_code=429, detail="Too many new accounts from this address. Try again in an hour.")
    recent.append(now)
    _signups_by_ip[ip] = recent


# ── Username matching ────────────────────────────────────────────────────
# iPhone keyboards capitalise the first letter and can add a trailing
# space, so "Josh " must find "josh". An exact match wins; otherwise a
# single case-insensitive match is accepted (two accounts differing only
# by case stay exact-only). New usernames are checked case-insensitively.
def find_by_username(db, model, name):
    name = (name or "").strip()
    if not name:
        return None
    user = db.query(model).filter(model.username == name).first()
    if user:
        return user
    hits = db.query(model).filter(func.lower(model.username) == name.lower()).limit(2).all()
    return hits[0] if len(hits) == 1 else None


def username_taken(db, model, name) -> bool:
    return db.query(model).filter(func.lower(model.username) == (name or "").strip().lower()).first() is not None


def _login_rate_limit_key(username: str, request: Request) -> str:
    # Keyed by username + client IP together, not either alone — username
    # alone would let an attacker distributed across many IPs still lock
    # out a legitimate account globally; IP alone would let one attacker
    # cycle through many different usernames with no real per-account limit.
    #
    # Behind Caddy/Cloudflare every request arrives from the proxy, so the
    # socket address is the same for everyone: one person's typos locked
    # that username for every phone. Use the address the proxy reports.
    return f"{(username or '').strip().lower()}:{client_address(request)}"


def client_address(request: Request) -> str:
    """The caller's address: Cloudflare's CF-Connecting-IP, else the first
    X-Forwarded-For hop (Caddy sets it), else the socket address."""
    h = request.headers
    ip = (h.get("cf-connecting-ip") or "").strip()
    if not ip:
        ip = (h.get("x-forwarded-for") or "").split(",")[0].strip()
    if not ip:
        ip = request.client.host if request.client else "unknown"
    return ip[:64]


def _check_login_rate_limit(key: str):
    now = time.time()
    ip = key.rsplit(":", 1)[-1] if ":" in key else key
    by_ip = [t for t in _failed_by_ip[ip] if now - t < LOGIN_IP_WINDOW]
    _failed_by_ip[ip] = by_ip
    if len(by_ip) >= LOGIN_IP_MAX:
        from ..security import note
        note("login_blocked", ip, "address")
        raise HTTPException(status_code=429, detail="Too many failed sign-ins from this address. Try again later.")
    attempts = [t for t in _failed_login_attempts[key] if now - t < LOGIN_WINDOW_SECONDS]
    _failed_login_attempts[key] = attempts
    if len(attempts) >= LOGIN_MAX_ATTEMPTS:
        from ..security import note
        note("login_blocked", ip, key.rsplit(":", 1)[0][:40])
        retry_after = int(LOGIN_WINDOW_SECONDS - (now - attempts[0]))
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Try again in {max(retry_after, 1)} seconds.",
        )


@router.post("/login", response_model=TokenOut)
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(),
          remember_me: bool = Form(False), db: Session = Depends(get_db)):
    rate_limit_key = _login_rate_limit_key(form.username, request)
    _check_login_rate_limit(rate_limit_key)

    crypt = _get_crypt()
    user = find_by_username(db, User, form.username)
    if not user or not crypt.verify(form.password, user.hashed_pw):
        _note_failed_login(rate_limit_key, form.username)
        log_activity(db, "login_failed", username=form.username, request=request)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.pending_approval is True:
        log_activity(db, "login_failed", user=user, request=request)
        raise HTTPException(status_code=403, detail="Account pending admin approval")
    if not user.active:
        log_activity(db, "login_failed", user=user, request=request)
        raise HTTPException(status_code=403, detail="Account disabled")
    _failed_login_attempts.pop(rate_limit_key, None)
    user.last_login = datetime.utcnow()
    db.commit()
    log_activity(db, "login", user=user, request=request)
    expires = 10080 if remember_me else 720  # 7 days vs 12h
    token = create_access_token({"sub": user.username, "role": user.role}, expires_minutes=expires)
    return TokenOut(access_token=token, username=user.username, role=user.role)


WATCH_TOKEN_DAYS = 30


@router.post("/watch-token")
def watch_token(token: str = Depends(oauth2_scheme), current_user=Depends(get_current_user)):
    """
    Sign-in for the Apple Watch app. The iPhone app asks for one when it
    opens and passes it to the watch. It lasts 30 days and only works for
    Live Detect (main.py's AuthMiddleware enforces that).
    """
    if current_user is None:
        return {"access_token": None, "auth_required": False}
    payload = verify_token(token) if token else None
    if not payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if payload.get("scope") == "watch":
        raise HTTPException(status_code=403, detail="A watch sign-in can't make another")
    claims = {k: payload[k] for k in ("sub", "global_user_id", "active_instance_id", "role") if k in payload}
    claims["scope"] = "watch"
    return {"access_token": create_access_token(claims, expires_minutes=WATCH_TOKEN_DAYS * 1440),
            "expires_days": WATCH_TOKEN_DAYS, "auth_required": True}


@router.get("/me")
def get_me(current_user=Depends(get_current_user)):
    if current_user is None:
        # Auth is disabled — return username=null and auth_required=false
        return {"id": "anon", "username": None, "role": "admin",
                "active": True, "auth_required": False,
                "created_at": datetime.utcnow().isoformat(), "last_login": None}
    # User is authenticated (either auth enabled with valid token,
    # or auth disabled but a valid token was provided anyway)
    from ..config import settings as cfg
    from ..database import SessionLocal
    auth_on = cfg.auth_enabled
    try:
        from ..models import AppSettings
        with SessionLocal() as db:
            s = db.query(AppSettings).first()
            if s and s.auth_enabled is not None:
                auth_on = bool(s.auth_enabled)
    except Exception:
        pass
    return {"id": current_user.id, "username": current_user.username,
            "role": current_user.role, "active": current_user.active,
            "auth_required": auth_on,
            "email": current_user.email,
            "notify_new_bird":     getattr(current_user, "notify_new_bird", True),
            "notify_daily_digest": getattr(current_user, "notify_daily_digest", False),
            "dashboard_mode": getattr(current_user, "dashboard_mode", None),
            "last_seen_whats_new_version": getattr(current_user, "last_seen_whats_new_version", None),
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
            "last_login": current_user.last_login.isoformat() if current_user.last_login else None}



class RegisterRequest(BaseModel):
    username: str
    email: Optional[str] = None
    password: str


@router.post("/register", status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db), request: Request = None):
    """
    Public registration endpoint. Creates account with pending_approval=True and active=False.
    An admin must approve the account before the user can log in.
    """
    check_signup_rate(request)
    body.username = body.username.strip()
    if not body.username:
        raise HTTPException(400, "Username required")
    if username_taken(db, User, body.username):
        raise HTTPException(400, "Username already taken")
    if len(body.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    import uuid
    user = User(
        id=str(uuid.uuid4()),
        username=body.username,
        email=body.email,
        hashed_pw=_get_crypt().hash(body.password),
        role="viewer",
        active=False,          # not active until approved
        pending_approval=True,
    )
    db.add(user)
    db.commit()
    logger.info("New registration pending approval: %s", body.username)
    # Notify admin via email (background - never blocks registration)
    try:
        from ..services.email_service import notify_new_registration
        notify_new_registration(db, body.username, body.email)
    except Exception as _e:
        logger.debug("Registration email failed: %s", _e)
    return {"status": "pending", "message": "Account created — awaiting admin approval."}


@router.post("/users/{user_id}/approve")
def approve_user(user_id: str, current_user=Depends(require_admin), db: Session = Depends(get_db)):
    """Admin: approve a pending registration."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    user.active = True
    user.pending_approval = False
    db.commit()
    return {"status": "approved", "username": user.username}


@router.get("/users", response_model=list[UserOut])
def list_users(current_user=Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.pending_approval.desc(), User.created_at.desc()).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, current_user=Depends(require_admin), db: Session = Depends(get_db)):
    body.username = body.username.strip()
    if not body.username:
        raise HTTPException(400, "Username required")
    if username_taken(db, User, body.username):
        raise HTTPException(400, "Username already exists")
    import uuid
    user = User(id=str(uuid.uuid4()), username=body.username, email=body.email,
                hashed_pw=_get_crypt().hash(body.password), role=body.role)
    db.add(user); db.commit(); db.refresh(user)
    return user


@router.put("/users/{user_id}/password")
def change_password(user_id: str, body: dict, current_user=Depends(require_admin),
                    db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user: raise HTTPException(404, "User not found")
    user.hashed_pw = _get_crypt().hash(body["password"])
    db.commit()
    return {"status": "ok"}


@router.put("/users/{user_id}/active")
def set_user_active(user_id: str, body: dict, current_user=Depends(require_admin),
                    db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user: raise HTTPException(404, "User not found")
    user.active = body.get("active", True)
    db.commit()
    return {"status": "ok"}


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: str, current_user=Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user: raise HTTPException(404, "Not found")
    db.delete(user); db.commit()


@router.put("/users/{user_id}/role")
def change_user_role(user_id: str, body: dict, current_user=Depends(require_admin),
                     db: Session = Depends(get_db)):
    """Admin: change a user's role."""
    new_role = body.get("role", "viewer")
    if new_role not in ("admin", "submitter", "viewer"):
        raise HTTPException(400, "Role must be admin, submitter, or viewer")
    user = db.query(User).filter(User.id == user_id).first()
    if not user: raise HTTPException(404, "User not found")
    # Prevent removing the last admin
    if user.role == "admin" and new_role != "admin":
        admin_count = db.query(User).filter(User.role == "admin", User.active == True).count()
        if admin_count <= 1:
            raise HTTPException(400, "Cannot demote the last admin account")
    user.role = new_role
    db.commit()
    return {"ok": True, "username": user.username, "role": user.role}

@router.put("/me/notification-prefs")
def update_notification_prefs(body: dict, request: Request, db: Session = Depends(get_db)):
    """Save per-user notification preferences.

    Identifies the user by:
      1. JWT Bearer token in Authorization header (auth enabled)
      2. Default admin user (auth disabled / open access)
    """
    user = None

    # Try JWT first
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = verify_token(token)
        if payload and payload.get("sub"):
            user = db.query(User).filter(User.username == payload["sub"]).first()

    # Fall back to default admin when auth is disabled or no token sent
    if user is None:
        user = db.query(User).filter(User.username == "admin").first()

    if user is None:
        raise HTTPException(status_code=404, detail="No user found to save preferences to")

    if "notify_new_bird" in body:
        user.notify_new_bird = bool(body["notify_new_bird"])
    if "notify_daily_digest" in body:
        user.notify_daily_digest = bool(body["notify_daily_digest"])
    db.commit()
    return {"ok": True, "notify_new_bird": user.notify_new_bird, "notify_daily_digest": user.notify_daily_digest}



# ── User self-service profile ──────────────────────────────────────────────────

class ProfileUpdateRequest(BaseModel):
    display_name:        Optional[str]  = None
    email:               Optional[str]  = None
    current_password:    Optional[str]  = None
    new_password:        Optional[str]  = None
    notify_new_bird:     Optional[bool] = None
    notify_daily_digest: Optional[bool] = None
    dashboard_mode:      Optional[str]  = None  # 'simplified' | 'detailed'
    last_seen_whats_new_version: Optional[str] = None
    inat_api_token:      Optional[str]  = None  # per-user iNat token (submitters)
    inat_username:       Optional[str]  = None  # per-user OAuth auto-refresh — this user's own iNat account
    inat_password:       Optional[str]  = None
    inat_oauth_client_id: Optional[str] = None
    inat_oauth_client_secret: Optional[str] = None


@router.get("/me/profile")
def get_my_profile(request: Request, db: Session = Depends(get_db)):
    """Return the current user's full profile for the self-service page."""
    user = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        payload = verify_token(auth_header[7:])
        if payload and payload.get("sub"):
            user = db.query(User).filter(User.username == payload["sub"]).first()
    if user is None:
        user = db.query(User).filter(User.username == "admin").first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    def _mask(v):
        if not v: return ""
        return v[:4] + "****" + v[-4:] if len(v) > 8 else "****"

    return {
        "id":                  user.id,
        "username":            user.username,
        "display_name":        getattr(user, "display_name", None),
        "email":               user.email if user.email and not user.email.endswith("@chirp.local") else "",
        "role":                user.role,
        "created_at":          user.created_at.isoformat() if user.created_at else None,
        "last_login":          user.last_login.isoformat() if user.last_login else None,
        "notify_new_bird":     getattr(user, "notify_new_bird", True),
        "notify_daily_digest": getattr(user, "notify_daily_digest", False),
        "inat_api_token":      _mask(getattr(user, "inat_api_token", None)),
        "has_inat_token":      bool(getattr(user, "inat_api_token", None)),
        "inat_username":       getattr(user, "inat_username", None) or "",
        "has_inat_oauth":      bool(getattr(user, "inat_username", None) and getattr(user, "inat_oauth_client_id", None)),
        "inat_token_set_at":   user.inat_token_set_at.isoformat() if getattr(user, "inat_token_set_at", None) else None,
        "inat_last_refresh_error": getattr(user, "inat_last_refresh_error", None),
        "photo_url":           getattr(user, "photo_url", None),
    }



@router.put("/me/photo")
def update_profile_photo(
    request: Request,
    db: Session = Depends(get_db),
    photo: UploadFile = File(None),
    photo_url: str = Form(None),
):
    """Upload a profile photo (file) or set a photo by URL."""
    user = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        payload = verify_token(auth_header[7:])
        if payload and payload.get("sub"):
            user = db.query(User).filter(User.username == payload["sub"]).first()
    if user is None:
        user = db.query(User).filter(User.username == "admin").first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    import os, shutil
    from ..config import settings as cfg

    if photo and photo.filename:
        # Save uploaded photo to data directory
        photos_dir = os.path.join(cfg.data_dir, "user_photos")
        os.makedirs(photos_dir, exist_ok=True)
        ext = os.path.splitext(photo.filename)[-1].lower()
        if ext not in _PHOTO_EXTS:
            ext = ".jpg"
        # One photo per user: drop the old one if it had another extension.
        for old in _PHOTO_EXTS:
            if old != ext:
                try:
                    os.remove(os.path.join(photos_dir, f"{user.id}_photo{old}"))
                except OSError:
                    pass
        dest = os.path.join(photos_dir, f"{user.id}_photo{ext}")
        with open(dest, "wb") as f:
            shutil.copyfileobj(photo.file, f)
        # ?v= changes with each upload, so the day-long cache below
        # doesn't keep showing the previous photo.
        import time as _time
        user.photo_url = f"/api/v1/auth/me/photo/{user.id}{ext}?v={int(_time.time())}"
    elif photo_url:
        user.photo_url = photo_url.strip()

    db.commit()
    return {"ok": True, "photo_url": user.photo_url}


_PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic")


@router.get("/me/photo/{name}")
def serve_user_photo(name: str):
    """Serve an uploaded profile photo: /me/photo/{user id}{.ext}. (The route
    was "{user_id}{ext:path}", which put the extension inside user_id, so
    every uploaded photo 404'd.)"""
    import os
    import re as _re
    from fastapi.responses import FileResponse
    from ..config import settings as cfg
    user_id, ext = os.path.splitext(name)
    if not _re.fullmatch(r"[A-Za-z0-9-]{1,64}", user_id):
        raise HTTPException(status_code=404, detail="Photo not found")
    photos_dir = os.path.join(cfg.data_dir, "user_photos")
    exts = ([ext.lower()] if ext.lower() in _PHOTO_EXTS else []) + list(_PHOTO_EXTS)
    for e in exts:
        p = os.path.join(photos_dir, f"{user_id}_photo{e}")
        if os.path.exists(p):
            # A user's avatar rarely changes; uploads add ?v= to bust this.
            return FileResponse(p, headers={"Cache-Control": "public, max-age=86400"})
    raise HTTPException(status_code=404, detail="Photo not found")

@router.put("/me/profile")
def update_my_profile(body: ProfileUpdateRequest, request: Request, db: Session = Depends(get_db)):
    """Update the current user's profile — password, email, display name, notifications."""
    user = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        payload = verify_token(auth_header[7:])
        if payload and payload.get("sub"):
            user = db.query(User).filter(User.username == payload["sub"]).first()
    if user is None:
        user = db.query(User).filter(User.username == "admin").first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    crypt = _get_crypt()

    # Password change
    if body.new_password:
        if len(body.new_password) < 6:
            raise HTTPException(400, "Password must be at least 6 characters")
        # When auth is enabled, require current password
        from ..models import AppSettings
        s = db.query(AppSettings).first()
        auth_on = bool(s.auth_enabled) if s and s.auth_enabled is not None else False
        if auth_on:
            if not body.current_password:
                raise HTTPException(400, "Current password is required")
            if not crypt.verify(body.current_password, user.hashed_pw):
                raise HTTPException(400, "Current password is incorrect")
        user.hashed_pw = crypt.hash(body.new_password)
        # Send confirmation email
        try:
            from ..services.email_service import notify_password_changed
            notify_password_changed(db, user.username, user.email or "")
        except Exception:
            pass

    # Display name
    if body.display_name is not None:
        user.display_name = body.display_name.strip() or None

    # Email
    if body.email is not None:
        cleaned = body.email.strip()
        if cleaned and "@" not in cleaned:
            raise HTTPException(400, "Invalid email address")
        user.email = cleaned or None

    # Notification prefs
    if body.notify_new_bird is not None:
        user.notify_new_bird = body.notify_new_bird
    if body.notify_daily_digest is not None:
        user.notify_daily_digest = body.notify_daily_digest
    if body.dashboard_mode is not None:
        if body.dashboard_mode not in ("simplified", "detailed"):
            raise HTTPException(status_code=400, detail="dashboard_mode must be 'simplified' or 'detailed'")
        user.dashboard_mode = body.dashboard_mode
    if body.last_seen_whats_new_version is not None:
        # Never backwards: an older copy of the web app (cached page, another
        # device) would otherwise make the newer popup show again.
        cur = user.last_seen_whats_new_version
        if not cur or _version_key(body.last_seen_whats_new_version) >= _version_key(cur):
            user.last_seen_whats_new_version = body.last_seen_whats_new_version

    # Per-user iNaturalist token (submitters and admins)
    if body.inat_api_token is not None:
        cleaned_inat = body.inat_api_token.strip()
        # Ignore if sent back masked
        if cleaned_inat and "*" not in cleaned_inat:
            user.inat_api_token = cleaned_inat
        elif not cleaned_inat:
            user.inat_api_token = None  # allow clearing

    # Per-user iNaturalist OAuth auto-refresh credentials — any user can
    # set their own, not just admins, so their token stays fresh using
    # their own real iNaturalist account instead of relying on an admin's
    # global fallback credentials (see InatAuthService.refresh_now).
    if body.inat_username is not None:
        user.inat_username = body.inat_username.strip() or None
    if body.inat_password is not None and "*" not in body.inat_password:
        user.inat_password = body.inat_password.strip() or None
    if body.inat_oauth_client_id is not None:
        user.inat_oauth_client_id = body.inat_oauth_client_id.strip() or None
    if body.inat_oauth_client_secret is not None and "*" not in body.inat_oauth_client_secret:
        user.inat_oauth_client_secret = body.inat_oauth_client_secret.strip() or None

    db.commit()
    return {"ok": True, "username": user.username, "display_name": user.display_name, "email": user.email}


# ── Activity log ────────────────────────────────────────────────────────────
# See services/activity_log.py and models.ActivityLog for exactly what is
# and isn't recorded. Ping/logout are open to any authenticated user (they
# only ever log *their own* activity); the list/summary views are admin-only.

class ActivityPingIn(BaseModel):
    path: str


@router.post("/activity/ping")
def activity_ping(
    body: ActivityPingIn,
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lightweight page-view beacon, called by the frontend on route change.
    Fire-and-forget by design on the client side — this endpoint always
    returns 200 (activity logging failures are swallowed inside
    log_activity itself, never surfaced as an error the UI has to handle).
    In auth-disabled/single-user mode current_user is None; we still log
    the page view with user=None so a basic access trail exists, since
    there's no concept of "logging in" to distinguish in that mode.
    """
    log_activity(db, "page_view", user=current_user, path=body.path, request=request)
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """
    JWTs are stateless — there's no server-side session to invalidate, the
    frontend just discards the token. This endpoint exists purely to log the
    logout event for the activity log before that happens; best-effort, not
    required for the actual logout to work client-side.
    """
    if current_user is not None:
        log_activity(db, "logout", user=current_user, request=request)
    return {"ok": True}


class ActivityEventOut(BaseModel):
    id: str
    user_id: Optional[str]
    username: Optional[str]
    event_type: str
    path: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime
    class Config: from_attributes = True


@router.get("/activity", response_model=list[ActivityEventOut])
def list_activity(
    user_id: Optional[str] = None,
    event_type: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin-only. Paginated, filterable raw activity feed."""
    limit = max(1, min(limit, 500))
    q = db.query(ActivityLog)
    if user_id:
        q = q.filter(ActivityLog.user_id == user_id)
    if event_type:
        q = q.filter(ActivityLog.event_type == event_type)
    if since:
        q = q.filter(ActivityLog.created_at >= since)
    if until:
        q = q.filter(ActivityLog.created_at <= until)
    return (
        q.order_by(ActivityLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/activity/count")
def count_activity(
    user_id: Optional[str] = None,
    event_type: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin-only. Total count matching the same filters as /activity, for pagination UI."""
    q = db.query(ActivityLog)
    if user_id:
        q = q.filter(ActivityLog.user_id == user_id)
    if event_type:
        q = q.filter(ActivityLog.event_type == event_type)
    if since:
        q = q.filter(ActivityLog.created_at >= since)
    if until:
        q = q.filter(ActivityLog.created_at <= until)
    return {"count": q.count()}


@router.get("/activity/summary")
def activity_summary(days: int = 30, admin=Depends(require_admin), db: Session = Depends(get_db)):
    """
    Admin-only dashboard summary:
      - per_user: per-account login/page-view counts, last login, online-now flag
      - daily_logins: one count per day for the last `days` days (for a bar/line chart)
      - top_pages: most-visited paths in the window
      - recent_events: last 20 raw events across all users (live-feed style)
      - totals: quick top-line numbers
    """
    from sqlalchemy import func as _func
    days = max(1, min(days, 365))
    window_start = datetime.utcnow() - timedelta(days=days)
    online_cutoff = datetime.utcnow() - timedelta(minutes=5)

    all_users = db.query(User).all()
    login_counts = dict(
        db.query(ActivityLog.user_id, _func.count(ActivityLog.id))
        .filter(ActivityLog.event_type == "login", ActivityLog.created_at >= window_start)
        .group_by(ActivityLog.user_id)
        .all()
    )
    page_view_counts = dict(
        db.query(ActivityLog.user_id, _func.count(ActivityLog.id))
        .filter(ActivityLog.event_type == "page_view", ActivityLog.created_at >= window_start)
        .group_by(ActivityLog.user_id)
        .all()
    )
    last_activity = dict(
        db.query(ActivityLog.user_id, _func.max(ActivityLog.created_at))
        .filter(ActivityLog.user_id.isnot(None))
        .group_by(ActivityLog.user_id)
        .all()
    )

    per_user = []
    for u in all_users:
        last_act = last_activity.get(u.id)
        per_user.append({
            "user_id": u.id,
            "username": u.username,
            "role": u.role,
            "active": u.active,
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "login_count": login_counts.get(u.id, 0),
            "page_view_count": page_view_counts.get(u.id, 0),
            "last_activity": last_act.isoformat() if last_act else None,
            "online_now": bool(last_act and last_act >= online_cutoff),
        })
    per_user.sort(key=lambda r: r["last_activity"] or "", reverse=True)

    # Daily login counts for the window, zero-filled for days with no logins
    # (a sparse GROUP BY result would otherwise leave gaps in the chart).
    raw_daily = dict(
        db.query(
            _func.date(ActivityLog.created_at), _func.count(ActivityLog.id)
        )
        .filter(ActivityLog.event_type == "login", ActivityLog.created_at >= window_start)
        .group_by(_func.date(ActivityLog.created_at))
        .all()
    )
    daily_logins = []
    for i in range(days - 1, -1, -1):
        d = (datetime.utcnow() - timedelta(days=i)).date()
        daily_logins.append({"date": d.isoformat(), "count": raw_daily.get(d.isoformat(), 0)})

    top_pages = (
        db.query(ActivityLog.path, _func.count(ActivityLog.id).label("n"))
        .filter(ActivityLog.event_type == "page_view", ActivityLog.created_at >= window_start, ActivityLog.path.isnot(None))
        .group_by(ActivityLog.path)
        .order_by(_func.count(ActivityLog.id).desc())
        .limit(10)
        .all()
    )

    recent_events = (
        db.query(ActivityLog)
        .order_by(ActivityLog.created_at.desc())
        .limit(20)
        .all()
    )

    return {
        "window_days": days,
        "totals": {
            "logins": sum(login_counts.values()),
            "page_views": sum(page_view_counts.values()),
            "failed_logins": db.query(ActivityLog).filter(
                ActivityLog.event_type == "login_failed", ActivityLog.created_at >= window_start
            ).count(),
            "online_now": sum(1 for r in per_user if r["online_now"]),
            "total_users": len(all_users),
        },
        "per_user": per_user,
        "daily_logins": daily_logins,
        "top_pages": [{"path": p, "count": n} for p, n in top_pages],
        "recent_events": [
            {
                "id": e.id, "username": e.username, "event_type": e.event_type,
                "path": e.path, "ip_address": e.ip_address,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in recent_events
        ],
    }


# ── Account deletion (App Store guideline 5.1.1(v)) ─────────────────────────
class DeleteAccountRequest(BaseModel):
    password: str


def purge_local_user(db, user) -> None:
    """Remove one person's rows from a location database: push registrations,
    notifications inbox, activity log, the notes they wrote, and the user row.
    Recordings and detections belong to the site and stay."""
    from ..models import ActivityLog, ApnsDeviceToken, Comment, InboxNotification, PushSubscription
    for model in (PushSubscription, ApnsDeviceToken, InboxNotification, ActivityLog):
        db.query(model).filter(model.user_id == user.id).delete(synchronize_session=False)
    db.query(Comment).filter(Comment.author == user.username).delete(synchronize_session=False)
    db.delete(user)
    db.commit()


@router.post("/me/delete", status_code=200)
def delete_my_account(body: DeleteAccountRequest, token: str = Depends(oauth2_scheme),
                      db: Session = Depends(get_db)):
    """Permanently delete the signed-in account after re-checking its password.
    The last admin can't delete themselves (nobody could manage the server)."""
    payload = verify_token(token) if token else None
    user = db.query(User).filter(User.username == payload.get("sub")).first() if payload else None
    if not user:
        raise HTTPException(401, "Not authenticated")
    if not _get_crypt().verify(body.password, user.hashed_pw):
        raise HTTPException(403, "Wrong password")
    if user.role == "admin" and db.query(User).filter(User.role == "admin", User.active == True, User.id != user.id).count() == 0:  # noqa: E712
        raise HTTPException(409, "You're the only admin. Make someone else an admin before deleting your account.")
    username = user.username
    purge_local_user(db, user)
    logger.info("Account deleted by its owner: %s", username)
    return {"deleted": True}
