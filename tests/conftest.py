import pytest

from app.db.session import SessionLocal
from app.models.models import WebhookEvent


@pytest.fixture(autouse=True)
def _reset_webhook_events():
    """Ensure webhook idempotency table doesn't leak state between tests."""
    session = SessionLocal()
    try:
        session.query(WebhookEvent).delete()
        session.commit()
        yield
        session.query(WebhookEvent).delete()
        session.commit()
    finally:
        session.close()
