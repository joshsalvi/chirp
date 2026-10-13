"""
Instance-aware database session resolution — the one piece this whole
multi-instance design rests on. See ARCHITECTURE.md.

Wired in via FastAPI's own `app.dependency_overrides` mechanism (see
main.py's own small, clearly-marked addition), NOT by editing
database.py's get_db() directly. That means:
  - database.py stays byte-identical to chirp-server's real file
    (confirmed with a real diff — see the comment in main.py)
  - every one of chirp-server's ~168 existing endpoints, which already
    declare `db: Session = Depends(get_db)`, gets silently redirected
    to get_instance_db below at runtime, without their own code
    referencing anything in this file, or knowing this file exists

Resolution is deliberately pure and stateless: decode the request's own
JWT, read the active_instance_id claim, look up (or open and cache) the
real SQLAlchemy engine for that instance. No database lookup of its own
— reading a claim already inside a token the request is carrying is a
fast, local operation, and avoids any circular dependency with
get_current_user (which itself depends on a database session).
"""
import os
import logging
import threading
import contextvars
from fastapi import Request, HTTPException
from starlette.requests import HTTPConnection
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger("chirp.instance_registry")

# Set by get_instance_db for the duration of one request (and, critically,
# any BackgroundTasks that request registers — see
# patch_session_local_for_instance_awareness()'s own docstring for why
# that specific detail matters). Holds the current request's resolved
# instance db_filename, or None outside any instance-scoped request.
_current_instance_db_filename: contextvars.ContextVar = contextvars.ContextVar(
    "current_instance_db_filename", default=None
)

INSTANCES_DIR = os.path.join(os.environ.get("CHIRP_DATA_DIR", "/app/data"), "instances")
os.makedirs(INSTANCES_DIR, exist_ok=True)

# Real engine cache, keyed by instance id — opening a SQLite connection
# is cheap but not free, and this is on the hot path for every single
# request once this is live, so each instance's engine (and its own
# sessionmaker) is created once and reused, not reopened per-request.
# A real lock guards the cache itself against a race where two
# concurrent requests for a not-yet-cached instance both try to create
# it at once — the SQLAlchemy engine creation itself is cheap enough
# that losing the race just means a wasted (immediately-discarded)
# engine object, not a correctness problem, but the lock avoids even
# that in the common case.
_engine_cache: dict = {}
_engine_cache_lock = threading.Lock()


def _instance_db_path(db_filename: str) -> str:
    return os.path.join(INSTANCES_DIR, db_filename)


def get_engine_for_instance(db_filename: str):
    """
    Returns a cached (or newly created and cached) SQLAlchemy engine for
    one instance's own real database file. Same real WAL/busy_timeout
    tuning as chirp-server's own single-instance engine (see
    database.py's own detailed comment on why) — every instance's
    database needs the exact same real concurrent-access behavior a
    single-instance deployment already relies on.
    """
    if db_filename in _engine_cache:
        return _engine_cache[db_filename]

    with _engine_cache_lock:
        if db_filename in _engine_cache:  # re-check: another thread may have won the race
            return _engine_cache[db_filename]

        db_path = _instance_db_path(db_filename)
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            echo=False,
        )

        @event.listens_for(engine, "connect")
        def _set_pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA cache_size=-64000")
            cur.execute("PRAGMA busy_timeout=15000")
            cur.close()

        _engine_cache[db_filename] = engine
        logger.info("Opened and cached engine for instance database: %s", db_filename)
        return engine


def patch_session_local_for_instance_awareness():
    """
    Investigated and fixed directly after tracing a real failed
    background job: process_recording_bg (and every other request-
    triggered background task in this codebase — auth.py, birds.py,
    live_detect.py, app_settings.py, bird_buddy_sync.py, ebird_service.py
    all do the identical thing) opens its own session with
    `from ..database import SessionLocal; db = SessionLocal()`, the
    ORIGINAL single-database factory — completely bypassing
    get_instance_db, since a background task has no Request object to
    resolve an instance from even if it wanted to. The observed symptom
    was a genuinely confusing one: the triggering upload itself
    succeeded (a real Recording row landed in the CORRECT instance
    database), but the background task that's supposed to run BirdNET
    on it immediately afterward silently failed with "no such table:
    recordings" — because it had opened a session against a different,
    unprovisioned database and never found the row it was looking for.
    A recording would sit in "processing" status forever with zero
    detections, no error visible anywhere a person would see.

    The fix stays true to this whole design's core rule (chirp-server's
    own code is never edited) by patching the database.SessionLocal
    NAME itself in-place, at the module level, once, at startup — not
    the file's source. Every one of those `from ..database import
    SessionLocal` call sites is a **call-time** import, confirmed by
    checking every occurrence in this codebase, none of them cache a
    reference at their own module's import time — so replacing the
    attribute here transparently reaches every one of them, forever,
    with no per-call-site changes.

    The replacement checks _current_instance_db_filename (set by
    get_instance_db for the duration of one request) and, when set,
    returns a session bound to THAT instance's engine instead of the
    legacy single database. This relies on one real, worth-stating-
    explicitly fact about how BackgroundTasks actually run: Starlette
    executes them after the response is sent but still within the same
    asyncio Task the request itself ran in (not a new one, and not a
    thread — confirmed directly for this codebase's async endpoints,
    e.g. upload_recording), and contextvars are Task-scoped, so a value
    set during the request is still correctly visible to a
    BackgroundTasks callable registered during that same request.
    Outside of any instance-scoped request (the scheduled jobs already
    using iter_instance_sessions() directly, or anything running before
    this patch is applied) the context var is unset and this transparently
    falls back to the exact original, unmodified behavior.
    """
    from . import database

    original_session_local = database.SessionLocal

    def _instance_aware_session_local(*args, **kwargs):
        db_filename = _current_instance_db_filename.get()
        if db_filename is None:
            return original_session_local(*args, **kwargs)
        engine = get_engine_for_instance(db_filename)
        InstanceSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        return InstanceSession(*args, **kwargs)

    database.SessionLocal = _instance_aware_session_local
    logger.info("Patched database.SessionLocal for instance-aware background tasks")


def provision_instance_database(db_filename: str):
    """
    Real, explicit provisioning for a brand-new instance — runs
    chirp-server's own real Base.metadata.create_all() (the same table
    definitions every existing model already declares, completely
    unmodified) against a fresh engine for this instance. Deliberately
    explicit, called once at instance-creation time (see api/instances.py),
    rather than lazily auto-creating tables the first time an instance is
    opened — a typo'd or since-deleted instance id should be a clear
    error, not a silently-created empty database.
    """
    from .database import Base
    from . import models  # noqa: F401 — ensures every model is registered on Base.metadata

    engine = get_engine_for_instance(db_filename)
    Base.metadata.create_all(bind=engine)

    # Cheap safety net, not the primary fix (that's the retroactive
    # fix-up in main.py's own startup for instances that already
    # existed): create_all() above already creates every column the
    # CURRENT model declares, so this is normally a no-op for a
    # brand-new instance. Only matters if the migration list in
    # database.py's _migrate_columns and the ORM model ever drift out
    # of sync with each other — cheap enough to run unconditionally
    # rather than rely on that never happening.
    from .database import _migrate_columns
    _migrate_columns(engine)

    # Seed AppSettings.auth_enabled=True immediately — reported directly:
    # a fresh instance's own AppSettings row doesn't exist yet at this
    # point, so until something else creates one, /auth/me's own
    # fallback logic (see auth.py's get_me) uses the GLOBAL
    # CHIRP_AUTH_ENABLED default instead, which chirp-server itself
    # defaults to false (a legitimate setting there — this multi-tenant
    # fork has no equivalent meaningful "auth disabled" mode, since
    # every request needs a JWT to resolve which instance's database to
    # even use). Left unseeded, a real logged-in user's own /auth/me
    # briefly reports auth_required: false, which is what was silently
    # hiding the sidebar's Sign Out button — confirmed directly by
    # reproducing the exact response before this fix, not assumed.
    from sqlalchemy.orm import sessionmaker
    from .models import AppSettings
    Session = sessionmaker(bind=engine)
    seed_db = Session()
    try:
        if not seed_db.query(AppSettings).filter(AppSettings.id == 1).first():
            seed_db.add(AppSettings(id=1, auth_enabled=True))
            seed_db.commit()
    finally:
        seed_db.close()

    logger.info("Provisioned new instance database: %s", db_filename)


def provision_instance_database_from_import(db_filename: str, source_db_path: str):
    """
    Provisions a new instance's database from an EXISTING, already-
    populated chirp-server (or another instance's) database file,
    rather than an empty schema — the counterpart to
    provision_instance_database() above, built for a real, requested
    feature: migrating an existing single-tenant chirp-server
    deployment's data into this multi-tenant fork as its own, separate
    location, instead of starting from zero and losing everything
    already recorded.

    source_db_path must already be validated (a real SQLite file with
    at least a recordings table) by the caller before this runs — this
    function's own job is only the provisioning side, not validation,
    matching the existing separation between /backup/restore's own
    validation step and this same instance_registry module's DB setup
    helpers.
    """
    import shutil as _shutil
    engine = get_engine_for_instance(db_filename)
    dest_path = _instance_db_path(db_filename)

    # get_engine_for_instance() above already opened (and cached) a
    # connection to dest_path the moment it was created — SQLite is
    # fine with copying over a file nothing has written through yet,
    # but the cached engine object itself must be dropped and rebuilt
    # after the copy, or every later use of this instance would keep
    # talking through a connection opened against the OLD (empty) file
    # rather than the one that now actually holds the imported data.
    engine.dispose()
    with _engine_cache_lock:
        _engine_cache.pop(db_filename, None)

    _shutil.copy2(source_db_path, dest_path)
    # A WAL-mode database can carry -wal/-shm sidecars alongside the
    # main file; if the SOURCE deployment had one of these sitting
    # around uncheckpointed, copying only the main file would silently
    # drop those pending writes. Copying it explicitly if present means
    # the import carries over exactly what the source had, not
    # whatever happened to already be checkpointed into the main file.
    for suffix in ("-wal", "-shm"):
        src_side = source_db_path + suffix
        if os.path.exists(src_side):
            _shutil.copy2(src_side, dest_path + suffix)

    # Fresh engine, now pointed at the real, copied-in data.
    engine = get_engine_for_instance(db_filename)

    from .database import _migrate_columns
    _migrate_columns(engine)

    # Unlike provision_instance_database()'s own "only if missing" seed
    # (a brand-new, empty database never has this row yet) — an
    # imported database almost certainly already HAS an AppSettings
    # row, carried over from the source deployment, and that source was
    # very likely a single-tenant chirp-server where auth_enabled can
    # legitimately be False. This fork has no equivalent "auth
    # disabled" mode (every request needs a JWT to resolve which
    # instance's database to even use — see provision_instance_database
    # above for the fuller version of this same reasoning), so this
    # needs to force auth_enabled=True on the imported row, not merely
    # add one if none exists.
    from sqlalchemy.orm import sessionmaker
    from .models import AppSettings
    Session = sessionmaker(bind=engine)
    seed_db = Session()
    try:
        existing = seed_db.query(AppSettings).filter(AppSettings.id == 1).first()
        if existing:
            existing.auth_enabled = True
        else:
            seed_db.add(AppSettings(id=1, auth_enabled=True))
        seed_db.commit()
    finally:
        seed_db.close()

    logger.info("Provisioned instance database %s from imported file %s", db_filename, source_db_path)


def iter_instance_sessions():
    """
    Real, shared helper for background/scheduled jobs — the one class of
    code get_instance_db's own per-request resolution can't help at all,
    since there's no request, no JWT, no "current user" for a timer-driven
    job to resolve an instance from (see ARCHITECTURE.md's own section on
    this). Yields (instance, session) for every real, currently-registered
    instance, so a background job's existing per-database logic can run
    unchanged, just once per instance instead of once globally.

    A real, previously-missing piece: auto-backup, Haikubox sync, Bird
    Buddy sync, and iNaturalist token refresh (see main.py's lifespan)
    all still operated on the single legacy database before this existed
    — meaning, notably, NO real instance's data was being automatically
    backed up at all, since auto_backup_enabled defaults to True (unlike
    the other three, which are genuinely opt-in and would have at least
    idled harmlessly with no configured credentials).

    Each session is properly closed after use regardless of whether the
    caller's own per-instance logic raised — one instance's failure
    (a locked database, a config error) must not prevent the loop from
    continuing to the next instance.
    """
    from .registry_db import RegistrySessionLocal
    from .registry_models import Instance
    from sqlalchemy.orm import sessionmaker

    reg_db = RegistrySessionLocal()
    try:
        instances = reg_db.query(Instance).all()
    finally:
        reg_db.close()

    for instance in instances:
        try:
            engine = get_engine_for_instance(instance.db_filename)
            SessionForInstance = sessionmaker(bind=engine)
            db = SessionForInstance()
        except Exception as e:
            logger.warning("iter_instance_sessions: could not open session for instance %s (%s): %s",
                            instance.id, instance.name, e)
            continue
        # Sets the same per-request context get_instance_db sets for a
        # real HTTP request — not just for SessionLocal() (see
        # patch_session_local_for_instance_awareness), but now also for
        # every module-level TTLCache (statistics_cache, life_list_cache,
        # etc. — see cache.py's own TTLCache._scoped_key). Without this,
        # a background job looping over every instance via this same
        # generator would read and write whichever instance's cache
        # entries happened to be there already, cross-contaminating
        # every location's dashboard/statistics with each other's data
        # — confirmed directly as the actual cause of a Dashboard
        # reverting to empty every 30 seconds on a real deployment.
        token = _current_instance_db_filename.set(instance.db_filename)
        try:
            yield instance, db
        finally:
            db.close()
            _current_instance_db_filename.reset(token)


def _resolve_token_state(request: Request) -> tuple:
    """
    Returns (has_valid_token, active_instance_id). Distinguishing these
    is real, not cosmetic: "no token at all" and "a real, valid token
    with no active_instance_id claim yet" are genuinely different
    situations that need different HTTP status codes for the frontend's
    existing auth logic (built around 401 meaning "not authenticated,
    show Login") to keep working correctly — a bug found via
    actual browser testing, not assumed: collapsing both into the same
    400 meant a completely unauthenticated visitor's own /me call also
    got a 400, which the frontend's 401-specific check never caught,
    so it fell through into rendering the app's own content instead of
    showing Login at all.

    Also checks a ?token= query parameter, not just the Authorization
    header — investigated and added directly after a real "Spectrogram
    unavailable" report traced to every spectrogram/audio/waveform
    request coming back 401. Root cause: those all render through a
    plain <img>/<audio> tag, and browsers have no mechanism to attach
    a custom header to that kind of request — there was no way for a
    real, logged-in browser to ever authenticate any of them, not a
    bug specific to one recording. A query-param token is the standard
    answer to exactly this limitation; it's checked only as a fallback,
    after the header, so a normal fetch()/XHR call with a real
    Authorization header is completely unaffected by this addition.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.query_params.get("token", "")
    if not token:
        return False, None
    try:
        from jose import jwt
        from .config import settings
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return True, payload.get("active_instance_id")
    except Exception:
        return False, None


def _find_instance_for_device_key(api_key: str):
    """
    Resolves which instance a device's own API key belongs to, by
    checking each instance's stored device_api_keys — the same lookup
    devices.py's own _validate_device_key already does, just tried
    across every instance instead of one already-known database.

    A real per-request cost (opens every instance's database once), not
    a free lookup — but device requests are infrequent relative to
    human traffic (one per captured recording, not one per page load),
    and the alternative — a separate registry-level index kept in sync
    with every device-key create/rotate/delete across every instance —
    is a second source of truth that could silently drift, for a save
    that only matters at a scale this project hasn't been shown to
    need yet (see ARCHITECTURE.md's own stated philosophy on exactly
    this kind of tradeoff, re: SQLite-per-instance vs. shared MariaDB).
    Revisit with real evidence (how many instances, how often devices
    actually hit this) if it ever becomes a measured problem.
    """
    from .registry_db import RegistrySessionLocal
    from .registry_models import Instance
    from sqlalchemy.orm import sessionmaker

    reg_db = RegistrySessionLocal()
    try:
        instances = reg_db.query(Instance).all()
    finally:
        reg_db.close()

    for instance in instances:
        try:
            engine = get_engine_for_instance(instance.db_filename)
            Session = sessionmaker(bind=engine)
            db = Session()
        except Exception as e:
            logger.warning("_find_instance_for_device_key: could not open instance %s (%s): %s", instance.id, instance.name, e)
            continue
        try:
            from .models import AppSettings
            s = db.query(AppSettings).filter(AppSettings.id == 1).first()
            keys = (s.device_api_keys or []) if s else []
            if any(k.get("key") == api_key for k in keys):
                return instance
        except Exception as e:
            logger.warning("_find_instance_for_device_key: lookup failed for instance %s (%s): %s", instance.id, instance.name, e)
        finally:
            db.close()
    return None


async def get_instance_db(request: HTTPConnection):
    # HTTPConnection, not Request: WebSocket routes (SSH terminal, mic
    # levels) resolve get_db through here too, and a Request parameter
    # fails their handshake with a 500. Browsers can't set headers on a
    # WebSocket, so those send ?token=.
    """
    The actual FastAPI dependency wired in as chirp-server's own get_db
    override (see main.py). Every existing endpoint's own
    `Depends(get_db)` resolves through here once the override is
    registered, completely transparently to that endpoint's own code —
    including device-facing endpoints (pair, recordings/upload, device
    heartbeat/config-pull), which is exactly the gap this function's
    device-key branch below closes.

    Investigated and fixed directly after tracing an actual failed
    device upload: a device never carries a JWT (it authenticates with
    its own long-lived API key, a completely separate scheme from human
    login), so the JWT-only version of this function rejected every
    single device request with 401 before device-facing endpoints ever
    got a chance to run their own, already-correct key validation.
    ARCHITECTURE.md's "one device to multiple instances... already real
    and working" turned out to be true only about schema compatibility
    (every instance has the same tables devices already expect) — it
    didn't account for this auth-routing layer sitting in front of
    every endpoint, device-facing ones included, and apparently nobody
    had tried a real device against this before now.

    Three real ways a device's key can arrive, all handled:
      - X-API-Key header — used by every device-facing endpoint EXCEPT
        pairing itself (heartbeat, config-pull, recordings/upload).
      - Authorization: Bearer <device-key> — an accepted fallback for
        the same header-based endpoints (see devices.py's own
        _device_key_from_header, which already treats these two the
        same way; this function has to match that, not invent a
        stricter rule chirp-server's own code doesn't enforce).
      - The JSON body's own "api_key" field — pairing specifically
        (POST .../devices/pair) sends its key this way, not as a
        header (confirmed directly in chirp-device's own
        server_sync.py and uploader.py). Peeking the body here is safe:
        Starlette caches the raw bytes the first time they're read, so
        the route handler's own Pydantic body-parsing afterward sees
        the exact same content, not a second, separate read.
    A JWT is still tried first — this only ever falls through to
    device-key resolution when there's no valid JWT to begin with, so a
    logged-in human's own request is never affected by any of this.
    """
    has_token, instance_id = _resolve_token_state(request)
    if has_token:
        if not instance_id:
            raise HTTPException(
                status_code=400,
                detail="No active instance selected. Choose one via POST /api/v1/instances/switch, or create/join one first.",
            )
        instance = _get_instance_by_id(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Your active instance no longer exists.")
    else:
        device_key = request.headers.get("X-API-Key")
        if not device_key:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                device_key = auth_header[7:]
        if not device_key and isinstance(request, Request) and request.url.path.endswith("/pair"):
            try:
                body = await request.json()
                device_key = body.get("api_key") if isinstance(body, dict) else None
            except Exception:
                device_key = None

        instance = _find_instance_for_device_key(device_key) if device_key else None
        if not instance:
            raise HTTPException(status_code=401, detail="Not authenticated.")

    engine = get_engine_for_instance(instance.db_filename)
    SessionForInstance = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionForInstance()
    token = _current_instance_db_filename.set(instance.db_filename)
    try:
        yield db
    finally:
        db.close()
        _current_instance_db_filename.reset(token)


def _get_instance_by_id(instance_id: str):
    from .registry_db import RegistrySessionLocal
    from .registry_models import Instance

    reg_db = RegistrySessionLocal()
    try:
        return reg_db.query(Instance).filter(Instance.id == instance_id).first()
    finally:
        reg_db.close()
