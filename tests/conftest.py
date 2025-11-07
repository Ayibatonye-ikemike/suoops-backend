from __future__ import annotations

import os
import warnings
from contextlib import contextmanager
from types import SimpleNamespace

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

# --- WhatsApp send patching ---
try:
    from app.bot.whatsapp_client import WhatsAppClient
except Exception:  # pragma: no cover - if module path changes
    WhatsAppClient = None  # type: ignore


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

# Suppress known third-party deprecation warnings (e.g., passlib crypt removal) to keep test output clean.
warnings.filterwarnings("ignore", category=DeprecationWarning, module="passlib.utils")


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


@pytest.fixture(autouse=True)
def _patch_whatsapp_send(monkeypatch):
    """Prevent real WhatsApp HTTP calls & noisy logs during tests.

    Replaces WhatsAppClient.send_text with a lightweight recorder that stores
    calls on the function object (for assertion if needed) without network activity.
    """
    if WhatsAppClient is None:  # pragma: no cover - safety
        return

    calls: list[tuple[str, str]] = []

    def fake_send_text(self, to: str, body: str):  # noqa: D401 - simple test double
        calls.append((to, body))

    monkeypatch.setattr(WhatsAppClient, "send_text", fake_send_text, raising=True)
    yield SimpleNamespace(calls=calls)


@pytest.fixture
def db_session():
    """Provide a transactional database session for tests."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    finally:
        session.close()


# FastAPI TestClient fixture expected by some tests (e.g., invoice verification)
from fastapi.testclient import TestClient  # noqa: E402
from app.api.main import app  # noqa: E402


@pytest.fixture
def client():  # noqa: D401 - simple factory fixture
    """Provide a FastAPI TestClient bound to the application."""
    return TestClient(app)
