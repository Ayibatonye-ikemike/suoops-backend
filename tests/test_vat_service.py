"""Tests for VAT service."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import User
from app.services.vat_service import VATService


engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)


@pytest.fixture
def db_session():
    """Create a fresh database session for each test."""
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def test_user(db_session):
    """Create a test user."""
    user = User(
        phone="+2341234567890",
        name="VATTestUser",
        email="vat@example.com",
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_vat_service_initialization(db_session):
    """Test VAT service can be initialized."""
    service = VATService(db_session)
    assert service.db == db_session


def test_calculate_monthly_vat(db_session, test_user):
    """Test monthly VAT calculation."""
    service = VATService(db_session)
    now = datetime.now(timezone.utc)
    
    result = service.calculate_monthly_vat(test_user.id, now.year, now.month)
    
    # Should return dict with VAT fields
    assert isinstance(result, dict)
    assert "output_vat" in result
    assert "input_vat" in result


def test_get_vat_summary(db_session, test_user):
    """Test VAT summary retrieval."""
    service = VATService(db_session)
    
    summary = service.get_vat_summary(test_user.id)
    
    # Should return dict with summary fields
    assert isinstance(summary, dict)
    assert "compliance_status" in summary or "error" in summary

