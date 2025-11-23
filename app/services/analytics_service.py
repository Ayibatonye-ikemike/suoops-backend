"""Analytics calculation service for business metrics."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.models import models
from app.models.schemas import (
    RevenueMetrics,
    InvoiceMetrics,
    CustomerMetrics,
    AgingReport,
    MonthlyTrend,
)


def calculate_revenue_metrics(
    db: Session,
    user_id: int,
    start_date: date,
    end_date: date,
    conversion_rate: Decimal,
) -> RevenueMetrics:
    """Calculate total revenue, paid, pending, and overdue amounts."""
    
    # Get all revenue invoices in period
    invoices = (
        db.query(models.Invoice)
        .filter(
            models.Invoice.issuer_id == user_id,
            models.Invoice.invoice_type == "revenue",
            models.Invoice.created_at >= datetime.combine(start_date, datetime.min.time()),
            models.Invoice.created_at <= datetime.combine(end_date, datetime.max.time()),
        )
        .all()
    )
    
    total_revenue = Decimal("0")
    paid_revenue = Decimal("0")
    pending_revenue = Decimal("0")
    overdue_revenue = Decimal("0")
    
    for inv in invoices:
        amount = inv.amount / conversion_rate
        total_revenue += amount
        
        if inv.status == "paid":
            paid_revenue += amount
        elif inv.status == "pending":
            if inv.due_date and inv.due_date.date() < end_date:
                overdue_revenue += amount
            else:
                pending_revenue += amount
        elif inv.status == "awaiting_confirmation":
            pending_revenue += amount
    
    # Calculate previous period for growth
    period_days = (end_date - start_date).days
    prev_start = start_date - timedelta(days=period_days)
    
    prev_revenue = (
        db.query(func.sum(models.Invoice.amount))
        .filter(
            models.Invoice.issuer_id == user_id,
            models.Invoice.invoice_type == "revenue",
            models.Invoice.status == "paid",
            models.Invoice.created_at >= datetime.combine(prev_start, datetime.min.time()),
            models.Invoice.created_at < datetime.combine(start_date, datetime.min.time()),
        )
        .scalar()
    ) or Decimal("0")
    
    prev_revenue = prev_revenue / conversion_rate
    
    # Calculate growth percentage
    if prev_revenue > 0:
        growth_rate = float(((paid_revenue - prev_revenue) / prev_revenue) * 100)
    else:
        growth_rate = 100.0 if paid_revenue > 0 else 0.0
    
    return RevenueMetrics(
        total_revenue=float(total_revenue),
        paid_revenue=float(paid_revenue),
        pending_revenue=float(pending_revenue),
        overdue_revenue=float(overdue_revenue),
        growth_rate=growth_rate,
        average_invoice_value=float(total_revenue / len(invoices)) if invoices else 0.0,
    )


def calculate_invoice_metrics(
    db: Session,
    user_id: int,
    start_date: date,
    end_date: date,
) -> InvoiceMetrics:
    """Calculate invoice counts by status."""
    
    invoices = (
        db.query(
            func.count(models.Invoice.id).label("total"),
            func.sum(case((models.Invoice.status == "paid", 1), else_=0)).label("paid"),
            func.sum(case((models.Invoice.status == "pending", 1), else_=0)).label("pending"),
            func.sum(case((models.Invoice.status == "awaiting_confirmation", 1), else_=0)).label("awaiting"),
            func.sum(case((models.Invoice.status == "failed", 1), else_=0)).label("failed"),
        )
        .filter(
            models.Invoice.issuer_id == user_id,
            models.Invoice.invoice_type == "revenue",
            models.Invoice.created_at >= datetime.combine(start_date, datetime.min.time()),
            models.Invoice.created_at <= datetime.combine(end_date, datetime.max.time()),
        )
        .first()
    )
    
    total = invoices.total or 0
    paid = invoices.paid or 0
    pending = invoices.pending or 0
    awaiting = invoices.awaiting or 0
    failed = invoices.failed or 0
    
    # Calculate conversion rate (paid / total)
    conversion_rate = (paid / total * 100) if total > 0 else 0.0
    
    return InvoiceMetrics(
        total_invoices=total,
        paid_invoices=paid,
        pending_invoices=pending,
        awaiting_confirmation=awaiting,
        failed_invoices=failed,
        conversion_rate=conversion_rate,
    )


def calculate_customer_metrics(
    db: Session,
    user_id: int,
    start_date: date,
    end_date: date,
) -> CustomerMetrics:
    """Calculate customer counts and repeat customer rate."""
    
    # Get unique customers in period
    customers_in_period = (
        db.query(func.count(func.distinct(models.Invoice.customer_id)))
        .filter(
            models.Invoice.issuer_id == user_id,
            models.Invoice.invoice_type == "revenue",
            models.Invoice.created_at >= datetime.combine(start_date, datetime.min.time()),
            models.Invoice.created_at <= datetime.combine(end_date, datetime.max.time()),
        )
        .scalar()
    ) or 0
    
    # Get total unique customers ever
    total_customers = (
        db.query(func.count(func.distinct(models.Invoice.customer_id)))
        .filter(
            models.Invoice.issuer_id == user_id,
            models.Invoice.invoice_type == "revenue",
        )
        .scalar()
    ) or 0
    
    # Get customers with multiple invoices (repeat customers)
    repeat_customers = (
        db.query(models.Invoice.customer_id)
        .filter(
            models.Invoice.issuer_id == user_id,
            models.Invoice.invoice_type == "revenue",
            models.Invoice.created_at >= datetime.combine(start_date, datetime.min.time()),
            models.Invoice.created_at <= datetime.combine(end_date, datetime.max.time()),
        )
        .group_by(models.Invoice.customer_id)
        .having(func.count(models.Invoice.id) > 1)
    ).count()
    
    # Calculate repeat rate
    repeat_rate = (repeat_customers / customers_in_period * 100) if customers_in_period > 0 else 0.0
    
    return CustomerMetrics(
        total_customers=total_customers,
        active_customers=customers_in_period,
        new_customers=customers_in_period,  # Simplified - in production, filter by first invoice date
        repeat_customer_rate=repeat_rate,
    )


def calculate_aging_report(
    db: Session,
    user_id: int,
    reference_date: date,
    conversion_rate: Decimal,
) -> AgingReport:
    """Calculate accounts receivable aging buckets."""
    
    # Get all unpaid invoices
    unpaid_invoices = (
        db.query(models.Invoice)
        .filter(
            models.Invoice.issuer_id == user_id,
            models.Invoice.invoice_type == "revenue",
            models.Invoice.status.in_(["pending", "awaiting_confirmation"]),
        )
        .all()
    )
    
    current = Decimal("0")  # 0-30 days
    days_31_60 = Decimal("0")
    days_61_90 = Decimal("0")
    over_90 = Decimal("0")
    
    for inv in unpaid_invoices:
        if not inv.due_date:
            current += inv.amount
            continue
        
        days_overdue = (reference_date - inv.due_date.date()).days
        amount = inv.amount / conversion_rate
        
        if days_overdue < 0 or days_overdue <= 30:
            current += amount
        elif days_overdue <= 60:
            days_31_60 += amount
        elif days_overdue <= 90:
            days_61_90 += amount
        else:
            over_90 += amount
    
    total_outstanding = current + days_31_60 + days_61_90 + over_90
    
    return AgingReport(
        current=float(current),
        days_31_60=float(days_31_60),
        days_61_90=float(days_61_90),
        over_90_days=float(over_90),
        total_outstanding=float(total_outstanding),
    )


def calculate_monthly_trends(
    db: Session,
    user_id: int,
    end_date: date,
    conversion_rate: Decimal,
) -> list[MonthlyTrend]:
    """Calculate revenue and invoice trends for last 12 months."""
    
    trends = []
    
    for i in range(11, -1, -1):  # 12 months, most recent last
        # Calculate month start and end
        month_end = end_date.replace(day=1) - timedelta(days=i*30)
        month_start = (month_end - timedelta(days=30)).replace(day=1)
        
        # Get revenue for month
        revenue = (
            db.query(func.sum(models.Invoice.amount))
            .filter(
                models.Invoice.issuer_id == user_id,
                models.Invoice.invoice_type == "revenue",
                models.Invoice.status == "paid",
                models.Invoice.created_at >= datetime.combine(month_start, datetime.min.time()),
                models.Invoice.created_at < datetime.combine(month_end, datetime.max.time()),
            )
            .scalar()
        ) or Decimal("0")
        
        # Get invoice count
        invoice_count = (
            db.query(func.count(models.Invoice.id))
            .filter(
                models.Invoice.issuer_id == user_id,
                models.Invoice.invoice_type == "revenue",
                models.Invoice.created_at >= datetime.combine(month_start, datetime.min.time()),
                models.Invoice.created_at < datetime.combine(month_end, datetime.max.time()),
            )
            .scalar()
        ) or 0
        
        # Get expense total
        expenses = (
            db.query(func.sum(models.Invoice.amount))
            .filter(
                models.Invoice.issuer_id == user_id,
                models.Invoice.invoice_type == "expense",
                models.Invoice.created_at >= datetime.combine(month_start, datetime.min.time()),
                models.Invoice.created_at < datetime.combine(month_end, datetime.max.time()),
            )
            .scalar()
        ) or Decimal("0")
        
        revenue_converted = revenue / conversion_rate
        expenses_converted = expenses / conversion_rate
        profit = revenue_converted - expenses_converted
        
        trends.append(
            MonthlyTrend(
                month=month_start.strftime("%b %Y"),
                revenue=float(revenue_converted),
                expenses=float(expenses_converted),
                profit=float(profit),
                invoice_count=invoice_count,
            )
        )
    
    return trends


def get_date_range(period: str) -> tuple[date, date]:
    """Calculate start and end dates based on period."""
    today = date.today()
    
    if period == "7d":
        start_date = today - timedelta(days=7)
    elif period == "30d":
        start_date = today - timedelta(days=30)
    elif period == "90d":
        start_date = today - timedelta(days=90)
    elif period == "1y":
        start_date = today - timedelta(days=365)
    else:  # all
        start_date = date(2020, 1, 1)
    
    return start_date, today


def get_conversion_rate(currency: str) -> Decimal:
    """Get currency conversion rate (NGN to target currency)."""
    # Simplified - in production, use live rates from API
    return Decimal("1550") if currency == "USD" else Decimal("1")
