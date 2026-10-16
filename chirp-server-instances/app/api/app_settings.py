from ..cache import invalidate_settings
"""
Chirp Server — Settings API
"""
from typing import Optional
from datetime import datetime
import httpx
import logging

logger = logging.getLogger("chirp.settings")
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import Field, BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import AppSettings
from .auth import get_current_user

router = APIRouter()

# Fixed list of Dashboard sections an admin can show/hide — referenced by
# models.py's own comment on dashboard_sections_full/simplified, and by
# the frontend Settings UI that builds the checkbox list from this same
# id set (see api.settings.dashboardSections() in api.js). Not strictly
# enforced against stored values below — an unrecognized id in a saved
# list is just ignored by the Dashboard itself, the same tolerance every
# other loosely-validated settings field in this app already has.
DASHBOARD_SECTIONS = [
    {"id": "latest_recording", "label": "Latest recording", "description": "Card for the most recent recording"},
    {"id": "seen_today", "label": "Seen today", "description": "Grid of species detected today"},
    {"id": "daily_journal", "label": "Daily journal", "description": "AI-written daily summary"},
    {"id": "weekly_journal", "label": "Weekly journal", "description": "AI-written weekly summary"},
    {"id": "daily_weekly_summary", "label": "Daily/weekly summary", "description": "Most common bird, rarest species, and Yard Diversity"},
    {"id": "yard_pulse", "label": "Yard pulse", "description": "Two highlight stats distinct from the day/week summary"},
    {"id": "stats", "label": "Stat cards", "description": "Recordings, species, detections, last detection"},
    {"id": "activity_chart", "label": "Activity & top species", "description": "The detection-activity chart and top-species list"},
    {"id": "recent_recordings", "label": "Recent recordings", "description": "Row of the most recent recordings"},
    {"id": "recent_comments", "label": "Recent comments", "description": "Latest comments left on recordings"},
]


class SettingsIn(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    timezone: Optional[str] = None
    ebird_api_key:    Optional[str] = None
    ebird_st_api_key: Optional[str] = None   # eBird S&T Data Products key
    inat_api_token:   Optional[str] = None   # iNaturalist personal API token
    server_url:       Optional[str] = None   # Public base URL for email links
    haikubox_serial:  Optional[str] = None   # Haikubox device serial number
    haikubox_enabled: Optional[bool] = None  # master on/off for the whole Haikubox feature
    bird_buddy_email:    Optional[str] = None
    bird_buddy_password: Optional[str] = None
    bird_buddy_enabled:  Optional[bool] = None
    bird_buddy_selected_feeders: Optional[list] = None
    inat_username: Optional[str] = None
    inat_password: Optional[str] = None
    inat_oauth_client_id: Optional[str] = None
    inat_oauth_client_secret: Optional[str] = None
    inat_auto_refresh_enabled: Optional[bool] = None
    bat_detection_enabled: Optional[bool] = None
    bat_species_id_enabled: Optional[bool] = None
    bat_detection_device_name: Optional[str] = None
    bat_active_hours_start: Optional[str] = None
    bat_active_hours_end:   Optional[str] = None
    bat_min_swept_fraction: Optional[float] = None
    bat_discard_likely_interference: Optional[bool] = None
    bat_auto_remove_wobble: Optional[bool] = None
    bat_max_pulse_rate:     Optional[float] = None
    anthropic_api_key: Optional[str] = None
    apns_team_id: Optional[str] = None
    apns_key_id: Optional[str] = None
    apns_bundle_id: Optional[str] = None
    apns_auth_key: Optional[str] = None
    apns_production: Optional[bool] = None
    push_relay_url: Optional[str] = None
    push_relay_token: Optional[str] = None
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    ollama_base_url: Optional[str] = None
    ollama_model: Optional[str] = None
    ai_feature_providers: Optional[dict] = None
    daily_summary_schedule_time: Optional[str] = None
    weekly_summary_schedule_day: Optional[int] = None
    weekly_summary_schedule_hour: Optional[int] = None
    daily_summary_schedule_times: Optional[list] = None
    profile_summary_auto_refresh: Optional[bool] = None
    profile_summary_refresh_days: Optional[int] = None
    profile_summary_refresh_hour: Optional[int] = None
    auto_backup_enabled: Optional[bool] = None
    auto_backup_hour: Optional[int] = None
    auto_backup_retention_count: Optional[int] = None
    ai_personality_friendliness: Optional[int] = None
    ai_personality_informational: Optional[int] = None
    ai_personality_irreverence: Optional[int] = None
    ai_personality_depth: Optional[int] = None
    ai_personality_curiosity: Optional[int] = None
    ai_web_search_enabled: Optional[bool] = None
    range_map_sources: Optional[dict] = None  # {"aab": bool, "macaulay": bool, "geomodel": bool, "birdlife": bool}
    range_map_source_order: Optional[list] = None  # e.g. ["aab", "macaulay", "ebird_st", "geomodel", "birdlife"]
    dark_mode: Optional[bool] = None
    distance_unit: Optional[str] = None
    temperature_unit: Optional[str] = None
    notifications_enabled: Optional[bool] = None
    notification_min_confidence: Optional[float] = None
    notification_webhook_url: Optional[str] = None
    min_confidence_display: Optional[float] = None
    birdnet_species_thresholds: Optional[dict] = None
    night_threshold_mode: Optional[str] = None
    night_threshold_species: Optional[dict] = None
    show_low_confidence: Optional[bool] = None
    bat_species_id_enabled: Optional[bool] = None
    bat_species_id_min_confidence: Optional[float] = None
    birdnet_min_confidence: Optional[float] = None
    birdnet_overlap: Optional[float] = None
    birdnet_sensitivity: Optional[float] = None
    auto_delete_recordings_days: Optional[int] = None
    auto_archive_recordings_days: Optional[int] = None
    auto_purge_empty_recordings:  Optional[bool] = None
    auto_purge_min_confidence:    Optional[float] = None
    auto_purge_all_device:        Optional[bool]  = None
    max_recordings_gb: Optional[float] = None
    share_location_with_ebird: Optional[bool] = None
    share_detections_public: Optional[bool] = None
    server_reanalyze_on_upload: Optional[bool] = None
    server_reanalyze_delete_device: Optional[bool] = None
    show_deleted_detections: Optional[bool] = None
    range_maps_enabled: Optional[bool] = None
    observation_heatmap_enabled: Optional[bool] = None
    allow_manual_reanalyze: Optional[bool] = None
    detection_color_palette: Optional[str] = None
    ai_enhance_enabled: Optional[bool] = None
    detection_model: Optional[str] = None
    exp_birdnet3_shadow: Optional[bool] = None
    exp_birdnet3_main: Optional[bool] = None
    exp_birdnet3_min_conf: Optional[float] = None
    exp_nighthawk_enabled: Optional[bool] = None
    exp_nighthawk_start: Optional[str] = None
    exp_nighthawk_end: Optional[str] = None
    exp_nighthawk_threshold: Optional[int] = None
    device_offline_minutes: Optional[int] = None
    ai_enhance_auto_apply: Optional[bool] = None
    ai_enhance_dry: Optional[float] = None
    rumble_removal_mode: Optional[str] = None
    # Recording device settings (pushed via managed config)
    recording_min_gap_seconds: Optional[int] = None
    recording_max_duration_sec: Optional[int] = None
    recording_max_per_hour: Optional[int] = None
    # Server-side storage management
    storage_compress_on_upload: Optional[bool] = None
    storage_compress_quality: Optional[str] = None
    storage_max_dir_gb: Optional[float] = None
    storage_cleanup_keep_flagged: Optional[bool] = None
    auth_enabled: Optional[bool] = None
    # Email / SMTP
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_address: Optional[str] = None
    smtp_use_tls: Optional[bool] = None
    admin_email: Optional[str] = None
    notify_on_register: Optional[bool] = None
    digest_hour: Optional[int] = None
    digest_push_hour: Optional[int] = Field(None, ge=0, le=23)    # local hour; noon or later covers that day
    digest_email_hour: Optional[int] = Field(None, ge=0, le=23)
    # Activity log — login/page-view audit trail (admin-only visibility)
    activity_log_enabled:        Optional[bool] = None
    activity_log_track_ip:       Optional[bool] = None
    activity_log_retention_days: Optional[int]  = None
    # Admin-configurable Dashboard sections — see models.py's own comment
    # on these two columns for the null-means-everything convention.
    dashboard_sections_full: Optional[list] = None
    dashboard_sections_simplified: Optional[list] = None


class SettingsOut(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    timezone: str = "America/New_York"
    ebird_api_key:    Optional[str] = None
    ebird_st_api_key: Optional[str] = None
    inat_api_token:   Optional[str] = None
    server_url:       Optional[str] = None
    haikubox_serial:  Optional[str] = None
    haikubox_enabled: Optional[bool] = False
    bird_buddy_email:    Optional[str] = None
    bird_buddy_password: Optional[str] = None
    bird_buddy_enabled:  Optional[bool] = False
    bird_buddy_selected_feeders: Optional[list] = None
    bird_buddy_last_sync_at: Optional[datetime] = None
    bird_buddy_last_sync_error: Optional[str] = None
    inat_username: Optional[str] = None
    inat_password: Optional[str] = None
    inat_oauth_client_id: Optional[str] = None
    inat_oauth_client_secret: Optional[str] = None
    inat_auto_refresh_enabled: Optional[bool] = False
    inat_last_refresh_error: Optional[str] = None
    bat_detection_enabled: Optional[bool] = False
    bat_species_id_enabled: Optional[bool] = False
    bat_detection_device_name: Optional[str] = None
    bat_active_hours_start: Optional[str] = "20:00"
    bat_active_hours_end:   Optional[str] = "06:00"
    bat_min_swept_fraction: Optional[float] = 0.3
    bat_discard_likely_interference: Optional[bool] = False
    bat_auto_remove_wobble: Optional[bool] = False
    bat_max_pulse_rate:     Optional[float] = 60.0
    anthropic_api_key: Optional[str] = None
    apns_team_id: Optional[str] = None
    apns_key_id: Optional[str] = None
    apns_bundle_id: Optional[str] = None
    apns_auth_key: Optional[str] = None
    apns_production: Optional[bool] = True
    push_relay_url: Optional[str] = None
    push_relay_token: Optional[str] = None
    push_route: Optional[str] = None      # site | server | relay | "" (read-only)
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    ollama_base_url: Optional[str] = None
    ollama_model: Optional[str] = None
    ai_feature_providers: Optional[dict] = None
    daily_summary_schedule_time: Optional[str] = None
    weekly_summary_schedule_day: Optional[int] = None
    weekly_summary_schedule_hour: Optional[int] = None
    daily_summary_schedule_times: Optional[list] = None
    profile_summary_auto_refresh: Optional[bool] = False
    profile_summary_refresh_days: Optional[int] = 7
    profile_summary_refresh_hour: Optional[int] = 3
    auto_backup_enabled: Optional[bool] = True
    auto_backup_hour: Optional[int] = 3
    auto_backup_retention_count: Optional[int] = 14
    auto_backup_last_run_at: Optional[datetime] = None
    auto_backup_last_success_at: Optional[datetime] = None
    auto_backup_last_error: Optional[str] = None
    ai_personality_friendliness: Optional[int] = 60
    ai_personality_informational: Optional[int] = 50
    ai_personality_irreverence: Optional[int] = 35
    ai_personality_depth: Optional[int] = 50
    ai_personality_curiosity: Optional[int] = 50
    ai_web_search_enabled: Optional[bool] = False
    dark_mode: bool = True
    distance_unit: str = "mi"
    temperature_unit: str = "F"
    notifications_enabled: bool = False
    notification_min_confidence: float = 0.75
    notification_webhook_url: Optional[str] = None
    min_confidence_display: float = 0.15
    birdnet_species_thresholds: dict = {}
    night_threshold_mode: str = "night"
    night_threshold_species: dict = {}
    show_low_confidence: bool = True
    bat_species_id_enabled: bool = False
    bat_species_id_min_confidence: float = 0.75
    birdnet_min_confidence: float = 0.05
    birdnet_overlap: float = 2.5
    birdnet_sensitivity: float = 1.5
    # These four were added via migration and may be NULL in existing DBs
    auto_delete_recordings_days: Optional[int] = 0
    auto_archive_recordings_days: Optional[int] = 0
    auto_purge_empty_recordings:  Optional[bool] = False
    max_recordings_gb: Optional[float] = 0.0
    share_location_with_ebird: Optional[bool] = False
    share_detections_public: Optional[bool] = False
    server_reanalyze_on_upload: Optional[bool] = True
    server_reanalyze_delete_device: Optional[bool] = True
    show_deleted_detections: Optional[bool] = False
    range_maps_enabled: Optional[bool] = False
    observation_heatmap_enabled: Optional[bool] = False
    allow_manual_reanalyze: Optional[bool] = True
    detection_color_palette: Optional[str] = "vivid"
    ai_enhance_enabled: Optional[bool] = False
    detection_model: Optional[str] = "birdnet3"
    exp_birdnet3_shadow: Optional[bool] = False
    exp_birdnet3_main: Optional[bool] = False
    exp_birdnet3_min_conf: Optional[float] = 0.5
    exp_nighthawk_enabled: Optional[bool] = False
    exp_nighthawk_start: Optional[str] = "21:00"
    exp_nighthawk_end: Optional[str] = "05:00"
    exp_nighthawk_threshold: Optional[int] = 80
    device_offline_minutes: Optional[int] = 15
    ai_enhance_auto_apply: Optional[bool] = False
    ai_enhance_dry: Optional[float] = 0.1
    rumble_removal_mode: Optional[str] = "auto"
    # Recording device settings
    recording_min_gap_seconds: Optional[int] = 10
    recording_max_duration_sec: Optional[int] = 30
    recording_max_per_hour: Optional[int] = 0
    # Storage management
    storage_compress_on_upload: Optional[bool] = True
    storage_compress_quality: Optional[str] = "lossless"
    storage_max_dir_gb: Optional[float] = 0.0
    storage_cleanup_keep_flagged: Optional[bool] = True
    auth_enabled: Optional[bool] = False
    # Email / SMTP
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_address: Optional[str] = None
    smtp_use_tls: Optional[bool] = True
    admin_email: Optional[str] = None
    notify_on_register: Optional[bool] = True
    digest_hour: Optional[int] = 7
    digest_push_hour: Optional[int] = None
    digest_email_hour: Optional[int] = None
    # Range map sources — must be in SettingsOut so GET /settings includes it
    range_map_sources: Optional[dict] = None
    range_map_source_order: Optional[list] = None
    auto_purge_min_confidence: Optional[float] = 0.65
    auto_purge_all_device:     Optional[bool]  = False
    # Activity log — must be Optional with real defaults: these columns are
    # backfilled by _defaults above, but a brand-new install's very first
    # GET (before that backfill runs) or a pre-migration row would otherwise
    # hit the exact NULL-vs-bool validation crash documented in past
    # versions (0.1.9.v, 0.1.4.e) for other migrated columns.
    activity_log_enabled:        Optional[bool] = True
    activity_log_track_ip:       Optional[bool] = True
    activity_log_retention_days: Optional[int]  = 90
    # Admin-configurable Dashboard sections — see models.py's own comment
    # on these two columns for the null-means-everything convention.
    dashboard_sections_full: Optional[list] = None
    dashboard_sections_simplified: Optional[list] = None

    class Config:
        from_attributes = True


def _seed_from_env(s: AppSettings) -> bool:
    """Seed any missing/blank settings from environment variables / config.py.
    Writes the env value when the DB column is None OR empty string.
    Returns True if any field was updated (caller must commit)."""
    from ..config import settings as _cfg
    changed = False
    pairs = [
        ("smtp_host",          _cfg.smtp_host),
        ("smtp_port",          _cfg.smtp_port if _cfg.smtp_port is not None else (587 if _cfg.smtp_host else None)),
        ("smtp_username",      _cfg.smtp_username),
        ("smtp_password",      _cfg.smtp_password),
        ("smtp_from_address",  _cfg.smtp_from_address),
        ("smtp_use_tls",       _cfg.smtp_use_tls if _cfg.smtp_use_tls is not None else (True if _cfg.smtp_host else None)),
        ("admin_email",        _cfg.admin_email),
        ("notify_on_register", _cfg.notify_on_register),
        ("ebird_api_key",      _cfg.ebird_api_key),
        ("ebird_st_api_key",   _cfg.ebird_st_api_key),
    ]
    for field, env_val in pairs:
        if env_val is None:
            continue
        current = getattr(s, field, None)
        # Write if DB has no value (None or empty string)
        if current is None or current == "":
            setattr(s, field, env_val)
            changed = True
    return changed


# Defaults applied to any column that's still NULL after a migration
# added it to an existing database — extracted to a module-level
# constant (rather than living as a local variable inside
# _get_or_create) specifically so it can be checked against
# SettingsIn/SettingsOut's own field sets by a real test. A real bug
# this exact mismatch caused: ai_personality_depth was added here and
# to the AppSettings model, but never added to SettingsIn (the PUT
# request schema) — Pydantic silently drops any field not defined on
# the model, so the frontend's save request correctly sent the value,
# the backend correctly received the HTTP request, and the value was
# silently discarded before ever reaching the database write loop. No
# error anywhere; it just didn't persist. A structural check comparing
# this list's field names against SettingsIn/SettingsOut's own field
# names catches this class of bug generally, for any future field, not
# just this one.
_MIGRATION_DEFAULTS = [
    ("auto_delete_recordings_days", 0),
    ("auto_archive_recordings_days", 0),
    ("auto_purge_empty_recordings",  False),
    ("max_recordings_gb", 0.0),
    ("share_location_with_ebird", False),
    ("share_detections_public", False),
    ("server_reanalyze_on_upload",     True),
    ("server_reanalyze_delete_device", True),
    ("show_deleted_detections",        False),
    ("range_maps_enabled", False),
    ("observation_heatmap_enabled", False),
    ("allow_manual_reanalyze", True),
    ("detection_color_palette", "vivid"),
    ("recording_min_gap_seconds", 10),
    ("recording_max_duration_sec", 30),
    ("recording_max_per_hour", 0),
    ("storage_compress_on_upload", True),
    ("storage_compress_quality", "lossless"),
    ("storage_max_dir_gb", 0.0),
    ("storage_cleanup_keep_flagged", True),
    ("dark_mode", True),
    ("notifications_enabled", False),
    ("notification_min_confidence", 0.75),
    ("min_confidence_display", 0.15),
    ("birdnet_species_thresholds", {}),
    ("night_threshold_mode", "night"),
    ("night_threshold_species", {}),
    ("show_low_confidence", True),
    ("bat_species_id_enabled", False),
    ("bat_species_id_min_confidence", 0.75),
    ("birdnet_min_confidence", 0.05),
    ("birdnet_overlap", 2.5),
    ("birdnet_sensitivity", 1.5),
    ("distance_unit", "mi"),
    ("temperature_unit", "F"),
    ("bat_detection_enabled", False),
    ("bat_species_id_enabled", False),
    ("bat_active_hours_start", "20:00"),
    ("bat_active_hours_end",   "06:00"),
    ("bat_min_swept_fraction", 0.3),
    ("bat_max_pulse_rate",     60.0),
    ("bat_auto_remove_wobble", False),
    ("profile_summary_auto_refresh", False),
    ("profile_summary_refresh_days", 7),
    ("profile_summary_refresh_hour", 3),
    ("auto_backup_enabled", True),
    ("auto_backup_hour", 3),
    ("auto_backup_retention_count", 14),
    ("ai_personality_friendliness", 60),
    ("ai_personality_informational", 50),
    ("ai_personality_irreverence", 35),
    ("ai_personality_depth", 50),
    ("ai_personality_curiosity", 50),
    ("ai_web_search_enabled", False),
    ("haikubox_enabled", False),
    ("bird_buddy_enabled", False),
    ("activity_log_enabled", True),
    ("activity_log_track_ip", True),
    ("activity_log_retention_days", 90),
    ("ai_enhance_enabled", False),
    ("detection_model", "birdnet3"),
    ("exp_birdnet3_shadow", False),
    ("exp_birdnet3_main", False),
    ("exp_birdnet3_min_conf", 0.5),
    ("exp_nighthawk_enabled", False),
    ("exp_nighthawk_start", "21:00"),
    ("exp_nighthawk_end", "05:00"),
    ("exp_nighthawk_threshold", 80),
    ("device_offline_minutes", 15),
    ("ai_enhance_auto_apply", False),
    ("ai_enhance_dry", 0.1),
    ("rumble_removal_mode", "auto"),
]


def _get_or_create(db: Session) -> AppSettings:
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if not s:
        s = AppSettings(id=1)
        db.add(s)
        db.commit()
        db.refresh(s)
    # Fix NULL values for columns added via migration on existing DBs
    needs_save = False
    for field, default in _MIGRATION_DEFAULTS:
        if getattr(s, field, None) is None:
            setattr(s, field, default)
            needs_save = True
    if needs_save:
        db.commit()
    return s


def _mask_key(key: Optional[str]) -> Optional[str]:
    if not key:
        return key
    return key[:4] + "****" + key[-4:] if len(key) > 8 else "****"


@router.get("", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    s = _get_or_create(db)
    out = SettingsOut.model_validate(s)
    out.ebird_api_key    = _mask_key(s.ebird_api_key)
    out.ebird_st_api_key = _mask_key(s.ebird_st_api_key)
    out.inat_api_token   = _mask_key(s.inat_api_token)
    out.haikubox_serial  = _mask_key(s.haikubox_serial)
    out.bird_buddy_password = _mask_key(s.bird_buddy_password)
    out.anthropic_api_key = _mask_key(s.anthropic_api_key)
    out.openai_api_key = _mask_key(s.openai_api_key)
    out.gemini_api_key = _mask_key(s.gemini_api_key)
    out.smtp_password    = _mask_key(s.smtp_password)   # never send password in plaintext
    out.apns_auth_key    = _mask_key(s.apns_auth_key)    # the .p8 private key content — never send in plaintext
    out.push_relay_token = _mask_key(s.push_relay_token)
    from ..services.apns_push import push_route
    out.push_route = push_route(s)
    from ..services.scheduled_push import digest_hours
    hours = digest_hours(s)
    out.digest_push_hour, out.digest_email_hour = hours["push"], hours["email"]
    return out


@router.put("", response_model=SettingsOut)
def update_settings(body: SettingsIn, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    s = _get_or_create(db)
    data = body.model_dump(exclude_none=True)
    # Don't overwrite smtp_password if the client sent back a masked value
    if "smtp_password" in data and data["smtp_password"] and "*" in str(data["smtp_password"]):
        del data["smtp_password"]
    if "bird_buddy_password" in data and data["bird_buddy_password"] and "*" in str(data["bird_buddy_password"]):
        del data["bird_buddy_password"]
    # Don't overwrite empty-string passwords with blank (treat as "unchanged")
    if data.get("smtp_password") == "":
        del data["smtp_password"]
    if data.get("bird_buddy_password") == "":
        del data["bird_buddy_password"]
    # Don't overwrite masked API tokens
    for masked_field in ("ebird_api_key", "ebird_st_api_key", "inat_api_token", "haikubox_serial", "anthropic_api_key", "openai_api_key", "gemini_api_key", "apns_auth_key", "push_relay_token"):
        if masked_field in data and data[masked_field] and "*" in str(data[masked_field]):
            del data[masked_field]
    _json_cols = {'device_api_keys', 'range_map_sources', 'range_map_source_order', 'managed_config',
                  'mic_names', 'ebird_data', 'call_media', 'extra_photos',
                  'description_sections', 'monthly_frequency', 'bird_buddy_selected_feeders',
                  'dashboard_sections_full', 'dashboard_sections_simplified',
                  'birdnet_species_thresholds', 'night_threshold_species'}
    if "birdnet_species_thresholds" in data:
        # {common name: score}; blank or out-of-range entries are dropped.
        clean = {}
        for k, v in (data["birdnet_species_thresholds"] or {}).items():
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            if str(k).strip() and 0.01 <= v <= 0.99:
                clean[str(k).strip()] = round(v, 3)
        data["birdnet_species_thresholds"] = clean
    if "night_threshold_mode" in data:
        from ..services.birdnet_pass import NIGHT_MODES
        if data["night_threshold_mode"] not in NIGHT_MODES:
            raise HTTPException(status_code=400, detail=f"night_threshold_mode must be one of {', '.join(NIGHT_MODES)}")
    if "night_threshold_species" in data:
        from ..services.birdnet_pass import NIGHT_CALLER_RE
        data["night_threshold_species"] = {
            str(k).strip(): bool(v) for k, v in (data["night_threshold_species"] or {}).items()
            if str(k).strip() and NIGHT_CALLER_RE.search(str(k))}
    # Experimental models: keep values sane (see services/birdnet3.py, nighthawk_service.py)
    import re as _re
    for k in ("exp_nighthawk_start", "exp_nighthawk_end"):
        if k in data and (not isinstance(data[k], str) or not _re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", data[k] or "")):
            raise HTTPException(status_code=422, detail="Night audio times must be HH:MM (24-hour)")
    if "detection_model" in data and data["detection_model"] not in ("birdnet3", "birdnet24"):
        raise HTTPException(status_code=422, detail="detection_model must be birdnet3 or birdnet24")
    if data.get("exp_birdnet3_min_conf") is not None:
        data["exp_birdnet3_min_conf"] = min(0.99, max(0.05, float(data["exp_birdnet3_min_conf"])))
    if data.get("exp_nighthawk_threshold") is not None:
        data["exp_nighthawk_threshold"] = int(min(99, max(1, int(data["exp_nighthawk_threshold"]))))
    if data.get("device_offline_minutes") is not None:
        try:
            data["device_offline_minutes"] = int(min(1440, max(5, int(data["device_offline_minutes"]))))
        except (TypeError, ValueError):
            data["device_offline_minutes"] = 15
    _night_changed = any(k in data and data[k] != getattr(s, k, None)
                         for k in ("night_threshold_mode", "night_threshold_species", "birdnet_min_confidence"))
    if data.get("exp_birdnet3_shadow") or data.get("detection_model") == "birdnet3":
        try:
            from ..services import birdnet3
            birdnet3.ensure_downloaded()
        except Exception as e:
            logger.warning("BirdNET v3 download couldn't start: %s", e)
    for field, value in data.items():
        setattr(s, field, value)
        if field in _json_cols:
            # SQLAlchemy doesn't always detect in-place JSON mutations; flag explicitly
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(s, field)
    db.commit()
    db.refresh(s)
    invalidate_settings()  # flush auth_enabled cache
    if _night_changed:
        # Devices read the night-caller rule with their config (see
        # devices.get_device_config); a new version makes them fetch it.
        try:
            from ..models import Device
            from .devices import _config_version_now
            v = _config_version_now()
            for d in db.query(Device).all():
                d.config_version = v
            db.commit()
        except Exception as e:
            logger.warning("Could not flag devices for the night threshold change: %s", e)

    # Stamp when iNat token was last set (tokens expire every 24 h)
    if body.inat_api_token and body.inat_api_token.strip():
        from datetime import datetime as _dt
        if hasattr(s, 'inat_token_set_at'):
            s.inat_token_set_at = _dt.utcnow()

    # Sync eBird key to runtime config immediately
    if body.ebird_api_key:
        from ..config import settings
        settings.ebird_api_key = body.ebird_api_key
        # Invalidate bar-chart cache so next enrichment uses new key + location
        from ..services.bird_enricher import BirdEnricher
        for attr in list(vars(BirdEnricher)):
            if attr.startswith("_bar_chart_cache_"):
                try:
                    delattr(BirdEnricher, attr)
                except AttributeError:
                    pass

    # Invalidate bar chart cache on location change too
    if body.latitude is not None or body.longitude is not None:
        from ..services.bird_enricher import BirdEnricher
        for attr in list(vars(BirdEnricher)):
            if attr.startswith("_bar_chart_cache_"):
                try:
                    delattr(BirdEnricher, attr)
                except AttributeError:
                    pass

    if body.ebird_st_api_key:
        from ..config import settings
        settings.ebird_st_api_key = body.ebird_st_api_key

    out = SettingsOut.model_validate(s)
    out.ebird_api_key    = _mask_key(s.ebird_api_key)
    out.ebird_st_api_key = _mask_key(s.ebird_st_api_key)
    out.haikubox_serial  = _mask_key(s.haikubox_serial)
    out.bird_buddy_password = _mask_key(s.bird_buddy_password)
    out.anthropic_api_key = _mask_key(s.anthropic_api_key)
    out.openai_api_key = _mask_key(s.openai_api_key)
    out.gemini_api_key = _mask_key(s.gemini_api_key)
    out.smtp_password    = _mask_key(s.smtp_password)
    out.apns_auth_key    = _mask_key(s.apns_auth_key)
    out.push_relay_token = _mask_key(s.push_relay_token)
    from ..services.apns_push import push_route
    out.push_route = push_route(s)
    from ..services.scheduled_push import digest_hours
    hours = digest_hours(s)
    out.digest_push_hour, out.digest_email_hour = hours["push"], hours["email"]

    # If min_confidence_display changed, proactively regenerate cached
    # spectrograms in the background rather than deleting them immediately.
    # Deleting every cached PNG up front made every recording a cache-miss
    # at once, triggering slow synchronous generation for the next viewer
    # of anything. Old spectrograms stay valid and servable until each
    # replacement is ready, so there's no window with nothing cached.
    if body.min_confidence_display is not None:
        background_tasks.add_task(_regenerate_spectrograms_bg, float(body.min_confidence_display))

    return out


SPECTROGRAM_PREWARM_LIMIT = int(__import__("os").environ.get("CHIRP_SPECTROGRAM_PREWARM", "500"))


def _regenerate_spectrograms_bg(new_threshold: float) -> None:
    """
    Proactively regenerate every recording's spectrogram for a new
    min_confidence_display threshold, run as a background task after a
    settings change. Uses its own DB session (background tasks must not
    share the request's session, which closes when the request returns).
    Processes recordings one at a time and continues past any individual
    failure (missing/corrupt audio, archived recording with no WAV) rather
    than aborting the whole batch — a partial cache-warm is still better
    than none, and the existing on-demand generation path remains as a
    correctness fallback for anything this misses.
    """
    import logging as _logging
    from ..database import SessionLocal
    from ..models import Recording
    from ..config import settings as _cfg
    from ..services.audio_processor import AudioProcessor

    logger = _logging.getLogger("chirp.spectrogram_regen")
    _processor = AudioProcessor()
    conf_key = str(int(round(new_threshold * 100)))
    db = SessionLocal()
    regenerated, skipped, failed = 0, 0, 0
    try:
        from ..models import AppSettings
        _regen_settings = db.query(AppSettings).filter(AppSettings.id == 1).first()
        _regen_palette = getattr(_regen_settings, "detection_color_palette", None) or "vivid"
        # Newest recordings only: the rest regenerate when someone opens
        # them. Warming every recording wrote two files per recording per
        # threshold change (a server with 24k recordings had 470k cached
        # spectrograms) for pages nobody visits.
        from ..services.audio_processor import spectrogram_filename
        recordings = (
            db.query(Recording)
            .filter(Recording.deleted_at.is_(None))
            .filter(Recording.archived_at.is_(None))
            .filter(Recording.is_bat.isnot(True))
            .filter(Recording.wav_path.isnot(None))
            .order_by(Recording.trigger_timestamp.desc())
            .limit(SPECTROGRAM_PREWARM_LIMIT)
            .all()
        )
        logger.info("Spectrogram regen: starting for %d recordings at threshold %s",
                    len(recordings), conf_key)
        for rec in recordings:
            import os as _os
            spec_path = _os.path.join(_cfg.spectrograms_dir, spectrogram_filename(rec.id, conf_key, False, _regen_palette))
            if _os.path.exists(spec_path):
                skipped += 1
                continue
            if not rec.wav_path or not _os.path.exists(rec.wav_path):
                skipped += 1
                continue
            try:
                visible_dets = [
                    {"common_name": d.common_name, "confidence": d.confidence,
                     "start_time": d.start_time, "end_time": d.end_time}
                    for d in rec.detections
                    if d.confidence >= new_threshold
                ]
                generated = _processor.generate_spectrogram(
                    rec.wav_path, _cfg.spectrograms_dir, rec.id,
                    detections=visible_dets or None, conf_key=conf_key,
                    color_palette=_regen_palette,
                )
                if conf_key == "0":
                    rec.spectrogram_path = generated
                    db.commit()
                # Same threshold change invalidates the thumbnail cache key
                # too (the detection-box overlay differs) — regenerate it
                # alongside the full-resolution version rather than leaving
                # it to a separate lazy on-demand path.
                thumb_path = _os.path.join(_cfg.spectrograms_dir, spectrogram_filename(rec.id, conf_key, True, _regen_palette))
                if not _os.path.exists(thumb_path):
                    try:
                        _processor.generate_spectrogram(
                            rec.wav_path, _cfg.spectrograms_dir, rec.id,
                            detections=visible_dets or None, conf_key=conf_key, thumb=True,
                            color_palette=_regen_palette,
                        )
                    except Exception as e_thumb:
                        logger.debug("Thumbnail regen failed for %s: %s", rec.id, e_thumb)
                regenerated += 1
            except Exception as e:
                failed += 1
                logger.debug("Spectrogram regen failed for %s: %s", rec.id, e)
        logger.info("Spectrogram regen: done — %d regenerated, %d already cached/skipped, %d failed",
                    regenerated, skipped, failed)
    except Exception as e:
        logger.warning("Spectrogram regen: batch error: %s", e)
    finally:
        db.close()


def _regenerate_spectrograms_for_color_fix_bg() -> None:
    """
    One-time (per instance) forced regeneration of every recording's
    default-threshold spectrogram, run once at startup after upgrading
    to the version that fixed sequential (rather than evenly-spread)
    detection color assignment — see audio_processor.py's own
    pick_species_colors(). Unlike _regenerate_spectrograms_bg() above,
    this DELETES the existing cached file first rather than skipping
    it when already present: the whole point is correcting a file that
    already exists but was drawn with the old, wrong color logic, not
    filling in ones that are simply missing.

    Only ever needs to touch the conf_key="0" (default threshold)
    files and their thumbnails — a non-default threshold's own
    spectrogram gets regenerated the normal way the next time someone
    actually changes that setting, and was never silently stuck the
    way the default one was (see the models.py column's own docstring
    for why the default case specifically needed this).
    """
    import logging as _logging
    import os as _os
    from ..database import SessionLocal
    from ..models import Recording, AppSettings
    from ..config import settings as _cfg
    from ..services.audio_processor import AudioProcessor

    logger = _logging.getLogger("chirp.spectrogram_regen")
    _processor = AudioProcessor()
    db = SessionLocal()
    regenerated, failed = 0, 0
    try:
        _settings_row = db.query(AppSettings).filter(AppSettings.id == 1).first()
        if _settings_row and _settings_row.spectrograms_regenerated_for_color_fix:
            return  # already done for this instance — nothing to do
        _palette = getattr(_settings_row, "detection_color_palette", None) or "vivid"
        recordings = (
            db.query(Recording)
            .filter(Recording.deleted_at.is_(None))
            .filter(Recording.wav_path.isnot(None))
            .all()
        )
        logger.info("Spectrogram color-fix regen: starting for %d recordings", len(recordings))
        for rec in recordings:
            if not rec.wav_path or not _os.path.exists(rec.wav_path):
                continue
            try:
                visible_dets = [
                    {"common_name": d.common_name, "confidence": d.confidence,
                     "start_time": d.start_time, "end_time": d.end_time}
                    for d in rec.detections
                ]
                for _thumb in (False, True):
                    _suffix = "_thumb2" if _thumb else ""
                    _path = f"{_cfg.spectrograms_dir}/{rec.id}_spectrogram_0{_suffix}.png"
                    try:
                        _os.remove(_path)
                    except OSError:
                        pass  # never existed, or already gone — fine either way
                generated = _processor.generate_spectrogram(
                    rec.wav_path, _cfg.spectrograms_dir, rec.id,
                    detections=visible_dets or None, color_palette=_palette,
                )
                rec.spectrogram_path = generated
                try:
                    _processor.generate_spectrogram(
                        rec.wav_path, _cfg.spectrograms_dir, rec.id,
                        detections=visible_dets or None, thumb=True, color_palette=_palette,
                    )
                except Exception as e_thumb:
                    logger.debug("Thumbnail color-fix regen failed for %s: %s", rec.id, e_thumb)
                db.commit()
                regenerated += 1
            except Exception as e:
                failed += 1
                logger.debug("Spectrogram color-fix regen failed for %s: %s", rec.id, e)
        if _settings_row:
            _settings_row.spectrograms_regenerated_for_color_fix = True
            db.commit()
        logger.info("Spectrogram color-fix regen: done — %d regenerated, %d failed", regenerated, failed)
    except Exception as e:
        logger.warning("Spectrogram color-fix regen: batch error: %s", e)
    finally:
        db.close()

@router.post("/cleanup-deleted")
def cleanup_deleted_recordings(
    delete_files: bool = Query(True, description="Also delete audio/spectrogram files from disk"),
    db: Session = Depends(get_db),
):
    """
    Hard-delete all soft-deleted recordings (deleted_at IS NOT NULL).
    Optionally removes associated files from disk.
    Returns counts of what was removed.
    """
    import os as _os
    from ..models import Recording

    soft_deleted = db.query(Recording).filter(
        Recording.deleted_at.isnot(None)
    ).all()

    if not soft_deleted:
        return {"removed_recordings": 0, "removed_files": 0, "freed_bytes": 0}

    # Committed batches, files after each commit (see file_cleanup).
    from ..services.file_cleanup import delete_recordings
    r = delete_recordings(db, soft_deleted, delete_files)
    removed_files, freed_bytes = r["removed_files"], r["freed_bytes"]

    return {
        "removed_recordings": r["purged"],
        "removed_files": removed_files,
        "freed_bytes": freed_bytes,
        "freed_mb": round(freed_bytes / 1048576, 2),
    }


@router.get("/deleted-count")
def get_deleted_count(db: Session = Depends(get_db)):
    """Return how many recordings are soft-deleted (pending cleanup)."""
    from ..models import Recording
    count = db.query(Recording).filter(Recording.deleted_at.isnot(None)).count()
    return {"soft_deleted_count": count}



def _empty_recording_query(db, mode: str):
    """Recordings that show no detections (the list's "Unknown" cards):
    nothing at min_confidence_display. The one exception is an owl the
    server pass kept under its owl rules (recordings._night_caller_protects).
    mode "no_server_detections" looks at server rows only. Haikubox rows
    (no audio) are never included; bats (device-sourced rows that never
    become "server") are excluded from the server mode."""
    from ..models import Recording, Detection, AppSettings as _AS
    from ..services.birdnet_pass import OWL_MIN_CONF, night_rules
    from .recordings import _night_caller_protects
    s = db.query(_AS).filter(_AS.id == 1).first()
    night = night_rules(s)
    display_min = float(getattr(s, "min_confidence_display", 0.0) or 0.0) if s else 0.0
    server_only = mode == "no_server_detections"

    def _dets():
        q = db.query(Detection.recording_id)
        return q.filter(Detection.source == "server") if server_only else q

    shown = _dets().filter(Detection.confidence >= display_min).distinct()
    keep = {rid for rid, name, conf in
            (db.query(Detection.recording_id, Detection.common_name, Detection.confidence)
             .filter(Detection.source == "server", Detection.confidence >= OWL_MIN_CONF,
                     Detection.confidence < display_min).all())
            if _night_caller_protects(name, float(conf or 0), "server", night=night)}
    q = db.query(Recording).filter(
        Recording.deleted_at.is_(None),
        Recording.haikubox_detection_id.is_(None),
        Recording.is_saved.isnot(True),
        ~Recording.id.in_(shown),
    )
    if server_only:
        q = q.filter(Recording.is_bat.is_(False))
    if keep:
        q = q.filter(~Recording.id.in_(list(keep)))
    return q


@router.get("/empty-recordings-count")
def get_empty_recordings_count(db: Session = Depends(get_db)):
    """How many recordings show 0 detections (candidates for purge). See
    _empty_recording_query for what counts."""
    return {
        "no_detections": _empty_recording_query(db, "no_detections").count(),
        "no_server_detections": _empty_recording_query(db, "no_server_detections").count(),
    }


@router.post("/purge-empty-recordings")
def purge_empty_recordings(
    mode: str = Query("no_detections",
                      description="'no_detections' = 0 shown detections; "
                                  "'no_server_detections' = 0 shown server-side detections"),
    delete_files: bool = Query(True, description="Also delete audio/spectrogram files from disk"),
    db: Session = Depends(get_db),
):
    """
    Hard-delete recordings that show no detections (see
    _empty_recording_query). Haikubox and bat recordings are protected as
    before: Haikubox rows have no server pass to judge, and bat rows are
    device-sourced forever.
    """
    targets = _empty_recording_query(
        db, "no_server_detections" if mode == "no_server_detections" else "no_detections").all()
    return _delete_recordings(db, targets, delete_files)


def _delete_recordings(db, targets: list, delete_files: bool = True,
                       batch_size: int = 20, pause: float = 0.05) -> dict:
    """Hard-delete recordings and their files in committed batches (see
    services.file_cleanup.delete_recordings)."""
    from ..services.file_cleanup import delete_recordings
    if not targets:
        return {"purged": 0, "removed_files": 0, "freed_bytes": 0, "freed_mb": 0.0}
    return delete_recordings(db, targets, delete_files, batch_size, pause)


def sweep_empty_recordings(db, min_age_minutes: int = 10) -> int:
    """Auto-purge for recordings already stored: with Auto-purge on, delete
    device recordings that show nothing (see _empty_recording_query), the
    same way a new upload is judged. Skips manual uploads, anything still
    processing or newer than min_age_minutes, and recordings someone
    labeled, wrote notes on or sent to iNaturalist. Without "all device
    recordings", only those whose device score was under the auto-purge
    threshold go. Returns how many were deleted."""
    from datetime import datetime as _dt, timedelta as _td
    from ..models import Recording, AppSettings as _AS
    s = db.query(_AS).filter(_AS.id == 1).first()
    if not s or not getattr(s, "auto_purge_empty_recordings", False):
        return 0
    purge_all = bool(getattr(s, "auto_purge_all_device", False))
    threshold = float(getattr(s, "auto_purge_min_confidence", 0.65) or 0.65)
    cutoff = _dt.utcnow() - _td(minutes=min_age_minutes)
    q = (_empty_recording_query(db, "no_detections")
         .filter(Recording.device_id.isnot(None),
                 Recording.is_bat.is_(False),
                 Recording.bird_buddy_media_id.is_(None),
                 Recording.processing_status.in_(["done", "error"]),
                 Recording.created_at < cutoff))
    targets = []
    for rec in q.all():
        if rec.label or rec.notes or getattr(rec, "inat_observation_id", None):
            continue
        if not purge_all and max((float(d.confidence or 0) for d in rec.detections), default=0.0) >= threshold:
            continue
        targets.append(rec)
    if targets:
        logger.info("Auto-purge sweep: deleting %d recording(s) that show no detections", len(targets))
    return _delete_recordings(db, targets)["purged"]


@router.get("/location/search")
def search_location(q: str, db: Session = Depends(get_db)):
    """Search for a place name → lat/lon via Nominatim (no API key needed)."""
    import httpx
    try:
        resp = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": q, "format": "json", "limit": 5},
            headers={"User-Agent": "Chirp-BirdDetection/1.0"},
            timeout=10,
        )
        return [
            {
                "name": r["display_name"],
                "latitude": float(r["lat"]),
                "longitude": float(r["lon"]),
            }
            for r in resp.json()
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Location search failed: {e}")


@router.get("/device-keys")
def list_device_keys(db: Session = Depends(get_db)):
    """List all device API keys, including their actual value (already
    stored in plaintext on AppSettings.device_api_keys — this endpoint
    previously omitted it from the response even though nothing else
    protected it, which just made it impossible for an admin to tell
    which device is actually using which key when deciding what to
    prune. Requires the same auth as every other admin-only settings
    endpoint; not a new exposure."""
    s = db.query(AppSettings).first()
    keys = (s.device_api_keys or []) if s else []
    return [{"id": k["id"], "name": k["name"], "created_at": k.get("created_at"), "key": k.get("key")} for k in keys]


@router.post("/device-keys", status_code=201)
def create_device_key(body: dict, db: Session = Depends(get_db)):
    """Generate a new device API key. Returns the full key value once at creation."""
    import secrets
    import uuid
    from datetime import datetime
    s = _get_or_create(db)
    new_key = "chirp-" + secrets.token_urlsafe(32)
    entry = {
        "id": str(uuid.uuid4()),
        "name": body.get("name", "Device"),
        "key": new_key,
        "created_at": datetime.utcnow().isoformat(),
    }
    existing = list(s.device_api_keys or [])
    existing.append(entry)
    s.device_api_keys = existing
    db.commit()
    return entry   # full key returned ONCE here; list endpoint never exposes it


@router.delete("/device-keys/{key_id}", status_code=204)
def delete_device_key(key_id: str, db: Session = Depends(get_db)):
    """Delete a device API key by id."""
    s = _get_or_create(db)
    s.device_api_keys = [k for k in (s.device_api_keys or []) if k["id"] != key_id]
    db.commit()

def _test_email_target(db):
    from ..services.email_service import _get_smtp_config, _get_server_url
    cfg = _get_smtp_config(db)
    if not cfg:
        raise HTTPException(400, "SMTP not configured — set host, username, and from address first")
    if not cfg.get("admin_email"):
        raise HTTPException(400, "Admin email not set")
    return cfg, cfg["admin_email"], _get_server_url(db)


@router.post("/test-email")
def send_test_email(db: Session = Depends(get_db)):
    """Send a test email to verify SMTP configuration."""
    from ..services.email_service import _send, _wrap_html, _info_box
    cfg, to, server_url = _test_email_target(db)
    html = _wrap_html("Test Email", "Your Chirp email settings work.",
                      _info_box("Your Chirp email settings are working. \U0001F426"),
                      server_url=server_url)
    if _send(cfg, to, "[Chirp] Test email", html, text="Your Chirp email settings are working."):
        return {"ok": True, "message": f"Test email sent to {to}"}
    raise HTTPException(500, "Failed to send — check SMTP settings and server logs")


@router.post("/save-env")
def save_to_env(db: Session = Depends(get_db)):
    """
    Write current SMTP/email settings from the DB into /app/data/.env so they
    survive container rebuilds. Creates the file if it doesn't exist; updates
    existing CHIRP_SMTP_* keys in-place; leaves all other lines untouched.
    """
    import os, re

    s = _get_or_create(db)
    env_path = "/app/data/.env"

    # Fields to persist (key → current DB value)
    smtp_fields = {
        "CHIRP_SMTP_HOST":         s.smtp_host         or "",
        "CHIRP_SMTP_PORT":         str(s.smtp_port)     if s.smtp_port else "587",
        "CHIRP_SMTP_USERNAME":     s.smtp_username      or "",
        "CHIRP_SMTP_PASSWORD":     s.smtp_password      or "",
        "CHIRP_SMTP_FROM_ADDRESS": s.smtp_from_address  or "",
        "CHIRP_SMTP_USE_TLS":      "true" if s.smtp_use_tls else "false",
        "CHIRP_ADMIN_EMAIL":       s.admin_email        or "",
    }

    # Read existing file if present
    existing_lines = []
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            existing_lines = f.readlines()

    # Update or append each key
    updated_keys = set()
    new_lines = []
    for line in existing_lines:
        match = re.match(r"^(CHIRP_SMTP_\w+|CHIRP_ADMIN_EMAIL)\s*=", line)
        if match:
            key = match.group(1)
            if key in smtp_fields:
                new_lines.append(f"{key}={smtp_fields[key]}\n")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    # Append any keys that weren't already in the file
    missing = [k for k in smtp_fields if k not in updated_keys]
    if missing:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append("\n# Email / SMTP (written by Chirp Settings UI)\n")
        for key in missing:
            new_lines.append(f"{key}={smtp_fields[key]}\n")

    os.makedirs(os.path.dirname(env_path), exist_ok=True)
    with open(env_path, "w") as f:
        f.writelines(new_lines)

    return {
        "ok": True,
        "path": env_path,
        "message": "SMTP settings written to /app/data/.env — they will persist across container rebuilds.",
    }


@router.post("/test-new-bird-email")
def send_test_new_bird_email(db: Session = Depends(get_db)):
    """Send a sample new-species email (the site's latest identification) to the admin address."""
    from ..models import Detection, Recording
    from ..services.email_service import _send, build_new_bird_email
    cfg, to, server_url = _test_email_target(db)
    d = (db.query(Detection).join(Recording, Recording.id == Detection.recording_id)
         .filter(Recording.deleted_at.is_(None))
         .order_by(Recording.trigger_timestamp.desc()).first())
    name, sci, conf = (d.common_name, d.scientific_name, float(d.confidence or 0)) if d \
        else ("Wood Thrush", "Hylocichla mustelina", 0.87)
    subject, html, images = build_new_bird_email(db, name, sci, conf, None, server_url)
    if _send(cfg, to, "[Test] " + subject, html, inline_images=images):
        return {"ok": True, "message": f"Test new-bird email ({name}) sent to {to}"}
    raise HTTPException(500, "Send failed — check SMTP settings and server logs")


@router.post("/test-digest-email")
def send_test_digest_email(db: Session = Depends(get_db)):
    """Send the latest day's digest (today so far, or the most recent day
    with birds in the last two weeks) to the admin address."""
    from datetime import timedelta
    from ..services.email_service import _send, build_daily_digest, compute_day_stats, site_today
    cfg, to, server_url = _test_email_target(db)
    today = site_today(db)
    stats = next((st for st in (compute_day_stats(db, today - timedelta(days=n)) for n in range(14)) if st), None)
    if not stats:
        raise HTTPException(400, "No birds recorded in the last two weeks to build a digest from")
    subject, html, images, text = build_daily_digest(db, server_url, stats=stats)
    if _send(cfg, to, "[Test] " + subject, html, text=text, inline_images=images):
        return {"ok": True, "message": f"Test digest ({stats['day_str']}) sent to {to}"}
    raise HTTPException(500, "Send failed — check SMTP settings and server logs")


# ── Admin: reveal full API key values ─────────────────────────────────────────

@router.get("/reveal-keys")
def reveal_api_keys(request: Request, db: Session = Depends(get_db)):
    """
    Return unmasked API key values to authenticated admins.
    SMTP password is never revealed (write-only).
    """
    from ..api.auth import verify_token
    from ..models import User

    # Require admin role
    auth_header = request.headers.get("Authorization", "")
    token_str   = auth_header[7:] if auth_header.startswith("Bearer ") else None
    user = None
    if token_str:
        payload = verify_token(token_str)
        if payload:
            user = db.query(User).filter(User.username == payload.get("sub")).first()

    # When auth is disabled treat caller as admin; otherwise enforce role
    s_check = db.query(AppSettings).first()
    auth_on = bool(s_check.auth_enabled) if s_check and s_check.auth_enabled is not None else False
    if auth_on and (user is None or user.role != "admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    s = _get_or_create(db)
    # Device keys: return id, name, and full key value for admin review
    device_keys_full = [
        {"id": k.get("id"), "name": k.get("name"), "key": k.get("key", "")}
        for k in (s.device_api_keys or [])
    ]
    return {
        "ebird_api_key":    s.ebird_api_key    or "",
        "ebird_st_api_key": s.ebird_st_api_key or "",
        "inat_api_token":   s.inat_api_token   or "",
        "inat_token_set_at": s.inat_token_set_at.isoformat() if getattr(s, "inat_token_set_at", None) else None,
        "haikubox_serial":  s.haikubox_serial  or "",
        "anthropic_api_key": s.anthropic_api_key or "",
        "openai_api_key": getattr(s, "openai_api_key", None) or "",
        "gemini_api_key": getattr(s, "gemini_api_key", None) or "",
        "server_url":       s.server_url        or "",
        "range_map_sources": s.range_map_sources if s.range_map_sources is not None else {"aab": True, "macaulay": True, "geomodel": True, "birdlife": True},
        "range_map_source_order": s.range_map_source_order if s.range_map_source_order is not None else ["aab", "macaulay", "geomodel", "birdlife", "ebird_st"],
        "device_api_keys":  device_keys_full,
        # smtp_password intentionally omitted — write-only
    }


# ── Database Backup / Restore ──────────────────────────────────────────────────

@router.get("/backup/download")
def download_backup(request: Request, db: Session = Depends(get_db)):
    """Stream a SQLite backup file to the client. Admin only."""
    from fastapi.responses import StreamingResponse

    _require_admin(request, db)
    db_path, _backups_dir, _instance = _current_instance_backup_paths(request)

    import sqlite3

    def generate():
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(":memory:")
        src.backup(dst)
        dst.backup(target := sqlite3.connect(db_path + ".bak.tmp"))
        target.close()
        # Stream the backup as bytes
        with open(db_path + ".bak.tmp", "rb") as f:
            while chunk := f.read(65536):
                yield chunk
        import os
        try: os.remove(db_path + ".bak.tmp")
        except OSError: pass
        src.close()
        dst.close()

    from datetime import datetime
    from ..config import settings as _S
    version = _S.app_version
    fname = f"chirp_v{version}_{_instance.name.replace(' ', '_')}_{datetime.utcnow().strftime('%Y%m%d')}.db"
    return StreamingResponse(
        generate(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@router.post("/backup/restore")
async def restore_backup(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Restore the SQLite database from an uploaded backup. Admin only. Restarts DB."""
    _require_admin(request, db)
    db_path, _backups_dir, instance = _current_instance_backup_paths(request)

    import sqlite3, shutil, os

    # Validate it's a real SQLite database before overwriting
    content = await file.read()
    if not content.startswith(b"SQLite format 3"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid SQLite database.")

    # Write to a temp file and validate
    tmp_path = db_path + ".restore.tmp"
    with open(tmp_path, "wb") as f:
        f.write(content)

    try:
        conn = sqlite3.connect(tmp_path)
        conn.execute("PRAGMA integrity_check")
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        conn.close()
        table_names = {t[0] for t in tables}
        # Must contain at least the recordings table
        if "recordings" not in table_names:
            os.remove(tmp_path)
            raise HTTPException(status_code=400, detail="Backup does not look like a Chirp database (no recordings table).")
    except HTTPException:
        raise
    except Exception as e:
        try: os.remove(tmp_path)
        except OSError: pass
        raise HTTPException(status_code=400, detail=f"Database validation failed: {e}")

    # Backup current DB then replace
    try:
        shutil.copy2(db_path, db_path + ".pre-restore.bak")
    except Exception:
        pass

    from ..instance_registry import _engine_cache, _engine_cache_lock
    with _engine_cache_lock:
        cached_engine = _engine_cache.pop(instance.db_filename, None)
    if cached_engine is not None:
        cached_engine.dispose()

    # This database runs in WAL mode (see instance_registry.py's own
    # PRAGMA setup) — a real -wal/-shm sidecar pair can sit next to
    # db_path holding the PREVIOUS database's own not-yet-checkpointed
    # writes. Confirmed directly as the actual cause of a restore
    # silently reverting: disposing the engine above closes its
    # connections, but doesn't guarantee those sidecar files are gone,
    # and a stale -wal file left behind after the main .db file gets
    # replaced would get replayed onto the newly-restored file by the
    # next connection that opens it, overwriting the very thing that
    # was just restored with whatever the OLD database had pending. The
    # uploaded backup itself is a complete, fully-checkpointed snapshot
    # (SQLite's own .backup() API guarantees this) with nothing of its
    # own to replay, so removing these two files here is always safe.
    for suffix in ("-wal", "-shm"):
        try:
            os.remove(db_path + suffix)
        except OSError:
            pass

    shutil.move(tmp_path, db_path)

    # Re-run the same real per-instance migration/seed logic a brand new
    # instance already gets at provisioning time — the uploaded backup
    # may predate columns or defaults this version of the app expects.
    from ..instance_registry import get_engine_for_instance
    from ..database import _migrate_columns
    try:
        fresh_engine = get_engine_for_instance(instance.db_filename)
        _migrate_columns(fresh_engine)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore succeeded but post-restore migration failed: {e}")

    # The restored data is completely different from whatever this
    # instance's settings/life-list/statistics caches still hold from
    # before the restore — confirmed directly as a real, separate bug:
    # the restore itself succeeds, but the very next read could still
    # show pre-restore values for up to each cache's own TTL. Same root
    # cause and same fix as the Field Guide refresh cache bug fixed
    # earlier this session.
    invalidate_settings()

    return {"ok": True, "tables": sorted(table_names), "message": "Database restored. Please reload the page."}


@router.get("/backup/auto/list")
def list_auto_backups(request: Request, db: Session = Depends(get_db)):
    """Lists automatic backups created by the scheduled backup loop, for the caller's own active instance. Admin only."""
    _require_admin(request, db)
    _db_path, backups_dir, _instance = _current_instance_backup_paths(request)
    from ..services.backup_service import list_backups
    # backups_dir here is the exact same value main.py's own scheduled
    # loop passes as data_dir — list_backups() appends its own "backups"
    # subdir internally (see backup_dir_path()), so passing it directly
    # (not its parent) finds the exact folder the scheduler actually
    # writes into for this instance.
    return list_backups(backups_dir)


@router.post("/backup/auto/run-now")
def run_auto_backup_now(request: Request, db: Session = Depends(get_db)):
    """
    Runs one automatic backup immediately for the caller's own active
    instance, synchronously, and returns the real result or error —
    rather than waiting for the scheduled hour to find out whether it's
    actually working. Admin only.

    Added directly in response to "automatic backups aren't working" —
    before this, the ONLY way to find out whether the daily scheduler
    (see main.py's per-instance auto-backup loop) was succeeding or
    failing was to tail server logs, since failures were only ever a
    logger.warning call with nothing surfaced in Settings. Uses the
    same per-instance path resolution as list_auto_backups above (see
    _current_instance_backup_paths' own docstring for why every backup
    endpoint here must resolve the CALLER's instance, not the single-
    tenant config.settings path).
    """
    _require_admin(request, db)
    s = _get_or_create(db)
    db_path, backups_dir, _instance = _current_instance_backup_paths(request)
    from ..services.backup_service import record_backup_result
    retention = int(s.auto_backup_retention_count) if s.auto_backup_retention_count is not None else 14
    result = record_backup_result(db, s, db_path, backups_dir, retention)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.get("/backup/auto/download/{filename}")
def download_auto_backup(filename: str, request: Request, db: Session = Depends(get_db)):
    """Downloads a specific past automatic backup, for the caller's own active instance, by filename. Admin only."""
    _require_admin(request, db)
    _db_path, backups_dir, _instance = _current_instance_backup_paths(request)
    import os
    from fastapi.responses import FileResponse
    from ..services.backup_service import backup_dir_path

    # Reject anything that isn't a bare filename — no path separators —
    # before joining it onto a real directory path. filename comes
    # straight from the URL path segment, so without this check someone
    # could try something like "../../etc/passwd" here; os.path.basename
    # strips any directory components regardless of what's in the raw
    # string, so the join below can only ever resolve to a file directly
    # inside the backups directory, nothing above or outside it.
    safe_name = os.path.basename(filename)
    path = os.path.join(backup_dir_path(backups_dir), safe_name)
    if not os.path.exists(path):
        raise HTTPException(404, "Backup not found")
    return FileResponse(path, media_type="application/octet-stream", filename=safe_name)


@router.post("/backup/auto/restore/{filename}")
def restore_auto_backup(filename: str, request: Request, db: Session = Depends(get_db)):
    """Restores the caller's own active instance from a specific past automatic backup, by filename. Admin only."""
    _require_admin(request, db)
    db_path, backups_dir, instance = _current_instance_backup_paths(request)
    import os, sqlite3, shutil
    from ..services.backup_service import backup_dir_path

    safe_name = os.path.basename(filename)  # same path-traversal guard as the download endpoint above
    src_path = os.path.join(backup_dir_path(backups_dir), safe_name)
    if not os.path.exists(src_path):
        raise HTTPException(404, "Backup not found")

    conn = sqlite3.connect(src_path)
    try:
        conn.execute("PRAGMA integrity_check")
        tables = {t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    finally:
        conn.close()
    if "recordings" not in tables:
        raise HTTPException(400, "Selected backup does not look like a Chirp database (no recordings table).")

    try:
        shutil.copy2(db_path, db_path + ".pre-restore.bak")
    except Exception:
        pass

    # Same instance-aware engine eviction as /backup/restore above — see
    # that endpoint's own comment for why disposing the single legacy
    # engine here would do nothing for this instance's real connections.
    from ..instance_registry import _engine_cache, _engine_cache_lock
    with _engine_cache_lock:
        cached_engine = _engine_cache.pop(instance.db_filename, None)
    if cached_engine is not None:
        cached_engine.dispose()

    # Same stale WAL-sidecar fix as /backup/restore above — see that
    # endpoint's own comment for why this is required, not optional.
    for suffix in ("-wal", "-shm"):
        try:
            os.remove(db_path + suffix)
        except OSError:
            pass

    shutil.copy2(src_path, db_path)  # copy2, not move — keep the backup file itself intact in the backups dir

    from ..instance_registry import get_engine_for_instance
    from ..database import _migrate_columns
    try:
        fresh_engine = get_engine_for_instance(instance.db_filename)
        _migrate_columns(fresh_engine)
    except Exception as e:
        raise HTTPException(500, f"Restore succeeded but post-restore migration failed: {e}")

    invalidate_settings()  # same cache-staleness fix as /backup/restore above

    return {"ok": True, "restored_from": safe_name, "message": "Database restored. Please reload the page."}


def _require_admin(request: Request, db: Session):
    """Shared admin-check, factored out of the existing backup/restore endpoints above rather than copy-pasted a third time for the three new ones."""
    from ..api.auth import verify_token
    from ..models import User

    auth_header = request.headers.get("Authorization", "")
    token_str = auth_header[7:] if auth_header.startswith("Bearer ") else None
    user = None
    if token_str:
        payload = verify_token(token_str)
        if payload:
            user = db.query(User).filter(User.username == payload.get("sub")).first()
    s_check = db.query(AppSettings).first()
    auth_on = bool(s_check.auth_enabled) if s_check and s_check.auth_enabled is not None else False
    if auth_on and (user is None or user.role != "admin"):
        raise HTTPException(status_code=403, detail="Admin access required")


def _current_instance_backup_paths(request: Request):
    """
    Resolves the CURRENT REQUEST's own active instance to a real
    (db_path, backups_dir) pair — the same convention main.py's own
    scheduled auto-backup loop already uses for exactly this instance
    (see that loop's own comment on why a real, separate backup
    directory per instance matters, same reasoning here).

    Investigated and added directly after confirming every one of the
    five backup/restore endpoints below was still reading
    config.settings.db_url / .data_dir — the single, original,
    deliberately-unused path this multi-tenant fork keeps around only
    for compatibility. Downloading a backup through any of these
    endpoints was silently grabbing an empty, irrelevant file; restoring
    one was silently overwriting that same irrelevant file, leaving the
    real instance's own data completely untouched either way. The
    scheduled loop was already fixed for this exact reason — these
    request-driven endpoints were the one place it was missed.

    Raises the same 400 get_instance_db itself would raise if the
    caller's own token has no active_instance_id resolved yet, rather
    than silently falling back to the wrong path again.
    """
    from ..instance_registry import _resolve_token_state, INSTANCES_DIR
    from ..registry_db import RegistrySessionLocal
    from ..registry_models import Instance
    import os as _os

    has_token, instance_id = _resolve_token_state(request)
    if not has_token or not instance_id:
        raise HTTPException(status_code=400, detail="No active instance selected.")

    reg_db = RegistrySessionLocal()
    try:
        instance = reg_db.query(Instance).filter(Instance.id == instance_id).first()
    finally:
        reg_db.close()
    if not instance:
        raise HTTPException(status_code=404, detail="Your active instance no longer exists.")

    db_path = _os.path.join(INSTANCES_DIR, instance.db_filename)
    backups_dir = _os.path.join(INSTANCES_DIR, f"{instance.id}_backups")
    _os.makedirs(backups_dir, exist_ok=True)
    return db_path, backups_dir, instance


# ── iNaturalist Geomodel range maps ──────────────────────────────────────────

@router.get("/geomodel/status")
def geomodel_status(db: Session = Depends(get_db)):
    """Return download status of the iNaturalist geopackage files."""
    from ..services.geomodel_service import get_status
    from ..config import settings as cfg
    return get_status(cfg.data_dir)


@router.post("/geomodel/download")
def geomodel_download(db: Session = Depends(get_db)):
    """Start background download of both iNaturalist Aves geopackage files."""
    from ..services.geomodel_service import get_status, start_download
    from ..config import settings as cfg
    status = get_status(cfg.data_dir)
    if status.get("downloading"):
        return {"ok": False, "message": "Download already in progress"}
    start_download(cfg.data_dir)
    return {"ok": True, "message": "Download started in background"}


@router.get("/geomodel/debug")
def geomodel_debug(db: Session = Depends(get_db)):
    """Inspect geopackage schema to diagnose iNat model issues."""
    import sqlite3
    from ..services.geomodel_service import _gpkg_paths
    from ..config import settings as cfg

    result = {}
    for path in _gpkg_paths(cfg.data_dir):
        name = path.name
        if not path.exists():
            result[name] = {"status": "missing"}
            continue
        info = {"status": "present", "size_gb": round(path.stat().st_size / 1e9, 2), "tables": {}}
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            for tbl in tables[:10]:
                try:
                    cols = [r[1] for r in conn.execute(f"PRAGMA table_info('{tbl}')").fetchall()]
                    cnt  = conn.execute(f"SELECT COUNT(*) FROM '{tbl}'").fetchone()[0]
                    sample = None
                    if cnt > 0:
                        row = conn.execute(f"SELECT * FROM '{tbl}' LIMIT 1").fetchone()
                        sample = str(row)[:200]
                    info["tables"][tbl] = {"cols": cols, "rows": cnt, "sample": sample}
                except Exception as e:
                    info["tables"][tbl] = {"error": str(e)}
            conn.close()
        except Exception as e:
            info["error"] = str(e)
        result[name] = info
    return result


# ── Haikubox ──────────────────────────────────────────────────────────────────

@router.post("/haikubox/sync")
def trigger_haikubox_sync(request: Request, db: Session = Depends(get_db)):
    """
    Admin endpoint: trigger an immediate Haikubox sync instead of waiting for
    the next 15-minute poll. Returns the number of new detections imported.
    """
    from ..models import AppSettings
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    serial = s.haikubox_serial if s else None
    enabled = bool(getattr(s, "haikubox_enabled", False)) if s else False
    if not enabled:
        raise HTTPException(status_code=400, detail="Haikubox is disabled in Settings → Account & Advanced.")
    if not serial:
        raise HTTPException(status_code=400, detail="No Haikubox serial number configured.")
    from ..services.haikubox_sync import get_sync_service
    import threading
    result = {"status": "started", "serial": serial[:8] + "…"}
    # Run in background so the response returns immediately
    t = threading.Thread(target=get_sync_service()._run_sync, daemon=True, name="haikubox-manual-sync")
    t.start()
    return result


@router.get("/haikubox/status")
def haikubox_status(request: Request, db: Session = Depends(get_db)):
    """Return Haikubox virtual device status and last-seen time.

    Hard-hidden when disabled: returns {"configured": False}, the same
    shape already returned when no serial is set, so every existing
    frontend check (Devices.jsx's haikuboxStatus?.configured,
    Settings.jsx's settings?.haikubox_serial &&) already renders nothing
    correctly with no changes needed on that side. Adds a "disabled": true
    flag specifically for the case where a serial IS configured but the
    master toggle is off, so the frontend can show a clear "currently
    disabled" message instead of the generic first-time onboarding copy.

    Also includes a real "enabled" flag in both never-configured response
    branches — without it, "disabled and never configured" and "enabled
    but never configured" were genuinely indistinguishable from the
    frontend's perspective (both returned {"configured": False, "disabled":
    False}), so a feature-disabled deployment would still show the "Got a
    Haikubox?" onboarding invite, which is misleading for a disabled
    feature.
    """
    from ..models import AppSettings, Device, Recording
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    serial    = s.haikubox_serial    if s else None
    device_id = s.haikubox_device_id if s else None
    enabled   = bool(getattr(s, "haikubox_enabled", False)) if s else False

    if not enabled:
        return {"configured": False, "disabled": bool(serial), "enabled": False}
    if not serial:
        return {"configured": False, "disabled": False, "enabled": True}

    device = db.query(Device).filter(Device.id == device_id).first() if device_id else None
    total = db.query(Recording).filter(
        Recording.device_id == device_id
    ).count() if device_id else 0

    return {
        "configured": True,
        "serial": serial[:8] + "…",
        "status": device.status if device else "never_connected",
        "last_seen": device.last_seen.isoformat() if device and device.last_seen else None,
        "total_recordings": total,
        "device_id": device_id,
    }


@router.get("/bird-buddy/feeders")
async def list_bird_buddy_feeders(db: Session = Depends(get_db)):
    """
    Lists feeders on the configured Bird Buddy account, for the device
    selection picker in Settings. Uses currently-saved credentials —
    doesn't require enabling sync first, so the picker works while
    setting things up.
    """
    from ..models import AppSettings
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    email = getattr(s, "bird_buddy_email", None) if s else None
    password = getattr(s, "bird_buddy_password", None) if s else None
    if not email or not password:
        raise HTTPException(status_code=400, detail="Bird Buddy email/password not configured yet")

    try:
        from birdbuddy.client import BirdBuddy
        bb = BirdBuddy(email, password)
        await bb.refresh()
        return {
            "feeders": [
                {"id": f.id, "name": f.name, "serial": f.serial}
                for f in bb.feeders.values()
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach Bird Buddy: {e}")


@router.post("/bird-buddy/sync-now")
def trigger_bird_buddy_sync(background_tasks: BackgroundTasks):
    """Manually triggers one Bird Buddy sync cycle immediately, rather than
    waiting up to POLL_INTERVAL_SECONDS for the next scheduled one."""
    from ..services.bird_buddy_sync import get_sync_service
    background_tasks.add_task(get_sync_service()._run_sync)
    return {"status": "sync_queued"}


@router.post("/inat/refresh-now")
def trigger_inat_refresh(background_tasks: BackgroundTasks, db: Session = Depends(get_db),
                          current_user=Depends(get_current_user)):
    """Manually fetches a fresh iNaturalist JWT immediately using saved
    username/password (OAuth app credentials optional — see
    InatAuthService.refresh_now, which falls back to simulating a normal
    login if no OAuth app is registered), rather than waiting for the
    next scheduled auto-refresh. Writes the result to the CALLING user's
    personal inat_api_token (see InatAuthService.refresh_now's docstring
    for why this is per-user, not a shared server-wide value).

    No pre-flight validation here beyond auth — refresh_now() already
    does its own correct check (per-user fields, OAuth optional) and
    returns False if nothing's configured.
    """
    from ..services.inat_auth import get_service
    try:
        refreshed = get_service().refresh_now(user_id=current_user.id)
        return {"status": "refreshed" if refreshed else "skipped"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Refresh failed: {e}")


@router.post("/inat/test")
def test_inat_connection(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """
    Tests whichever token would actually be used for THIS user's
    submissions right now: their personal inat_api_token if set (the
    override — see User.inat_api_token), otherwise the global
    AppSettings.inat_api_token fallback. Calls the real iNaturalist API to
    confirm the token is genuinely accepted, not just present/non-empty.
    """
    from ..models import AppSettings
    from ..services.inat_auth import test_inat_token

    token = getattr(current_user, "inat_api_token", None)
    source = "personal"
    if not token:
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        token = getattr(s, "inat_api_token", None) if s else None
        source = "global fallback"

    if not token:
        raise HTTPException(status_code=400, detail="No iNaturalist token configured — add your personal token, or ask an admin to set one up")

    try:
        info = test_inat_token(token)
        return {"ok": True, "source": source, **info}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Token test failed: {e}")


class AiKeyTestRequest(BaseModel):
    provider: str  # "anthropic" | "openai" | "gemini" | "ollama"
    api_key: Optional[str] = None  # if omitted, tests whatever's already stored for that provider
    base_url: Optional[str] = None  # ollama only — testing an unsaved value, same idea as api_key above
    model: Optional[str] = None     # ollama only


@router.post("/ai/test")
def test_ai_key(body: AiKeyTestRequest, db: Session = Depends(get_db)):
    """
    Tests an AI provider with the cheapest real call each one offers.
    Accepts an explicit api_key (or, for ollama, base_url/model — testing
    a value not yet saved, the Settings page's Test button next to an
    unsaved field), or if omitted, tests whatever's currently stored.
    """
    from ..models import AppSettings
    from ..services.ai_providers import test_provider_key

    if body.provider == "ollama":
        base_url = body.base_url
        model = body.model
        if not base_url or not model:
            s = db.query(AppSettings).filter(AppSettings.id == 1).first()
            base_url = base_url or (getattr(s, "ollama_base_url", None) if s else None)
            model = model or (getattr(s, "ollama_model", None) if s else None)
        if not base_url or not model:
            raise HTTPException(status_code=400, detail="Ollama needs both a base URL and a model name configured or provided")
        import json as _json
        credential = _json.dumps({"base_url": base_url.rstrip("/"), "model": model})
        try:
            return test_provider_key("ollama", credential)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Key test failed: {e}")

    api_key = body.api_key
    if not api_key:
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        key_map = {"anthropic": "anthropic_api_key", "openai": "openai_api_key", "gemini": "gemini_api_key"}
        field = key_map.get(body.provider)
        if not field:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {body.provider}")
        api_key = getattr(s, field, None) if s else None

    if not api_key:
        raise HTTPException(status_code=400, detail=f"No {body.provider} API key configured or provided")

    try:
        return test_provider_key(body.provider, api_key)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Key test failed: {e}")


@router.get("/ai/ollama/models")
def list_ollama_models(base_url: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Lists models already pulled on the configured (or given) Ollama
    server — the same {base_url}/api/tags call test_provider_key()
    already makes for its own "is the configured model there"
    check, exposed as its own endpoint so Settings can show the full
    list, not just confirm one specific model.
    """
    from ..models import AppSettings
    if not base_url:
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        base_url = getattr(s, "ollama_base_url", None) if s else None
    if not base_url:
        raise HTTPException(status_code=400, detail="No Ollama base URL configured or provided")
    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=10.0)
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach Ollama server: {e}")
    models = resp.json().get("models", [])
    return {
        "models": [
            {"name": m.get("name", ""), "size_bytes": m.get("size"), "modified_at": m.get("modified_at")}
            for m in models
        ]
    }


class OllamaPullRequest(BaseModel):
    model: str
    base_url: Optional[str] = None  # testing/pulling to a not-yet-saved URL, same idea as AiKeyTestRequest above


@router.post("/ai/ollama/pull")
def pull_ollama_model(body: OllamaPullRequest, db: Session = Depends(get_db)):
    """
    Downloads a model onto the Ollama server directly from Settings,
    instead of needing to SSH into wherever Ollama is running and run
    `ollama pull <model>` by hand. Blocks for the duration of the
    download rather than streaming progress back — a pull can run
    several minutes for a multi-gigabyte model, hence the long timeout,
    but a live progress bar would need a second endpoint to poll (or a
    streamed response) for what's still a fairly rare, one-off action;
    not worth that complexity for a first pass. stream=False on the
    Ollama side collapses its own NDJSON progress stream into a single
    final response for the same reason.
    """
    model = (body.model or "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="Model name is required")

    from ..models import AppSettings
    base_url = body.base_url
    if not base_url:
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        base_url = getattr(s, "ollama_base_url", None) if s else None
    if not base_url:
        raise HTTPException(status_code=400, detail="No Ollama base URL configured or provided")

    try:
        resp = httpx.post(
            f"{base_url.rstrip('/')}/api/pull",
            json={"name": model, "stream": False},
            timeout=900.0,  # large models can take this long over a slow connection
        )
        resp.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"Pulling '{model}' timed out after 15 minutes — it may still be downloading on the Ollama server; check back or try a smaller model.")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach Ollama server: {e}")

    result = resp.json()
    status = result.get("status", "")
    if status not in ("success", ""):
        # Ollama's non-streaming pull still returns 200 with an error
        # message INSIDE the body for some failure modes (e.g. an
        # unknown model name) rather than a non-2xx status code — a 200
        # here doesn't necessarily mean it worked.
        raise HTTPException(status_code=502, detail=f"Ollama reported: {status}")
    return {"ok": True, "model": model, "status": status or "success"}


@router.get("/tailscale-status")
def get_tailscale_status(request: Request, db: Session = Depends(get_db)):
    """
    Read-only status for the server's own Tailscale/Headscale connection
    (see tailscale_manager.py) — whether it's enabled, whether the
    binary is present, whether it's currently connected, and its IP if
    so. Admin-only. One Tailscale identity per container regardless of
    which instance is currently active — the manager itself lives on
    app.state, set once at startup, not per-instance.
    """
    _require_admin(request, db)
    mgr = request.app.state.tailscale_manager if hasattr(request.app.state, "tailscale_manager") else None
    if mgr is None:
        return {"enabled": False, "binary_installed": False, "connected": False, "ip": None, "login_server": None}
    return mgr.status()


@router.get("/dashboard-sections")
def list_dashboard_sections():
    """
    The fixed list of Dashboard sections an admin can show/hide, plus
    the currently-saved full/simplified selections — one call instead
    of the frontend needing to separately fetch the static list and the
    saved settings. Null selections mean "everything" (see models.py's
    own comment on the two columns), left as null in the response too
    rather than expanded into an explicit list here — that expansion is
    the Settings UI's own job when it renders every checkbox as checked
    by default, not something to bake into the API response itself.
    """
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        return {
            "sections": DASHBOARD_SECTIONS,
            "full": getattr(s, "dashboard_sections_full", None) if s else None,
            "simplified": getattr(s, "dashboard_sections_simplified", None) if s else None,
        }
    finally:
        db.close()


@router.get("/ai/usage")
def get_ai_usage(db: Session = Depends(get_db)):
    """
    Aggregated API usage across every AI feature (photo_id, call_reanalysis,
    daily_summary, profile_summary), grouped by provider — call counts and
    token totals, both all-time and last-30-days. Read-only visibility;
    Chirp doesn't know each provider's actual per-token pricing (which
    varies by model and changes over time), so this reports real counts
    rather than a guessed dollar estimate that could be meaningfully wrong.
    """
    from ..models import AiUsageLog
    from sqlalchemy import func as _func
    from datetime import datetime as _dt, timedelta as _td

    thirty_days_ago = _dt.utcnow() - _td(days=30)

    def _aggregate(query):
        rows = (
            query
            .with_entities(
                AiUsageLog.provider,
                _func.count(AiUsageLog.id).label("calls"),
                _func.sum(AiUsageLog.input_tokens).label("input_tokens"),
                _func.sum(AiUsageLog.output_tokens).label("output_tokens"),
            )
            .group_by(AiUsageLog.provider)
            .all()
        )
        return {
            r.provider: {
                "calls": r.calls,
                "input_tokens": int(r.input_tokens or 0),
                "output_tokens": int(r.output_tokens or 0),
            }
            for r in rows
        }

    all_time = _aggregate(db.query(AiUsageLog))
    last_30d = _aggregate(db.query(AiUsageLog).filter(AiUsageLog.created_at >= thirty_days_ago))

    # By feature too, all-time only — enough to see which feature is
    # actually driving usage without a second full breakdown by provider.
    feature_rows = (
        db.query(AiUsageLog)
        .with_entities(AiUsageLog.feature, _func.count(AiUsageLog.id).label("calls"))
        .group_by(AiUsageLog.feature)
        .all()
    )
    by_feature = {r.feature: r.calls for r in feature_rows}

    providers = ("anthropic", "openai", "gemini", "ollama")
    return {
        "all_time": {p: all_time.get(p, {"calls": 0, "input_tokens": 0, "output_tokens": 0}) for p in providers},
        "last_30d": {p: last_30d.get(p, {"calls": 0, "input_tokens": 0, "output_tokens": 0}) for p in providers},
        "by_feature": by_feature,
    }
