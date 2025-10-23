from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db import session as db_session
from app.db.base_class import Base
from app.db.session import SessionLocal

try:
    from app.models.models import WebhookEvent
except ImportError:  # pragma: no cover - legacy tables may be removed
    WebhookEvent = None


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")


test_engine = create_engine(
    TEST_DATABASE_URL,
    future=True,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Ensure application code uses the test engine
settings.DATABASE_URL = TEST_DATABASE_URL  # type: ignore[attr-defined]
settings.ENV = "test"  # type: ignore[attr-defined]
db_session.engine = test_engine  # type: ignore[assignment]
SessionLocal.configure(bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def _setup_database_schema():
    """Create all tables once for the test session and drop afterwards."""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(autouse=True)
def _reset_database_state():
    """Ensure each test sees a fresh database schema."""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield


@pytest.fixture(autouse=True)
def _reset_webhook_events():
    """Ensure webhook idempotency table doesn't leak state between tests."""
    session = SessionLocal()
    try:
        if WebhookEvent is not None:
            session.query(WebhookEvent).delete()
            session.commit()
        yield
        if WebhookEvent is not None:
            session.query(WebhookEvent).delete()
            session.commit()
    finally:
        session.close()


@pytest.fixture
def db_session():
    """Provide a transactional database session for tests."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    finally:
        session.close()
