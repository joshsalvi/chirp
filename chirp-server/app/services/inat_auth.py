"""
iNaturalist Token Auto-Refresh
==============================
Automates what would otherwise be a manual daily chore: JWTs from
https://www.inaturalist.org/users/api_token expire in 24h, and the only
documented way to get one is to be logged into a browser session there and
visit that URL directly.

Verified directly against pyinaturalist's actual implementation (not
assumed) — two real HTTP calls:
  1. POST https://www.inaturalist.org/oauth/token
     {"username", "password", "client_id", "client_secret", "grant_type": "password"}
     -> {"access_token": "..."}  (OAuth2 Resource Owner Password Credentials flow)
  2. GET https://www.inaturalist.org/users/api_token
     Authorization: Bearer <access_token>
     -> {"api_token": "..."}  (the actual JWT used elsewhere in this app)

Requires a one-time registered iNaturalist OAuth application (client_id +
client_secret) — created once at
https://www.inaturalist.org/oauth/applications/new, redirect_uri can be
anything since the password grant doesn't use it. This is a real
constraint: Chirp cannot fetch a JWT with only a username/password, the
same way pyinaturalist and every other client can't — iNaturalist requires
an app to exist for this flow regardless of client.

Runs on its own schedule (every REFRESH_INTERVAL_HOURS), refreshing well
before the 24h expiry. Stores the result on a User's personal
inat_api_token / inat_token_set_at (see InatAuthService.refresh_now's own
docstring for exactly which user) — NOT AppSettings.inat_api_token, which
was this module's original design but is a poor fit: the configured
credentials authenticate as one specific person's real iNaturalist
account, so the resulting token is inherently personal, not a
generic value meant to be shared server-wide.
"""

import logging
import threading
from datetime import datetime
from typing import Optional

logger = logging.getLogger("chirp.inat_auth")

INAT_BASE = "https://www.inaturalist.org"
INAT_API_BASE = "https://api.inaturalist.org/v1"
REFRESH_INTERVAL_HOURS = 12  # comfortably inside the 24h JWT expiry


def _utcnow() -> datetime:
    return datetime.utcnow()


def test_inat_token(token: str) -> dict:
    """
    Validates a token by calling iNaturalist's real /users/me endpoint —
    confirms the token is actually accepted right now (not just present),
    and returns the account it belongs to, which is more useful feedback
    for a "Test Connection" button than a bare yes/no. Raises on any
    failure (expired/invalid token, network error) — caller decides how to
    present that.
    """
    import httpx

    if not token or not token.strip():
        raise ValueError("No token configured")

    with httpx.Client(timeout=15) as client:
        resp = client.get(f"{INAT_API_BASE}/users/me",
                           headers={"Authorization": f"Bearer {token.strip()}"})
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or []
        if not results:
            raise ValueError("Token accepted but returned no user data — unexpected iNaturalist API response")
        user = results[0]
        return {"login": user.get("login"), "id": user.get("id"), "name": user.get("name")}


def fetch_inat_jwt(username: str, password: str, client_id: str, client_secret: str) -> str:
    """
    Real two-step exchange, verified against pyinaturalist's actual
    implementation. Raises on any failure — caller decides how to log/store it.
    """
    import httpx

    with httpx.Client(timeout=30) as client:
        oauth_resp = client.post(f"{INAT_BASE}/oauth/token", json={
            "username": username,
            "password": password,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "password",
        })
        oauth_resp.raise_for_status()
        access_token = oauth_resp.json()["access_token"]

        jwt_resp = client.get(f"{INAT_BASE}/users/api_token",
                               headers={"Authorization": f"Bearer {access_token}"})
        jwt_resp.raise_for_status()
        return jwt_resp.json()["api_token"]


def fetch_inat_jwt_via_login(username: str, password: str, remember_me: bool = True) -> str:
    """
    Alternative to fetch_inat_jwt() above, for accounts with no registered
    OAuth application — automates the same "log into a browser session
    and visit /users/api_token" method iNaturalist documents for getting
    a token by hand.

    Scrapes a real login form (standard Rails CSRF token, Devise sign-in
    convention) rather than a documented API contract, so it depends on
    iNaturalist's current login page structure and could change without
    notice. Verified end-to-end against the live site. Prefer
    fetch_inat_jwt() whenever an OAuth app is registered.
    """
    import re
    import httpx

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        login_page = client.get(f"{INAT_BASE}/login")
        login_page.raise_for_status()
        m = (re.search(r'meta-csrf-token:\s*([^\n]+)', login_page.text)
             or re.search(r'<meta name="csrf-token" content="([^"]+)"', login_page.text))
        if not m:
            raise RuntimeError(
                "Could not find a CSRF token on iNaturalist's login page -- "
                "their login page structure may have changed since this was written."
            )
        csrf_token = m.group(1).strip()

        form_data = {
            "authenticity_token": csrf_token,
            "user[email]": username,
            "user[password]": password,
        }
        if remember_me:
            form_data["user[remember_me]"] = "1"

        signin_resp = client.post(f"{INAT_BASE}/users/sign_in", data=form_data)
        signin_resp.raise_for_status()
        # A failed login redirects back to the sign-in page rather than
        # returning a 4xx -- Devise's default behavior. Detect that rather
        # than trusting a 200 status alone (which a failed attempt still
        # gets, on the re-rendered form).
        if "/login" in str(signin_resp.url) or "sign_in" in str(signin_resp.url):
            raise RuntimeError(
                "Login failed -- check the saved username/password (invalid "
                "credentials, or iNaturalist required a CAPTCHA/2FA step this can't automate)"
            )

        jwt_resp = client.get(f"{INAT_BASE}/users/api_token")
        jwt_resp.raise_for_status()
        data = jwt_resp.json()
        if "api_token" not in data:
            raise RuntimeError(f"Logged in, but /users/api_token didn't return the expected field: {data}")
        return data["api_token"]


class InatAuthService:
    """Background thread that keeps a user's personal inat_api_token fresh
    (see refresh_now() for exactly which user)."""

    def __init__(self):
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="inat-auth-refresh")
        self._thread.start()
        logger.info("iNaturalist token auto-refresh started (every %dh)", REFRESH_INTERVAL_HOURS)

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.refresh_now()
            except Exception as e:
                logger.warning("iNaturalist token refresh error: %s", e)
            self._stop.wait(REFRESH_INTERVAL_HOURS * 3600)

    def refresh_now(self, user_id: Optional[str] = None) -> bool:
        """
        Runs one refresh attempt immediately, regardless of schedule.
        Returns True if the token was actually refreshed, False if skipped
        (disabled or missing credentials) — distinct from raising, which
        means a refresh was attempted and failed.

        Writes the refreshed JWT to a USER's personal inat_api_token, not
        AppSettings.inat_api_token — the inat_username/password/OAuth
        credentials used here authenticate as one specific person's real
        iNaturalist account, so the resulting token is that person's
        personal token, not a generic server-wide fallback value shared by
        everyone.

        Credentials are resolved per-target-user: if that user has their
        OWN inat_username/password/OAuth app set on their own profile
        (User.inat_username etc — any submitter can set these, not just
        admins), those are used. Otherwise falls back to the global
        AppSettings credentials, same as before this option existed. If
        user_id is given (the manual "Refresh Now" button passes the
        actual logged-in user who clicked it — no ambiguity), that user's
        token is updated. If user_id is None (the unattended scheduled
        background refresh, which has no request/user context to draw
        from), falls back to the first admin user found and uses THAT
        admin's own credentials if set, else the global ones.
        """
        from ..database import SessionLocal
        from ..models import AppSettings, User

        def _target_user(db):
            if user_id:
                u = db.query(User).filter(User.id == user_id).first()
                if u:
                    return u
            # Picking "the first admin ever created" breaks the moment
            # more than one admin exists and the real owner's account
            # isn't literally the first — prefer whichever admin actually
            # has credentials set, checking each in creation order, only
            # falling back to "the first admin regardless" if none do.
            admins = db.query(User).filter(User.role == "admin").order_by(User.created_at).all()
            for a in admins:
                if a.inat_username and a.inat_password:
                    return a
            return admins[0] if admins else None

        with SessionLocal() as db:
            u = _target_user(db)
            if not u:
                return False
            enabled = True  # per-user credentials imply intent to use them; global toggle only gates the global fallback path below
            if u.inat_username and u.inat_password:
                username, password = u.inat_username, u.inat_password
                client_id, client_secret = u.inat_oauth_client_id, u.inat_oauth_client_secret  # optional — falls back to the login-scrape method below if either is missing
            else:
                s = db.query(AppSettings).filter(AppSettings.id == 1).first()
                enabled = bool(getattr(s, "inat_auto_refresh_enabled", False)) if s else False
                username = getattr(s, "inat_username", None) if s else None
                password = getattr(s, "inat_password", None) if s else None
                client_id = getattr(s, "inat_oauth_client_id", None) if s else None
                client_secret = getattr(s, "inat_oauth_client_secret", None) if s else None

        # An OAuth app (client_id/client_secret) gives the more reliable,
        # documented-API refresh path (fetch_inat_jwt). Without one, fall
        # back to fetch_inat_jwt_via_login — simulating the "log into a
        # browser session and visit /users/api_token" method by hand,
        # just automated. Less certain (a real login-page scrape, not a
        # versioned API contract) but means someone doesn't have to
        # register an OAuth app at all just to get auto-refresh.
        if not enabled or not username or not password:
            return False
        use_oauth = bool(client_id and client_secret)

        try:
            if use_oauth:
                jwt = fetch_inat_jwt(username, password, client_id, client_secret)
            else:
                jwt = fetch_inat_jwt_via_login(username, password)
        except Exception as e:
            with SessionLocal() as db:
                u = _target_user(db)
                if u:
                    u.inat_last_refresh_error = str(e)[:500]
                    db.commit()
            raise

        with SessionLocal() as db:
            u = _target_user(db)
            if not u:
                logger.warning("iNaturalist JWT refreshed but no target user found to store it on "
                                "(no admin user exists) — token discarded")
                return False
            u.inat_api_token = jwt
            u.inat_token_set_at = _utcnow()
            u.inat_last_refresh_error = None
            db.commit()
            logger.info("iNaturalist JWT refreshed successfully for user %s", u.username)
        return True


_service_instance: Optional[InatAuthService] = None


def get_service() -> InatAuthService:
    global _service_instance
    if _service_instance is None:
        _service_instance = InatAuthService()
    return _service_instance
