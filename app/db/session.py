"""Database engine setup.

For test runs (ENV=test) we intentionally fallback to synchronous in-memory SQLite
when DATABASE_URL is unset or explicitly requested via SUOOPS_TEST_SQLITE=1.
This avoids needing a PostgreSQL driver (psycopg2/pg_config) for logic tests.
"""

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

raw_url = settings.DATABASE_URL

use_sqlite_memory = (
    settings.ENV.lower() == "test" and (
        os.getenv("SUOOPS_TEST_SQLITE") == "1" or not raw_url or raw_url.startswith("sqlite+aiosqlite:///:memory:")
    )
)

if use_sqlite_memory:
    # Use a transient in-memory database; persistence not required for unit tests.
    raw_url = "sqlite:///file:test_db?mode=memory&cache=shared"  # shared cache enables multiple connections
    engine = create_engine(raw_url, future=True)
else:
    # If URL is PostgreSQL but driver not installed (tests), gracefully downgrade to file-based sqlite
    if raw_url and raw_url.startswith("postgresql"):
        try:
            # Configure connection pool for production PostgreSQL
            # Pool size: base connections kept open
            # Max overflow: additional connections that can be created on demand
            # Pool recycle: recycle connections after 1 hour to prevent stale connections
            # Pool pre-ping: verify connection health before using
            engine = create_engine(
                raw_url,
                future=True,
                pool_size=5,  # Base pool size (Heroku Standard-0: 20 connections max, shared with workers)
                max_overflow=10,  # Allow up to 15 total connections (5 + 10)
                pool_recycle=3600,  # Recycle connections after 1 hour
                pool_pre_ping=True,  # Verify connection health before use
            )
        except ModuleNotFoundError:
            fallback_url = "sqlite:///./storage/test_fallback.db"
            engine = create_engine(fallback_url, future=True)
    else:
        engine = create_engine(raw_url, future=True)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
