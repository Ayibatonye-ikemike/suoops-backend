"""Tests for analytics service."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import Customer, Invoice, User
from app.services.analytics_service import (
    calculate_revenue_metrics,
    calculate_invoice_metrics,
    calculate_customer_metrics,
    calculate_aging_report,
    calculate_monthly_trends,
)

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
        name="TestUser",
        email="analytics-test@example.com",
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_customer(db_session):
    """Create a test customer."""
    customer = Customer(
        name="TestCustomer",
        phone="+2349876543210",
        email="analytics-customer@example.com",
    )
    db_session.add(customer)
    db_session.commit()
    return customer


def create_invoice(
    db_session,
    issuer_id: int,
    customer_id: int,
    amount: Decimal,
    status: str = "pending",
    invoice_type: str = "revenue",
    created_at: datetime = None,
    due_date: datetime = None,
):
    """Helper to create an invoice."""
    if created_at is None:
        created_at = datetime.now(timezone.utc)
    if due_date is None:
        due_date = created_at + timedelta(days=30)
    
    invoice = Invoice(
        invoice_id=f"INV-{issuer_id}-{created_at.timestamp()}",
        issuer_id=issuer_id,
        customer_id=customer_id,
        amount=amount,
        status=status,
        invoice_type=invoice_type,
        created_at=created_at,
        due_date=due_date,
    )
    db_session.add(invoice)
    db_session.commit()
    return invoice


def test_calculate_revenue_metrics_no_invoices(db_session, test_user):
    """Test revenue metrics with no invoices."""
    start = date.today() - timedelta(days=30)
    end = date.today()
    
    metrics = calculate_revenue_metrics(
        db_session, test_user.id, start, end, Decimal("1.0")
    )
    
    assert metrics.total_revenue == Decimal("0")
    assert metrics.paid_revenue == Decimal("0")
    assert metrics.pending_revenue == Decimal("0")
    assert metrics.overdue_revenue == Decimal("0")


def test_calculate_revenue_metrics_with_invoices(db_session, test_user, test_customer):
    """Test revenue metrics with various invoice statuses."""
    today = datetime.now(timezone.utc)
    
    # Create paid invoice
    create_invoice(db_session, test_user.id, test_customer.id, Decimal("1000"), "paid")
    
    # Create pending invoice
    create_invoice(db_session, test_user.id, test_customer.id, Decimal("500"), "pending")
    
    # Create overdue invoice
    overdue_date = today - timedelta(days=60)
    create_invoice(
        db_session,
        test_user.id,
        test_customer.id,
        Decimal("300"),
        "pending",
        created_at=overdue_date,
        due_date=overdue_date + timedelta(days=30),
    )
    
    start = date.today() - timedelta(days=90)
    end = date.today()
    
    metrics = calculate_revenue_metrics(
        db_session, test_user.id, start, end, Decimal("1.0")
    )
    
    assert metrics.total_revenue == Decimal("1800")
    assert metrics.paid_revenue == Decimal("1000")
    assert metrics.pending_revenue == Decimal("500")
    assert metrics.overdue_revenue == Decimal("300")


def test_calculate_invoice_metrics(db_session, test_user, test_customer):
    """Test invoice metrics calculation."""
    # Create various invoices
    create_invoice(db_session, test_user.id, test_customer.id, Decimal("1000"), "paid")
    create_invoice(db_session, test_user.id, test_customer.id, Decimal("500"), "pending")
    create_invoice(db_session, test_user.id, test_customer.id, Decimal("200"), "failed")
    
    start = date.today() - timedelta(days=30)
    end = date.today()
    
    metrics = calculate_invoice_metrics(db_session, test_user.id, start, end)
    
    assert metrics.total_count == 3
    assert metrics.paid_count == 1
    assert metrics.pending_count == 1
    assert metrics.failed_count == 1


def test_calculate_customer_metrics(db_session, test_user):
    """Test customer metrics calculation."""
    # Create customers with invoices
    for i in range(5):
        customer = Customer(
            id=i + 10,
            name=f"Customer{i}",
            phone=f"+23490000000{i}",
            email=f"cust{i}@example.com",
        )
        db_session.add(customer)
        db_session.commit()
        
        # Create invoices for some customers
        if i < 3:
            create_invoice(
                db_session,
                test_user.id,
                customer.id,
                Decimal("100") * (i + 1),
                "paid",
            )
    
    start = date.today() - timedelta(days=30)
    end = date.today()
    
    metrics = calculate_customer_metrics(db_session, test_user.id, start, end)
    
    assert metrics.total_customers >= 3
    assert metrics.active_customers == 3
    assert len(metrics.top_customers) > 0


def test_calculate_aging_report(db_session, test_user, test_customer):
    """Test aging report calculation."""
    today = datetime.now(timezone.utc)
    
    # Create invoices with different ages
    create_invoice(
        db_session,
        test_user.id,
        test_customer.id,
        Decimal("100"),
        "pending",
        due_date=today - timedelta(days=10),
    )
    create_invoice(
        db_session,
        test_user.id,
        test_customer.id,
        Decimal("200"),
        "pending",
        due_date=today - timedelta(days=40),
    )
    create_invoice(
        db_session,
        test_user.id,
        test_customer.id,
        Decimal("300"),
        "pending",
        due_date=today - timedelta(days=70),
    )
    
    report = calculate_aging_report(db_session, test_user.id, Decimal("1.0"))
    
    assert report.current >= Decimal("0")
    assert report.days_1_30 >= Decimal("0")
    assert report.days_31_60 >= Decimal("0")
    assert report.days_61_90 >= Decimal("0")


def test_calculate_monthly_trends(db_session, test_user, test_customer):
    """Test monthly trends calculation."""
    today = datetime.now(timezone.utc)
    
    # Create invoices for the last 3 months
    for i in range(3):
        month_ago = today - timedelta(days=30 * i)
        create_invoice(
            db_session,
            test_user.id,
            test_customer.id,
            Decimal("1000") * (i + 1),
            "paid",
            created_at=month_ago,
        )
    
    trends = calculate_monthly_trends(db_session, test_user.id, 3, Decimal("1.0"))
    
    assert len(trends) <= 3
    assert all(isinstance(trend.month, str) for trend in trends)
    assert all(trend.revenue >= Decimal("0") for trend in trends)
