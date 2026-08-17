"""
Database configuration and connection pooling
PostgreSQL with SQLAlchemy
"""

import os
from sqlalchemy import create_engine, event, Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
import logging

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


def init_db():
    """Initialize database (create any missing tables — checkfirst, never alters existing ones)."""
    from core.db.models import Base
    # Import the full model modules so EVERY table is registered on Base.metadata before create_all —
    # otherwise a model defined in a not-yet-imported module is silently skipped.
    import core.db.models_regulatory_complete  # noqa: F401
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized")


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
