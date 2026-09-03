"""
Database configuration and connection pooling
PostgreSQL with SQLAlchemy
"""

import logging
import os

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)

# Database URL — SINGLE SOURCE OF TRUTH. The request path (core.db.session) reads settings.DATABASE_URL
# (from .env), so this engine — used by init_db()/create_all and the schedulers — MUST resolve to the same
# database, or tables get created in a database nobody reads. Previously this defaulted to a separate
# `climate_platform` DB, which meant create_all silently provisioned tables the app never queried.
# Note: Uses postgresql+psycopg:// dialect for psycopg3 driver.
from core.config import settings  # noqa: E402

DATABASE_URL = os.getenv("DATABASE_URL", settings.DATABASE_URL)

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,  # Number of connections to keep in pool
    max_overflow=20,  # Maximum overflow connections
    pool_pre_ping=True,  # Test connections before using
    pool_recycle=3600,  # Recycle connections after 1 hour
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",  # Log SQL queries if SQL_ECHO=true
    future=True  # Use SQLAlchemy 2.0 style
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Set PostgreSQL connection parameters"""
    if not isinstance(dbapi_conn, type(None)):
        # PostgreSQL-specific settings can go here if needed
        pass


def get_db() -> Session:
    """
    Dependency for FastAPI endpoints.
    Usage: def my_endpoint(db: Session = Depends(get_db)): ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations() -> None:
    """Bring the database to head via the Alembic migration chain — the SINGLE source of truth for schema.

    This replaces the legacy ``create_all`` boot path. ``create_all`` only ever knew the subset of tables
    registered on the imported ORM ``Base.metadata`` (and none of the immutability triggers / functions /
    security columns that live only in migrations), so it produced a stale, partial schema. ``alembic upgrade
    head`` reproduces the FULL application schema on an empty database and is idempotent (a no-op once at head).
    """
    import sys
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))  # so alembic env.py can import `core.*`
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "core" / "db" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)  # target the same DB the request path reads
    command.upgrade(cfg, "head")
    logger.info("Database migrated to head (alembic)")


def init_db():
    """Initialize the database schema by migrating to head. Migrations are the source of truth (not create_all)."""
    run_migrations()


def check_db_connection() -> bool:
    """Check if database is accessible"""
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False
