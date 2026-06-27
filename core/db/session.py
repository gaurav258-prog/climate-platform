from contextlib import contextmanager
from functools import lru_cache
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from core.config import settings


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker:
    """
    Build the engine + session factory on first use, not at import.

    Eager engine creation made every module that touches the DB un-importable
    without a live driver/URL — which broke offline unit tests of pure functions.
    Deferring it means importing a module no longer requires a database; only
    actually calling get_session() does.
    """
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = _session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def set_rls_context(session: Session, customer_id: str) -> None:
    """Set Row Level Security context for the session."""
    session.execute(text(f"SET app.customer_id = '{customer_id}'"))


def __getattr__(name: str):
    # Backward-compatible lazy access for the old module globals, in case any
    # external script references them. They are built on first access, not import.
    if name == "SessionLocal":
        return _session_factory()
    if name == "engine":
        return _session_factory().kw["bind"]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
