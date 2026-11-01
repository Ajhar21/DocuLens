"""Sync SQLAlchemy 2.0 engine and session factory (psycopg3 driver).

Provides two entry points:
- ``get_db()``         — FastAPI ``Depends()`` generator for HTTP routes.
- ``get_db_session()`` — context manager for scripts and the worker process.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.sqlalchemy_database_url,
    pool_pre_ping=True,       # Detect and recycle stale Supabase connections
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,   # Prevent lazy-load surprises after commit
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and closes it on teardown."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager for scripts and the worker process."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def check_db_health() -> bool:
    """Verify database connectivity.

    Used by health checks to avoid embedding raw SQL in HTTP routers.
    """
    from sqlalchemy import text

    try:
        with get_db_session() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


