"""Unit tests for assessable profit and levy endpoint logic (service-level)."""
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from app.services.tax_service import TaxProfileService
from app.models.models import Invoice, User, Customer
from app.db.base_class import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# NOTE: These tests use SQLAlchemy; ensure 'sqlalchemy' is in requirements for local runs.
# In-memory SQLite (simplified) – if models have vendor-specific types, adjust accordingly.
engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)


def make_user(session, user_id: int = 1):
    u = User(id=user_id, phone="+234000000000", name="Test", email="test@example.com")
    session.add(u)
    session.flush()
    # Also create a minimal customer record so FK constraint for invoices passes
    c = Customer(id=user_id, name="Cust", phone="+234000000001", email="cust@example.com")
    session.add(c)
    session.commit()
    return u


def make_invoice(session, issuer_id: int, amount: float, status: str = "paid", discount: float | None = None, days_offset: int = -1):
    inv = Invoice(
        invoice_id=f"INV-{issuer_id}-{amount}-{status}-{days_offset}",
        issuer_id=issuer_id,
        customer_id=issuer_id,  # using same ID for simplicity
        amount=Decimal(str(amount)),
        discount_amount=Decimal(str(discount)) if discount else None,
        status=status,
        due_date=datetime.now(timezone.utc) + timedelta(days=days_offset),
        created_at=datetime.now(timezone.utc) + timedelta(days=days_offset),
    )
    session.add(inv)
    session.commit()
    return inv


def test_assessable_profit_paid_basis_excludes_future_and_discount():
    session = SessionLocal()
    make_user(session, 1)
    service = TaxProfileService(session)
    # Paid invoice past due
    make_invoice(session, 1, 10000, status="paid", discount=1000, days_offset=-10)
    # Paid invoice future due (should be excluded)
    make_invoice(session, 1, 5000, status="paid", discount=None, days_offset=5)
    # Pending invoice past due (excluded for paid basis)
    make_invoice(session, 1, 8000, status="pending", days_offset=-3)
    profit = service.compute_assessable_profit(1, basis="paid")
    # Only first invoice counts: 10000 - 1000 = 9000
    assert profit == Decimal("9000")


def test_assessable_profit_all_basis_includes_pending_not_future():
    session = SessionLocal()
    make_user(session, 2)
    service = TaxProfileService(session)
    make_invoice(session, 2, 10000, status="paid", discount=2000, days_offset=-2)
    make_invoice(session, 2, 6000, status="pending", discount=None, days_offset=-1)
    make_invoice(session, 2, 4000, status="paid", discount=None, days_offset=10)  # future due excluded
    profit = service.compute_assessable_profit(2, basis="all")
    # (10000-2000) + 6000 = 14000
    assert profit == Decimal("14000")


def test_development_levy_medium_business_calculation():
    session = SessionLocal()
    make_user(session, 3)
    service = TaxProfileService(session)
    # Force medium classification
    service.update_profile(3, annual_turnover=Decimal("150000000"), fixed_assets=Decimal("300000000"))
    make_invoice(session, 3, 200000, status="paid", discount=20000, days_offset=-1)
    profit = service.compute_assessable_profit(3, basis="paid")
    levy = service.compute_development_levy(3, profit)
    # Profit = 180000; levy 4% = 7200
    assert levy["levy_amount"] == 7200.0

def test_assessable_profit_month_filter():
    session = SessionLocal()
    make_user(session, 4)
    service = TaxProfileService(session)
    # Two invoices different months
    # January (past due)
    make_invoice(session, 4, 5000, status="paid", discount=500, days_offset=-280)  # approx months back
    # February (past due) - will target this month
    make_invoice(session, 4, 7000, status="paid", discount=0, days_offset=-250)
    now = datetime.now(timezone.utc)
    target_year = now.year if now.month > 2 else now.year - 1
    target_month = 2
    profit = service.compute_assessable_profit(4, year=target_year, month=target_month, basis="paid")
    # Only February invoice considered: 7000
    assert profit == Decimal("7000")

def test_assessable_profit_discount_subtraction():
    session = SessionLocal()
    make_user(session, 5)
    service = TaxProfileService(session)
    make_invoice(session, 5, 10000, status="paid", discount=1234, days_offset=-1)
    profit = service.compute_assessable_profit(5, basis="paid")
    assert profit == Decimal("8766")

def test_assessable_profit_basis_toggle_difference():
    session = SessionLocal()
    make_user(session, 6)
    service = TaxProfileService(session)
    make_invoice(session, 6, 4000, status="paid", discount=None, days_offset=-2)
    make_invoice(session, 6, 3000, status="pending", discount=None, days_offset=-2)
    paid_profit = service.compute_assessable_profit(6, basis="paid")
    all_profit = service.compute_assessable_profit(6, basis="all")
    assert paid_profit == Decimal("4000")
    assert all_profit == Decimal("7000")
    session = SessionLocal()
    make_user(session, 3)
    service = TaxProfileService(session)
    # Force medium classification
    service.update_profile(3, annual_turnover=Decimal("150000000"), fixed_assets=Decimal("300000000"))
    make_invoice(session, 3, 200000, status="paid", discount=20000, days_offset=-1)
    profit = service.compute_assessable_profit(3, basis="paid")
    levy = service.compute_development_levy(3, profit)
    # Profit = 180000; levy 4% = 7200
    assert levy["levy_amount"] == 7200.0

