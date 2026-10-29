"""
Chirp Server Database Setup
SQLAlchemy async engine with SQLite.
"""
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import NullPool
from .config import settings

logger = logging.getLogger(__name__)

# NullPool: no connection pooling — each request gets its own SQLite connection.
# Eliminates QueuePool exhaustion when many requests fire simultaneously.
# SQLite handles its own internal locking; pooling adds no benefit for a local file.
engine = create_engine(
    settings.db_url,
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
    echo=settings.debug,
)


# No PRAGMA tuning existed before this at all — SQLite was running under its
# default rollback-journal mode, where every write transaction takes an
# exclusive lock on the ENTIRE database file for its duration, blocking every
# concurrent reader until it commits. This app is not a single-writer,
# single-reader toy: the device upload endpoint, two 15-minute background
# sync services (Haikubox, Bird Buddy), bat/bird background processing tasks,
# and every page's API requests all hit this same SQLite file concurrently.
# Combined with NullPool's connection-per-request pattern (many short-lived
# connections rather than a few long-lived pooled ones), the default
# rollback-journal mode meant a single in-flight write (e.g. a
# processing_status update) could stall every other request hitting the API
# at the same moment.
#
# WAL (write-ahead log) mode lets readers proceed concurrently with a single
# writer instead of blocking — the standard fix for exactly this pattern, and
# safe for a locally-mounted file (not recommended over network filesystems
# like NFS, but this is Chirp's own Docker volume on the Unraid array, not a
# network mount from the container's perspective).
# synchronous=NORMAL is the documented safe pairing with WAL (full durability
# against application crashes; a very small window of vulnerability only on
# an actual OS crash or power loss, which is an acceptable tradeoff here for
# the write-latency improvement — full FULL synchronous is not needed with
# WAL's own crash-safety guarantees for this use case).
@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA cache_size=-64000")   # ~64MB page cache, negative = KB not pages
    cur.execute("PRAGMA busy_timeout=15000")  # wait up to 15s on a lock instead of raising immediately
    cur.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _fix_stuck_pending_approvals(db):
    """Fix accounts that were activated via setActive but still have pending_approval=True."""
    try:
        from .models import User
        stuck = db.query(User).filter(
            User.active == True,
            User.pending_approval == True,
        ).all()
        if stuck:
            for u in stuck:
                u.pending_approval = False
            db.commit()
            logger.info("Fixed %d stuck pending-approval users", len(stuck))
    except Exception as e:
        logger.warning("_fix_stuck_pending_approvals: %s", e)


def _fix_swapped_taxonomy(db):
    log = logging.getLogger("chirp.db")
    """Fix profiles where common_name looks like a scientific name (from BirdNET label format)."""
    from .models import BirdProfile
    import re
    def looks_scientific(name):
        if not name: return False
        words = name.strip().split()
        return (len(words) == 2 and words[0][0].isupper()
                and words[1][0].islower()
                and re.match(r"^[a-z]+$", words[1]))
    try:
        fixed = 0
        for p in db.query(BirdProfile).all():
            if looks_scientific(p.common_name) and p.scientific_name and not looks_scientific(p.scientific_name):
                p.common_name, p.scientific_name = p.scientific_name, p.common_name
                fixed += 1
        if fixed:
            db.commit()
            log.info("Fixed taxonomy swap for %d bird profiles", fixed)
    except Exception as e:
        log.info(f"_fix_swapped_taxonomy error: {e}")


def _clear_stale_description_sections(db):
    """
    Clear description_sections and enrichment_complete for profiles that have
    no sections stored (enriched with old code before Wikipedia section support).
    This forces re-enrichment to fetch proper multi-section Wikipedia content.
    """
    log = logging.getLogger("chirp.db")
    from .models import BirdProfile
    try:
        stale = db.query(BirdProfile).filter(
            BirdProfile.enrichment_complete == True,
            BirdProfile.description_sections == None,
        ).all()
        if stale:
            for p in stale:
                p.enrichment_complete = False  # triggers re-enrich on next access
            db.commit()
            log.info("Marked %d bird profiles for re-enrichment (no sections)", len(stale))
    except Exception as e:
        log.info(f"Migration _clear_stale_description_sections error: {e}")


def _clear_stale_aab_data(db):
    """
    Same real pattern as _clear_stale_description_sections just above,
    for the same real reason: a profile that was already fully enriched
    BEFORE Cornell Lab / All About Birds support existed (aab_description,
    aab_cool_facts, the habitat/food/nesting/behavior tags — see
    bird_enricher.py) has enrichment_complete=True but aab_fetched_at is
    still NULL, and nothing was ever re-triggering enrichment for
    already-completed profiles — a real, confirmed cause of a direct
    report ("I don't see the new sections... running latest version"):
    the new sections were real and working, but only for profiles
    enriched fresh AFTER that code shipped; every profile enriched
    before it stayed permanently missing the new data with no way to
    pick it up short of a manual per-species "Refresh" click.
    """
    log = logging.getLogger("chirp.db")
    from .models import BirdProfile
    try:
        stale = db.query(BirdProfile).filter(
            BirdProfile.enrichment_complete == True,
            BirdProfile.aab_fetched_at == None,
        ).all()
        if stale:
            for p in stale:
                p.enrichment_complete = False  # triggers re-enrich (including the new AAB step) on next access
            db.commit()
            log.info("Marked %d bird profiles for re-enrichment (missing Cornell Lab / All About Birds data)", len(stale))
    except Exception as e:
        log.info(f"Migration _clear_stale_aab_data error: {e}")


def _clear_blocked_aab_data(db):
    """
    Companion to _clear_stale_aab_data just above, for a distinct real
    cause of the same symptom (no Cool Facts / AAB content showing on a
    profile): before this fix, a Cloudflare-blocked AAB fetch attempt
    (the "Attention Required" challenge page) was indistinguishable from
    a confirmed "AAB genuinely has no page for this species" result —
    both stamped aab_fetched_at permanently, silencing all future
    retries. AAB's Cloudflare blocking has been a real, recurring,
    long-standing issue across many sessions (see CHANGELOG), so any
    profile that happened to be enriched during a blocked window is
    permanently stuck with no AAB data, with no way to recover short of
    a manual per-species "Refresh" click — the direct cause of a report
    that Cool Facts added "a few versions ago" aren't actually showing.

    Targets profiles that were stamped as fetched but got no URL — the
    real, reliable signature of a past blocked/failed attempt, since
    aab_url is only ever set on a successful fetch (see bird_enricher.py).
    Deliberately does NOT also check aab_cool_facts: it's a JSON column,
    and SQLAlchemy serializes a Python None assigned to it as the JSON
    text 'null', not SQL NULL — an `== None` filter on a JSON column
    silently never matches, confirmed by a real failing integration test
    against this exact query before this fix. aab_url (a plain String
    column) doesn't have that pitfall and is sufficient on its own.
    """
    log = logging.getLogger("chirp.db")
    from .models import BirdProfile
    try:
        stale = db.query(BirdProfile).filter(
            BirdProfile.enrichment_complete == True,
            BirdProfile.aab_fetched_at != None,
            BirdProfile.aab_url == None,
        ).all()
        if stale:
            for p in stale:
                p.aab_fetched_at = None      # actual retry trigger, read by _do_enrich's own gate
                p.enrichment_complete = False  # triggers re-enrich on next access
            db.commit()
            log.info("Marked %d bird profiles for AAB retry (previously stamped with no data — likely a past Cloudflare block)", len(stale))
    except Exception as e:
        log.info(f"Migration _clear_blocked_aab_data error: {e}")


def init_db():
    """Create all tables and run any pending column migrations on startup."""
    from . import models  # noqa: F401 — ensures models are registered
    Base.metadata.create_all(bind=engine)
    _migrate_columns()
    with SessionLocal() as _db:
        _fix_stuck_pending_approvals(_db)
        _reset_dashboard_mode_once(_db)
        # Real, confirmed bug fixed here: both of these were fully
        # implemented but never actually called anywhere in the
        # codebase — dead code, not a deliberate no-op. Their whole
        # purpose is exactly this: real, safe, idempotent one-time
        # fixes that run on every startup but only ever ACT on rows
        # that genuinely need it, so wiring them in now is a real
        # improvement with no downside for anyone already fully
        # migrated. _clear_stale_aab_data specifically is the direct
        # fix for a real report: Cornell Lab content not appearing on
        # profiles that were already enriched before that feature shipped.
        _fix_swapped_taxonomy(_db)
        _clear_stale_description_sections(_db)
        _clear_stale_aab_data(_db)
        _clear_blocked_aab_data(_db)
        _fix_comment_edited_timestamps(_db)


def _fix_comment_edited_timestamps(db):
    """
    One-time cleanup for comments posted before the Comment.updated_at
    schema fix (see models.py's own comment on the column definition):
    every comment ever posted got a stored updated_at value a few
    microseconds after created_at, purely from two independent
    datetime.utcnow() calls at INSERT time — not a genuine edit. The
    model change only affects comments posted after this fix ships;
    existing rows keep their already-stored (and misleadingly non-null)
    updated_at forever unless cleaned up here, which is exactly what
    was reported: an existing comment kept showing "(edited)" with no
    edit ever having happened. A comment is treated as never edited if
    the gap between the two timestamps is under 5 seconds — comfortably
    wider than any realistic delay between the two default callables at
    insert time, while still leaving comments edited later
    (at minimum seconds, more often minutes or longer, after posting in
    practice) untouched.
    """
    log = logging.getLogger("chirp.db")
    from .models import Comment
    from datetime import timedelta
    try:
        fixed = 0
        for c in db.query(Comment).filter(Comment.updated_at.isnot(None)).all():
            if c.created_at and c.updated_at and abs(c.updated_at - c.created_at) < timedelta(seconds=5):
                c.updated_at = None
                fixed += 1
        if fixed:
            db.commit()
            log.info("Cleared spurious 'edited' flag on %d comments that were never edited", fixed)
    except Exception as e:
        log.info(f"_fix_comment_edited_timestamps error: {e}")


def _reset_dashboard_mode_once(db):
    """
    One-time reset: clears dashboard_mode for every existing user, guarded
    by AppSettings.dashboard_mode_reset_v1_done so this only ever runs
    once, on the first startup after this feature shipped — not on every
    restart, which would keep wiping people's actual choices.

    Why this exists: the picker was gated behind the Dashboard's own
    "stats not loaded yet" early-return, so on the version that first
    shipped it, it effectively never appeared for anyone (new accounts
    included) until that render-order bug was also fixed in this same
    release. Existing accounts should still see the picker once now that
    it actually works, rather than being silently stuck on whatever
    default they'd never actually chosen.
    """
    from .models import AppSettings, User
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if s is not None and s.dashboard_mode_reset_v1_done:
        return
    db.query(User).update({User.dashboard_mode: None})
    if s is None:
        s = AppSettings(id=1, dashboard_mode_reset_v1_done=True)
        db.add(s)
    else:
        s.dashboard_mode_reset_v1_done = True
    db.commit()


def _migrate_columns():
    """
    Lightweight column migration: adds any columns that exist in the ORM models
    but are missing from the live SQLite tables. Runs at every startup; safe to
    call repeatedly — skips columns that already exist.

    This replaces a full Alembic setup for the simple schema changes we make.
    """
    from sqlalchemy import text, inspect

    log = logging.getLogger("chirp.db")
    # New tables (near_misses, reanalysis_runs, ...) for databases that
    # predate them.
    try:
        from . import models  # noqa: F401
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        log.warning("DB migration: create_all failed: %s", e)
    insp = inspect(engine)

    # Map of table_name → list of (col_name, col_type_ddl)
    # Add any future new columns here alongside the model change.
    # All columns ever added to existing tables must be listed here.
    # Startup runs ALTER TABLE ADD COLUMN for any that are missing.
    # Safe to run repeatedly — skips already-existing columns.
    pending = {
        "recordings": [
            ("inat_observation_id",  "VARCHAR"),
            ("inat_observation_url", "VARCHAR"),
            ("ai_reanalysis_note",           "TEXT"),
            ("ai_reanalysis_generated_at",   "DATETIME"),
            ("ai_reanalysis_error",          "VARCHAR"),
            ("ai_reanalysis_verdict",        "VARCHAR"),
            ("deleted_at", "DATETIME"),
            ("file_size_bytes", "INTEGER"),
            ("label",            "TEXT"),
            ("bird_buddy_media_id", "VARCHAR"),
            ("bird_buddy_video_path", "VARCHAR"),
            ("birdweather_soundscape_id", "VARCHAR"),
            ("notes",            "TEXT"),
            ("device_id",        "VARCHAR"),
            ("processing_error", "TEXT"),
            ("is_live_session",  "BOOLEAN DEFAULT 0"),
            ("is_saved",         "BOOLEAN DEFAULT 0"),
            ("is_live_detect_clip", "BOOLEAN DEFAULT 0"),
            ("shadow_checked_at", "DATETIME"),
            # Added for device GPS tagging (chirp_fixed6+)
            ("latitude",         "REAL"),
            ("longitude",        "REAL"),
            # Added for Haikubox deduplication
            ("haikubox_detection_id", "VARCHAR"),
            # Added when bat activity moved from the standalone bat_activity
            # table into Recording/Detection (see services/bat_profile_content.py)
            ("is_bat",      "BOOLEAN"),
            ("bat_metadata", "JSON"),
            # Added for the archive feature — see Recording.archived_at's
            # full docstring for why this is deliberately distinct from
            # deleted_at above.
            ("archived_at", "DATETIME"),
            # Added for the SNR quality signal — see Recording.snr_db's
            # own comment in models.py for the full reasoning.
            ("snr_db", "REAL"),
            # Live Detect from a phone (Chirp Live): the place it was made.
            ("place_name", "VARCHAR"),
        ],
        "bird_profiles": [
            ("notes",                   "TEXT"),
            ("is_bat",                  "BOOLEAN"),
            ("ai_presence_summary",             "TEXT"),
            ("ai_presence_summary_generated_at", "DATETIME"),
            ("ai_presence_summary_error",        "VARCHAR"),
            ("range_map_source",         "VARCHAR"),
            ("photo_thumb_path",        "VARCHAR"),
            ("description_sections",    "JSON"),
            ("range_map_url",           "VARCHAR"),
            ("conservation_status",     "VARCHAR"),
            ("conservation_authority",  "VARCHAR"),
            ("extra_photos",            "JSON"),
            # Cornell Lab of Ornithology / All About Birds enrichment
            ("aab_url",                 "VARCHAR"),
            ("aab_description",         "TEXT"),
            ("aab_cool_facts",          "JSON"),
            ("aab_habitat",             "VARCHAR"),
            ("aab_food",                "VARCHAR"),
            ("aab_nesting",             "VARCHAR"),
            ("aab_behavior",            "VARCHAR"),
            ("aab_fetched_at",          "DATETIME"),
            # Added for the At a Glance size-comparison ruler — a
            # separate AAB page/tab (/id, not /overview) from everything
            # else above.
            ("aab_length_min_cm",       "REAL"),
            ("aab_length_max_cm",       "REAL"),
            ("aab_length_text",         "VARCHAR"),
            # Life History card additions
            ("aab_conservation",        "VARCHAR"),
            ("aab_habitat_text",        "TEXT"),
            ("aab_food_text",           "TEXT"),
            ("aab_nesting_text",        "TEXT"),
            ("aab_behavior_text",       "TEXT"),
            ("aab_conservation_text",   "TEXT"),
            # Added for iNaturalist monthly frequency chart (chirp_fixed12+)
            ("monthly_frequency",       "JSON"),
            # Added for iNaturalist integration
            ("inaturalist_id",          "INTEGER"),
            ("inaturalist_url",         "VARCHAR"),
            ("ebird_data",              "JSON"),
            ("ebird_species_code",      "VARCHAR"),
            ("order_name",              "VARCHAR"),
            ("family_name",             "VARCHAR"),
            ("last_enriched",           "DATETIME"),
            ("enrichment_complete",     "BOOLEAN"),
            ("call_media",              "JSON"),
            ("photo_url",               "VARCHAR"),
            ("photo_credit",            "VARCHAR"),
            # Added for per-species BirdLife/AAB legend extraction + eager
            # range-map pre-fetch on enrichment (chirp_0.1.10.w+)
            ("birdlife_legend",         "JSON"),
            ("aab_legend",              "JSON"),
            ("range_maps_prefetched_at","DATETIME"),
        ],
        "regional_species": [
            ("days_seen",       "INTEGER"),
            ("total_days",      "INTEGER"),
            ("family_com_name", "VARCHAR"),
            ("order_name",      "VARCHAR"),
            ("photo_url",    "VARCHAR"),
            ("region_code",  "VARCHAR"),
            ("fetched_at",   "DATETIME"),
        ],
        "app_settings": [
            ("digest_last_sent_on",         "VARCHAR"),
            ("digest_push_hour",            "INTEGER"),
            ("digest_email_hour",           "INTEGER"),
            ("digest_push_sent_on",         "VARCHAR"),
            ("digest_email_sent_on",        "VARCHAR"),
            ("birdnet_species_thresholds", "JSON"),
            ("night_threshold_mode",       "VARCHAR DEFAULT 'night'"),
            ("night_threshold_species",    "JSON"),
            ("ebird_st_api_key",            "VARCHAR"),
            ("inat_api_token",              "VARCHAR"),
            ("inat_token_set_at",           "DATETIME"),
            ("server_url",                  "VARCHAR"),
            ("haikubox_serial",             "VARCHAR"),
            ("haikubox_device_id",          "VARCHAR"),
            ("bird_buddy_enabled",          "BOOLEAN"),
            ("bird_buddy_email",            "VARCHAR"),
            ("bird_buddy_password",         "VARCHAR"),
            ("bird_buddy_selected_feeders", "JSON"),
            ("bird_buddy_last_sync_at",     "DATETIME"),
            ("bird_buddy_last_sync_error",  "VARCHAR"),
            ("birdweather_enabled",         "BOOLEAN"),
            ("birdweather_token",           "VARCHAR"),
            ("birdweather_cursor_at",       "DATETIME"),
            ("birdweather_last_sync_at",    "DATETIME"),
            ("birdweather_last_sync_error", "VARCHAR"),
            ("inat_username",                "VARCHAR"),
            ("inat_password",                "VARCHAR"),
            ("inat_oauth_client_id",         "VARCHAR"),
            ("inat_oauth_client_secret",     "VARCHAR"),
            ("inat_auto_refresh_enabled",    "BOOLEAN"),
            ("dashboard_mode_reset_v1_done", "BOOLEAN"),
            ("dashboard_sections_full",       "JSON"),
            ("dashboard_sections_simplified", "JSON"),
            ("openai_api_key",              "VARCHAR"),
            ("gemini_api_key",              "VARCHAR"),
            ("ollama_base_url",             "VARCHAR"),
            ("ollama_model",                "VARCHAR"),
            ("ollama_api_key",              "VARCHAR"),
            ("vapid_public_key",            "VARCHAR"),
            ("vapid_private_key",           "VARCHAR"),
            ("apns_team_id",                "VARCHAR"),
            ("apns_key_id",                 "VARCHAR"),
            ("apns_bundle_id",               "VARCHAR"),
            ("apns_auth_key",                "TEXT"),
            ("apns_production",              "BOOLEAN"),
            ("push_relay_url",               "VARCHAR"),
            ("push_relay_token",             "VARCHAR"),
            ("ai_feature_providers",        "JSON"),
            ("daily_summary_schedule_time", "VARCHAR"),
            ("daily_summary_schedule_times", "JSON"),
            ("profile_summary_auto_refresh", "BOOLEAN"),
            ("profile_summary_refresh_days", "INTEGER"),
            ("profile_summary_refresh_hour", "INTEGER"),
            ("auto_backup_enabled", "BOOLEAN"),
            ("auto_backup_hour", "INTEGER"),
            ("auto_backup_retention_count", "INTEGER"),
            ("ai_personality_friendliness", "INTEGER"),
            ("ai_personality_informational", "INTEGER"),
            ("ai_personality_irreverence", "INTEGER"),
            ("ai_personality_depth", "INTEGER"),
            ("ai_personality_curiosity", "INTEGER"),
            ("ai_web_search_enabled", "BOOLEAN"),
            ("daily_summary_recent_openings", "JSON"),
            ("daily_summary_text",          "TEXT"),
            ("daily_summary_generated_at",  "DATETIME"),
            ("daily_summary_error",         "VARCHAR"),
            ("weekly_summary_text",           "TEXT"),
            ("weekly_summary_generated_at",   "DATETIME"),
            ("weekly_summary_period_start",   "DATETIME"),
            ("weekly_summary_period_end",     "DATETIME"),
            ("weekly_summary_error",          "VARCHAR"),
            ("weekly_summary_recent_openings", "JSON"),
            ("weekly_summary_schedule_day",   "INTEGER"),
            ("weekly_summary_schedule_hour",  "INTEGER"),
            ("inat_last_refresh_error",      "VARCHAR"),
            ("anthropic_api_key",            "VARCHAR"),
            ("bat_detection_enabled",        "BOOLEAN"),
            ("bat_species_id_enabled",       "BOOLEAN"),
            ("bat_species_id_min_confidence", "FLOAT"),
            ("bat_active_hours_start",        "VARCHAR"),
            ("bat_active_hours_end",          "VARCHAR"),
            ("bat_min_swept_fraction",        "REAL"),
            ("bat_max_pulse_rate",            "REAL"),
            ("bat_discard_likely_interference", "BOOLEAN"),
            ("bat_auto_remove_wobble",        "BOOLEAN"),
            ("haikubox_enabled",             "BOOLEAN"),
            ("bat_detection_device_name",    "VARCHAR"),
            ("notification_webhook_url",   "VARCHAR"),
            ("birdnet_min_confidence",     "REAL"),
            ("birdnet_overlap",            "REAL"),
            ("birdnet_sensitivity",        "REAL"),
            ("birdnet_lat",                "REAL"),
            ("birdnet_lon",                "REAL"),
            ("birdnet_week",               "INTEGER"),
            ("auth_enabled",               "BOOLEAN"),
            ("device_api_keys",            "JSON"),
            ("timezone",                   "VARCHAR"),
            ("dark_mode",                  "BOOLEAN"),
            ("min_confidence_display",     "REAL"),
            ("show_low_confidence",        "BOOLEAN"),
            # Location (for eBird queries and device geolocation)
            ("latitude",                   "REAL"),
            ("longitude",                  "REAL"),
            ("location_name",              "VARCHAR"),
            # Notification
            ("notifications_enabled",      "BOOLEAN"),
            ("notification_min_confidence","REAL"),
            ("ebird_api_key",              "VARCHAR"),
            ("updated_at",                 "DATETIME"),
            ("distance_unit",               "VARCHAR"),
            ("temperature_unit",            "VARCHAR"),
            ("auto_delete_recordings_days", "INTEGER"),
            # Independent auto-archive timer — see AppSettings model's
            # comment for the two-stage lifecycle this pairs with.
            ("auto_archive_recordings_days", "INTEGER"),
            ("auto_purge_min_confidence",   "REAL"),
            ("auto_purge_empty_recordings",  "BOOLEAN"),
            ("auto_purge_all_device",        "BOOLEAN"),
            ("notification_min_confidence",  "REAL"),
            ("storage_cleanup_keep_flagged", "BOOLEAN"),
            ("max_recordings_gb",           "REAL"),
            ("share_location_with_ebird",   "BOOLEAN"),
            ("share_detections_public",     "BOOLEAN"),
            ("range_map_sources",           "JSON"),
            ("range_map_source_order",      "JSON"),
            ("server_reanalyze_on_upload",     "BOOLEAN"),
            ("server_reanalyze_delete_device", "BOOLEAN"),
            ("show_deleted_detections",        "BOOLEAN"),
            ("range_maps_enabled",          "BOOLEAN"),
            ("observation_heatmap_enabled", "BOOLEAN"),
            # Explicit DEFAULT 1 (unlike the two flags just above, which
            # default OFF) — this one needs existing rows to come back
            # enabled too, matching the button's behavior before this
            # setting existed. An unqualified ALTER TABLE ADD COLUMN
            # would leave it NULL on the app's one existing settings
            # row, which the app treats as falsy — hiding a button
            # every admin already had on upgrade, not just new installs.
            ("allow_manual_reanalyze",      "BOOLEAN DEFAULT 1"),
            ("detection_color_palette",     "VARCHAR DEFAULT 'vivid'"),
            ("spectrograms_regenerated_for_color_fix", "BOOLEAN DEFAULT 0"),
            ("recording_min_gap_seconds",   "INTEGER"),
            ("recording_max_duration_sec",  "INTEGER"),
            ("recording_max_per_hour",      "INTEGER"),
            ("storage_compress_on_upload",  "BOOLEAN"),
            ("storage_compress_quality",    "VARCHAR"),
            ("storage_max_dir_gb",          "REAL"),
            ("storage_cleanup_keep_flagged","BOOLEAN"),
            ("smtp_host",                   "VARCHAR"),
            ("smtp_port",                   "INTEGER"),
            ("smtp_username",               "VARCHAR"),
            ("smtp_password",               "VARCHAR"),
            ("smtp_from_address",           "VARCHAR"),
            ("smtp_use_tls",                "BOOLEAN"),
            ("admin_email",                 "VARCHAR"),
            ("notify_on_register",          "BOOLEAN"),
            ("digest_hour",                 "INTEGER"),
            ("activity_log_enabled",        "BOOLEAN"),
            ("activity_log_track_ip",       "BOOLEAN"),
            ("activity_log_retention_days", "INTEGER"),
            ("tailscale_enabled",        "BOOLEAN DEFAULT 0"),
            ("tailscale_auth_key",       "VARCHAR"),
            ("tailscale_login_server",   "VARCHAR"),
            ("tailscale_hostname",       "VARCHAR"),
            ("ai_enhance_enabled",       "BOOLEAN"),
            ("ai_enhance_auto_apply",    "BOOLEAN"),
            ("ai_enhance_dry",           "REAL"),
            ("detection_model",          "VARCHAR DEFAULT 'birdnet3'"),
            ("exp_birdnet3_shadow",      "BOOLEAN DEFAULT 0"),
            ("exp_birdnet3_main",        "BOOLEAN DEFAULT 0"),
            ("exp_birdnet3_min_conf",    "REAL DEFAULT 0.5"),
            ("exp_nighthawk_enabled",    "BOOLEAN DEFAULT 0"),
            ("exp_nighthawk_start",      "VARCHAR DEFAULT '21:00'"),
            ("exp_nighthawk_end",        "VARCHAR DEFAULT '05:00'"),
            ("exp_nighthawk_threshold",  "INTEGER DEFAULT 80"),
            ("device_offline_minutes",   "INTEGER DEFAULT 15"),
            ("rumble_removal_mode",      "VARCHAR"),
            ("auto_backup_last_run_at",     "DATETIME"),
            ("auto_backup_last_success_at", "DATETIME"),
            ("auto_backup_last_error",      "VARCHAR"),
        ],
        "users": [
            ("display_name",         "VARCHAR"),
            ("inat_api_token",       "VARCHAR"),
            ("inat_token_set_at",    "DATETIME"),
            ("inat_last_refresh_error", "VARCHAR"),
            ("inat_username",        "VARCHAR"),
            ("inat_password",        "VARCHAR"),
            ("inat_oauth_client_id", "VARCHAR"),
            ("inat_oauth_client_secret", "VARCHAR"),
            ("pending_approval",     "BOOLEAN"),
            ("notify_new_bird",      "BOOLEAN"),
            ("notify_daily_digest",  "BOOLEAN"),
            ("notify_daily_digest_push", "BOOLEAN"),
            ("notify_new_bird_push", "BOOLEAN"),
            ("notify_device_offline_push", "BOOLEAN"),
            ("notify_device_offline_email", "BOOLEAN"),
            ("notify_daily_journal_push", "BOOLEAN"),
            ("notify_weekly_journal_push", "BOOLEAN"),
            ("dashboard_mode",       "VARCHAR"),
            ("last_seen_whats_new_version", "VARCHAR"),
            ("photo_url",            "VARCHAR"),
        ],
        "inbox_notifications": [
            ("data", "JSON"),
        ],
        "comments": [
            ("bird_profile_id", "VARCHAR"),
            ("recording_id",    "VARCHAR"),
            ("author",          "VARCHAR"),
            ("body",            "TEXT"),
            ("created_at",      "DATETIME"),
            ("updated_at",      "DATETIME"),
            ("deleted_at",      "DATETIME"),
        ],
        "devices": [
            ("offline_since",          "DATETIME"),
            ("hostname",               "VARCHAR"),
            ("ip_address",             "VARCHAR"),
            ("tailscale_ip",           "VARCHAR"),
            ("platform",               "VARCHAR"),
            ("os_version",             "VARCHAR"),
            ("coral_present",          "BOOLEAN"),
            ("bird_buddy_feeder_id",   "VARCHAR"),
            ("mic_count",              "INTEGER"),
            ("mic_names",              "JSON"),
            ("birdnet_backend",        "VARCHAR"),
            ("device_version",         "VARCHAR"),
            ("bat_status",             "JSON"),
            ("last_seen",              "DATETIME"),
            ("status",                 "VARCHAR"),
            ("managed_config",         "JSON"),
            ("config_version",         "INTEGER"),
            ("config_applied_version", "INTEGER"),
            ("ssh_username",           "VARCHAR"),
            ("ssh_password",           "VARCHAR"),
            ("created_at",             "DATETIME"),
            ("coral_form_factor",       "VARCHAR"),
            ("coral_model_present",     "BOOLEAN"),
            ("connect_via",             "VARCHAR"),
        ],
    }

    with engine.connect() as conn:
        for table, columns in pending.items():
            if not insp.has_table(table):
                continue
            existing = {col["name"] for col in insp.get_columns(table)}
            for col_name, col_type in columns:
                if col_name not in existing:
                    try:
                        conn.execute(text(
                            f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"
                        ))
                        conn.commit()
                        log.info("DB migration: added column %s.%s (%s)", table, col_name, col_type)
                    except Exception as e:
                        log.warning("DB migration skipped %s.%s: %s", table, col_name, e)

        # Strip HTML from any bird descriptions — must run inside the with block
        # so the connection is still open
        _clean_html_descriptions(conn, log)

        # Fix any column where the model says nullable=True but a pre-existing
        # SQLite table still enforces the old NOT NULL (SQLite can't alter
        # constraints on existing tables — only ALTER TABLE ADD COLUMN above
        # gets applied automatically). Checked generically across every
        # table/column, not just the one instance that was actually reported.
        _fix_stale_notnull_constraints(conn, log)

        _migrate_indexes(conn, insp, log)


def _migrate_indexes(conn, insp, log):
    """
    Adds indexes to existing columns that gained index=True in the ORM
    model after the table already existed. Base.metadata.create_all()
    only creates indexes for brand-new tables — it does not retroactively
    add an index to a column on a table that already exists, the same
    gap _migrate_columns() exists to cover for new columns. Idempotent
    and safe to call on every startup: checks the live index list first
    and skips anything already present.

    Map of (table, column) → index name for single-column indexes. Add
    an entry here any time an existing column gets index=True added to
    its model definition.
    """
    from sqlalchemy import text
    pending_indexes = {
        ("recordings", "device_id"): "ix_recordings_device_id",
        ("recordings", "archived_at"): "ix_recordings_archived_at",
        # Range-filtered (>=) and joined against Recording on every
        # non-"All confidence" selection on the Recordings page filter bar
        # — previously unindexed, meaning every confidence-filtered list
        # query did a full table scan across every Detection row.
        ("detections", "confidence"): "ix_detections_confidence",
        # Scanned in full by both purge_empty_recordings and
        # get_empty_recordings_count's "no_server_detections" subqueries
        # (Detection.source == "server") — previously unindexed, meaning
        # both of those ran a full table scan on every call.
        ("detections", "source"): "ix_detections_source",
    }
    for (table, column), index_name in pending_indexes.items():
        if not insp.has_table(table):
            continue
        try:
            existing_indexes = {ix["name"] for ix in insp.get_indexes(table)}
        except Exception as e:
            log.warning("DB migration: could not list indexes for %s: %s", table, e)
            continue
        if index_name in existing_indexes:
            continue
        try:
            conn.execute(text(f"CREATE INDEX {index_name} ON {table} ({column})"))
            conn.commit()
            log.info("DB migration: added index %s on %s.%s", index_name, table, column)
        except Exception as e:
            log.warning("DB migration skipped index %s: %s", index_name, e)

    # Composite (multi-column) indexes — map of table → list of
    # (index_name, [columns]). SQLite generally can't intersect two
    # separate single-column indexes as efficiently as it can use one
    # purpose-built composite index, so these target specific hot
    # combined filter/sort patterns rather than just any column that
    # happens to be queried.
    pending_composite_indexes = {
        "recordings": [
            # The single most common pattern across the statistics and
            # listing endpoints: "non-deleted recordings, ordered/filtered
            # by trigger_timestamp" — this exact combination appears in
            # full_statistics(), recording_stats(), and the main listing
            # endpoint, all independently filtering deleted_at IS NULL
            # then ordering or grouping by trigger_timestamp.
            ("ix_recordings_deleted_trigger", ["deleted_at", "trigger_timestamp"]),
            # Haikubox-exclusion subqueries (added across several recent
            # sessions to fix the Life List / Statistics page double-
            # counting bug) always filter haikubox_detection_id IS NULL
            # then join through to Detection.common_name — this composite
            # covers the Recording side of that join's filter.
            ("ix_recordings_haikubox_id_deleted", ["haikubox_detection_id", "deleted_at"]),
        ],
        "detections": [
            # Covers the detections side of every stats join (recording id,
            # the display-threshold filter, the species): Dashboard stats
            # 0.67 -> 0.51 s and dashboard-summary 0.78 -> 0.50 s on 60k
            # recordings / 200k detections.
            ("ix_detections_recording_conf_name", ["recording_id", "confidence", "common_name"]),
        ],
    }
    # Indexes that made queries slower. ix_detections_common_name_recording
    # (common_name, recording_id) let SQLite answer "common_name IN (...)"
    # filters by probing every listed species for every recording: the
    # Dashboard stats, Statistics, and Life List queries (which all filter
    # on the Haikubox-only species subquery) took 7-10 s each on 60k
    # recordings / 200k detections, 0.3-0.6 s without it.
    for table, index_name in (("detections", "ix_detections_common_name_recording"),):
        try:
            if insp.has_table(table) and index_name in {ix["name"] for ix in insp.get_indexes(table)}:
                conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
                conn.commit()
                log.info("DB migration: dropped index %s", index_name)
        except Exception as e:
            log.warning("DB migration: could not drop index %s: %s", index_name, e)

    for table, indexes in pending_composite_indexes.items():
        if not insp.has_table(table):
            continue
        try:
            existing_indexes = {ix["name"] for ix in insp.get_indexes(table)}
        except Exception as e:
            log.warning("DB migration: could not list indexes for %s: %s", table, e)
            continue
        for index_name, columns in indexes:
            if index_name in existing_indexes:
                continue
            try:
                cols_sql = ", ".join(columns)
                conn.execute(text(f"CREATE INDEX {index_name} ON {table} ({cols_sql})"))
                conn.commit()
                log.info("DB migration: added composite index %s on %s(%s)",
                        index_name, table, cols_sql)
            except Exception as e:
                log.warning("DB migration skipped composite index %s: %s", index_name, e)

    # Refresh the planner's statistics where they're stale (cheap; SQLite
    # only re-analyzes tables that changed enough).
    try:
        conn.execute(text("PRAGMA optimize"))
        conn.commit()
    except Exception as e:
        log.debug("PRAGMA optimize skipped: %s", e)


def _clean_html_descriptions(conn, log):
    """Strip HTML tags from bird profile descriptions stored before HTML cleaning was added."""
    import re
    import html as _html_mod
    from sqlalchemy import text
    try:
        rows = conn.execute(text(
            "SELECT id, description FROM bird_profiles WHERE description IS NOT NULL AND description LIKE '%<%'"
        )).fetchall()
        for row in rows:
            clean = re.sub(r"<[^>]+>", "", row[1])
            clean = _html_mod.unescape(clean)
            clean = re.sub(r"\s+", " ", clean).strip()
            conn.execute(text("UPDATE bird_profiles SET description=:d WHERE id=:i"),
                         {"d": clean, "i": row[0]})
            log.info("DB migration: stripped HTML from bird_profiles.description for %s", row[0])
        if rows:
            conn.commit()
    except Exception as e:
        log.debug("HTML strip migration skipped: %s", e)


def _fix_stale_notnull_constraints(conn, log):
    """
    SQLite doesn't support ALTER TABLE ... ALTER COLUMN, so a model change
    from nullable=False to nullable=True doesn't apply to databases where the
    table already existed under the old schema — _migrate_columns() above
    only adds missing columns, it can't relax an existing constraint.

    This was caught as a real, reported bug specifically for
    devices.api_key_id (virtual devices like Haikubox are created with
    api_key_id=None by design, which raised sqlite3.IntegrityError: NOT NULL
    constraint failed on any database whose devices table predates the
    nullable=True model change) — but the same bug class could exist for any
    column on any table that's ever had its nullability relaxed, so this
    checks every table/column the ORM knows about generically rather than
    special-casing just the one reported instance.

    For each mismatch found, rebuilds that one table — using the table's OWN
    actual live column list as the template (preserving every column byte-
    for-byte, including any that exist in the live database but aren't
    mirrored on the model class, e.g. devices.ssh_username), with only the
    specific stale constraint(s) relaxed. Idempotent and safe to run on
    every startup: tables with no mismatch are left completely untouched
    (just one cheap PRAGMA query each), no rebuild happens unless one is
    actually needed.
    """
    from sqlalchemy import text, inspect

    try:
        insp = inspect(conn)
        for table_name, table_obj in Base.metadata.tables.items():
            if not insp.has_table(table_name):
                continue  # fresh table — create_all() already used the correct schema

            live_cols = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
            # PRAGMA table_info columns: (cid, name, type, notnull, dflt_value, pk)
            live_notnull = {c[1]: bool(c[3]) for c in live_cols}

            stale = [
                col.name for col in table_obj.columns
                if col.nullable and live_notnull.get(col.name) is True
            ]
            if not stale:
                continue

            log.info(
                "DB migration: %s.%s %s NOT NULL on this database but the model "
                "says nullable — rebuilding table",
                table_name, ", ".join(stale), "is" if len(stale) == 1 else "are",
            )
            _rebuild_table_relaxing_notnull(conn, table_name, live_cols, stale, log)
    except Exception as e:
        log.warning("DB migration _fix_stale_notnull_constraints error: %s", e)


def _rebuild_table_relaxing_notnull(conn, table_name, live_cols, columns_to_relax, log):
    """
    Rebuild a single table, preserving its OWN actual live column list exactly
    (not the ORM model's), only dropping the NOT NULL constraint on the given
    column names. See _fix_stale_notnull_constraints() for why this matters.
    """
    from sqlalchemy import text

    col_names = [c[1] for c in live_cols]
    tmp_name = f"{table_name}_old_migration"

    col_defs = []
    for cid, name, ctype, notnull, dflt_value, pk in live_cols:
        parts = [name, ctype or "TEXT"]
        if pk:
            parts.append("PRIMARY KEY")
        if name in columns_to_relax:
            pass  # the targeted change: drop NOT NULL for these columns
        elif notnull:
            parts.append("NOT NULL")
        if dflt_value is not None:
            parts.append(f"DEFAULT {dflt_value}")
        col_defs.append(" ".join(parts))

    conn.execute(text(f"ALTER TABLE {table_name} RENAME TO {tmp_name}"))
    conn.execute(text(f"CREATE TABLE {table_name} ({', '.join(col_defs)})"))
    col_list = ", ".join(col_names)
    conn.execute(text(
        f"INSERT INTO {table_name} ({col_list}) SELECT {col_list} FROM {tmp_name}"
    ))
    conn.execute(text(f"DROP TABLE {tmp_name}"))
    conn.commit()

    count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
    log.info(
        "DB migration: %s rebuilt (%d row(s) preserved, all %d original columns retained)",
        table_name, count, len(col_names),
    )
