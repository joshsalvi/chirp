"""
Registry database — the ONE thing that lives outside every per-instance
database. Tracks which instances exist, the real global login identity
a person authenticates with, and which instances they belong to.

Deliberately its own separate SQLite file and its own separate engine/
session, not reusing chirp-server's existing database.py machinery —
that module's engine is meant to point at exactly one instance's data
at a time (and becomes request-dynamic once get_db() is modified below
it), while this one is the same for every request, always. Keeping them
structurally separate makes it impossible to accidentally query
instance-scoped data through the registry's session or vice versa.
"""
import os
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

logger = logging.getLogger("chirp.registry")

REGISTRY_DB_PATH = os.environ.get(
    "CHIRP_REGISTRY_DB_PATH",
    os.path.join(os.environ.get("CHIRP_DATA_DIR", "/app/data"), "instances", "_registry.db"),
)


def _ensure_registry_dir():
    os.makedirs(os.path.dirname(REGISTRY_DB_PATH), exist_ok=True)


_ensure_registry_dir()

registry_engine = create_engine(
    f"sqlite:///{REGISTRY_DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)


@event.listens_for(registry_engine, "connect")
def _set_registry_pragmas(dbapi_conn, _):
    # Same real WAL/busy_timeout tuning as the per-instance databases
    # (see database.py's own detailed comment on why) — the registry is
    # hit on every single request (to resolve the active instance), so
    # it needs the same real concurrent-read behavior, not just the
    # per-instance databases.
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA busy_timeout=15000")
    cur.close()


RegistrySessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=registry_engine)


class RegistryBase(DeclarativeBase):
    pass


def get_registry_db():
    """FastAPI dependency: yields a registry database session."""
    db = RegistrySessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_registry_db():
    """Create the registry's own tables. Safe to call repeatedly."""
    from . import registry_models  # noqa: F401 — ensures models are registered
    RegistryBase.metadata.create_all(bind=registry_engine)
    _migrate_registry_columns()
    logger.info("Registry database initialized at %s", REGISTRY_DB_PATH)


def _migrate_registry_columns():
    """
    Same lightweight column migration as database.py's own
    _migrate_columns() — but that one only ever runs against the
    per-instance database's engine, never this registry one, so a
    column added to a registry model (is_global_admin, first one to
    need this) would otherwise never actually reach an already-existing
    registry.db on upgrade. create_all() above only creates missing
    TABLES, not missing columns on tables that already exist.
    """
    from sqlalchemy import text, inspect

    insp = inspect(registry_engine)
    pending = {
        "global_users": [
            ("is_global_admin", "BOOLEAN DEFAULT 0"),
        ],
        "registry_settings": [
            ("headscale_basic_auth_enabled", "BOOLEAN DEFAULT 0"),
            ("headscale_basic_auth_username", "VARCHAR"),
            ("headscale_basic_auth_password_hash", "VARCHAR"),
        ],
    }
    with registry_engine.connect() as conn:
        for table, columns in pending.items():
            if not insp.has_table(table):
                continue
            existing = {col["name"] for col in insp.get_columns(table)}
            for col_name, col_type in columns:
                if col_name not in existing:
                    try:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                        logger.info("Registry DB migration: added column %s.%s (%s)", table, col_name, col_type)
                    except Exception as e:
                        logger.warning("Registry DB migration skipped %s.%s: %s", table, col_name, e)
