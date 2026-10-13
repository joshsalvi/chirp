"""
Chirp Server Configuration
Reads from environment variables with sensible defaults.
"""
import secrets
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator, Field


def _read_version() -> str:
    """
    Canonical version lives in chirp-server/VERSION — i.e. ../VERSION
    relative to this file (app/config.py). This must match the real
    Docker container layout, not just a dev checkout: the Dockerfile
    does `WORKDIR /app` then `COPY VERSION ./VERSION` (giving
    /app/VERSION) and `COPY app/ ./app/` (giving /app/app/config.py),
    so from this file's own directory ../VERSION is exactly right.
    ../../VERSION was tried first previously, on the assumption the
    repo root was the right place for this file — that broke the real
    `docker build` entirely, since COPY VERSION ./VERSION in the
    Dockerfile resolves against the build context (chirp-server/, per
    docker-compose.yml's `context: .`), which is one level below the
    repo root and has no visibility into anything above it. A file
    that exists on a dev machine's disk one directory up is invisible
    to Docker's build process regardless of whether Python can `open()`
    it locally — confirmed by this exact failure: "COPY VERSION
    ./VERSION ... /VERSION: not found". ../VERSION and bare VERSION are
    both kept as fallbacks for robustness, but ../../VERSION is no
    longer tried at all, since relying on it being there is what caused
    this bug.

    Moved to module level (out of the Settings class body) and wired
    into a real app_version field below — previously defined as a
    staticmethod inside Settings but never actually referenced by any
    field, meaning the correctly-implemented version-reading logic was
    never actually reachable as settings.app_version or anywhere else.
    Confirmed via a direct search: zero references anywhere in the app
    before this fix. This is exactly the missing piece diagnostics
    needed for reporting the server's own version number.
    """
    import os
    for rel in ("../VERSION", "VERSION"):
        p = os.path.join(os.path.dirname(__file__), rel)
        try:
            return open(p).read().strip()
        except OSError:
            pass
    return "1.0.0"


class Settings(BaseSettings):
    # Security
    secret_key: str = secrets.token_hex(32)
    device_api_key: str = "chirp-device-key-change-me"

    # Server's own version — see _read_version() above for why this
    # wasn't actually accessible anywhere before this fix.
    app_version: str = Field(default_factory=_read_version)

    # External APIs
    ebird_api_key:    Optional[str] = None
    ebird_st_api_key: Optional[str] = None   # eBird Status & Trends Data Products key

    # Paths
    data_dir: str = "/app/data"
    recordings_dir: str = "/app/data/recordings"
    media_dir: str = "/app/data/media/birds"
    spectrograms_dir: str = "/app/data/spectrograms"
    clips_dir: str = "/app/data/clips"
    enhanced_dir: str = "/app/data/enhanced"   # cached "isolated bird call" audio
    bat_clips_dir: str = "/app/data/bat_clips"  # raw + downshifted bat-activity clips
    ai_models_dir: str = "/app/data/ai_models"  # downloaded AI Enhance model weights (persists across restarts)

    # Database
    db_url: str = "sqlite:////app/data/chirp.db"

    # Server
    host: str = "0.0.0.0"
    port: int = 8765
    debug: bool = False

    # Processing
    spectrogram_width: int = 1200
    spectrogram_height: int = 300
    spectrogram_dpi: int = 150
    clip_padding_seconds: float = 1.0   # Padding around each detection for clip export
    max_upload_mb: int = 500
    auth_enabled: bool = False          # Set CHIRP_AUTH_ENABLED=true to require login
    admin_password: str = "chirp-admin" # Set CHIRP_ADMIN_PASSWORD in production            # Max recording upload size

    # Bird enrichment
    enrich_on_upload: bool = True       # Auto-enrich new species after recording arrives
    media_download_enabled: bool = False  # Stream from source URLs instead of downloading

    # Tailscale/Headscale — gives this SERVER container a second, stable
    # IP reachable from anywhere on your tailnet, the same way
    # chirp-device already supports for the Pi (see tailscale_manager.py
    # in both places — this is the server-side counterpart, previously
    # missing entirely: a device could be reached over Tailscale, but
    # the server itself never could be). Env-driven like secret_key/
    # admin_password above, not a per-instance Settings toggle — one
    # Tailscale identity per container, shared by every instance this
    # server hosts, matching how the container itself is a single
    # deployment regardless of how many locations run inside it.
    tailscale_enabled: bool = False
    tailscale_auth_key: str = ""
    tailscale_login_server: str = ""   # empty → Tailscale's own cloud service; set for self-hosted Headscale
    tailscale_hostname: str = ""       # empty → let tailscale pick (usually the container hostname)

    # Email / SMTP — can also be configured in Settings UI; env vars seed the DB on first run
    # All Optional so that empty-string env vars (unset in docker-compose) are treated as absent
    smtp_host:         Optional[str]  = None
    smtp_port:         Optional[int]  = None
    smtp_username:     Optional[str]  = None
    smtp_password:     Optional[str]  = None
    smtp_from_address: Optional[str]  = None
    smtp_use_tls:      Optional[bool] = None
    admin_email:       Optional[str]  = None
    notify_on_register: Optional[bool] = None

    # Server-wide iPhone push key (CHIRP_APNS_*). Used when a site has no APNs
    # key of its own, and to sign pushes forwarded by the push relay. Kept in
    # the environment so site admins never see it. AUTH_KEY_FILE points at the
    # .p8 file; AUTH_KEY holds its PEM text instead.
    apns_team_id:       Optional[str]  = None
    apns_key_id:        Optional[str]  = None
    apns_bundle_id:     Optional[str]  = None
    apns_auth_key:      Optional[str]  = None
    apns_auth_key_file: Optional[str]  = None
    apns_production:    bool           = True
    # Public address of this server (e.g. https://ourchirp.com); used in
    # emails sent outside any site (site requests, relay tokens).
    public_url:         Optional[str]  = None

    class Config:
        env_prefix = "CHIRP_"
        # /app/data/.env is on the mounted volume — survives container rebuilds.
        # Falls back to .env in cwd for local development.
        env_file = ["/app/data/.env", ".env"]
        extra = "ignore"

    @field_validator(
        "smtp_host", "smtp_port", "smtp_username", "smtp_password",
        "smtp_from_address", "smtp_use_tls", "admin_email", "notify_on_register",
        "ebird_api_key", "ebird_st_api_key",
        "apns_team_id", "apns_key_id", "apns_bundle_id", "apns_auth_key", "apns_auth_key_file", "public_url",
        mode="before"
    )
    @classmethod
    def empty_str_to_none(cls, v):
        """Convert empty strings to None so Optional[int]/Optional[bool] fields
        don't crash when docker-compose passes unset env vars as ''."""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator("data_dir", "recordings_dir", "media_dir", mode="before")
    @classmethod
    def create_dirs(cls, v):
        try:
            Path(v).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass  # Will be created by ensure_dirs() at runtime
        return v

    def ensure_dirs(self):
        for d in [self.data_dir, self.recordings_dir, self.media_dir,
                  self.spectrograms_dir, self.clips_dir, self.enhanced_dir,
                  self.bat_clips_dir, self.ai_models_dir]:
            Path(d).mkdir(parents=True, exist_ok=True)


# Global singleton
settings = Settings()
settings.ensure_dirs()
