"""Analytics dashboard endpoints for business metrics and insights."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.api.dependencies import get_data_owner_id
from app.api.routes_auth import get_current_user_id
from app.db.session import get_db
from app.models import models
from app.models.schemas import AnalyticsDashboard
from app.services.analytics_service import (
    calculate_aging_report,
    calculate_customer_metrics,
    calculate_invoice_metrics,
    calculate_monthly_trends,
    calculate_revenue_metrics,
    get_conversion_rate,
    get_date_range,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Type aliases for dependency injection
CurrentUserDep = Annotated[int, Depends(get_current_user_id)]
DataOwnerDep = Annotated[int, Depends(get_data_owner_id)]
DbDep = Annotated[Session, Depends(get_db)]


@router.get("/dashboard", response_model=AnalyticsDashboard)
async def get_analytics_dashboard(
    current_user_id: CurrentUserDep,
    data_owner_id: DataOwnerDep,
    db: DbDep,
    period: str = Query("30d", pattern="^(7d|30d|90d|1y|all)$"),
    currency: str = Query("NGN", pattern="^(NGN|USD)$"),
) -> AnalyticsDashboard:
    """
    Get comprehensive analytics dashboard with revenue, invoices, customers, and aging.
    
    Args:
        current_user_id: Authenticated user ID
        data_owner_id: Data owner ID (team admin for members)
        db: Database session
        period: Time period (7d, 30d, 90d, 1y, all)
        currency: Display currency (NGN or USD)
        
    Returns:
        Complete analytics dashboard data (team data for team members)
    """
    # Calculate date range and conversion rate
    start_date, end_date = get_date_range(period)
    conversion_rate = get_conversion_rate(currency)
    
    # Calculate all metrics using data_owner_id for team context
    revenue_metrics = calculate_revenue_metrics(
        db, data_owner_id, start_date, end_date, conversion_rate
    )
    
    invoice_metrics = calculate_invoice_metrics(
        db, data_owner_id, start_date, end_date
    )
    
    customer_metrics = calculate_customer_metrics(
        db, data_owner_id, start_date, end_date
    )
    
    aging_report = calculate_aging_report(
        db, data_owner_id, end_date, conversion_rate
    )
    
    monthly_trends = calculate_monthly_trends(
        db, data_owner_id, end_date, conversion_rate
    )
    
    return AnalyticsDashboard(
        period=period,
        currency=currency,
        start_date=start_date,
        end_date=end_date,
        revenue=revenue_metrics,
        invoices=invoice_metrics,
        customers=customer_metrics,
        aging=aging_report,
        monthly_trends=monthly_trends,
    )


@router.get("/revenue-by-customer")
async def get_revenue_by_customer(
    current_user_id: CurrentUserDep,
    data_owner_id: DataOwnerDep,
    db: DbDep,
    period: str = Query("30d", pattern="^(7d|30d|90d|1y|all)$"),
    limit: int = Query(10, ge=1, le=100),
):
    """Get top customers by revenue (team data for team members)."""
    
    start_date, _ = get_date_range(period)
    
    # Query top customers using data_owner_id
    top_customers = (
        db.query(
            models.Customer.name,
            func.sum(models.Invoice.amount).label("total_revenue"),
            func.count(models.Invoice.id).label("invoice_count"),
        )
        .join(models.Invoice, models.Invoice.customer_id == models.Customer.id)
        .filter(
            models.Invoice.issuer_id == data_owner_id,
            models.Invoice.invoice_type == "revenue",
            models.Invoice.status == "paid",
            models.Invoice.created_at >= datetime.combine(start_date, datetime.min.time()),
        )
        .group_by(models.Customer.id, models.Customer.name)
        .order_by(func.sum(models.Invoice.amount).desc())
        .limit(limit)
        .all()
    )
    
    return {
        "period": period,
        "customers": [
            {
                "name": customer.name,
                "total_revenue": float(customer.total_revenue),
                "invoice_count": customer.invoice_count,
            }
            for customer in top_customers
        ],
    }


@router.get("/conversion-funnel")
async def get_conversion_funnel(
    current_user_id: CurrentUserDep,
    data_owner_id: DataOwnerDep,
    db: DbDep,
    period: str = Query("30d", pattern="^(7d|30d|90d|1y|all)$"),
):
    """Get invoice conversion funnel (created → paid). Returns team data for team members."""
    
    start_date, _ = get_date_range(period)
    
    # Count invoices by status using data_owner_id
    stats = (
        db.query(
            func.count(models.Invoice.id).label("total"),
            func.sum(case((models.Invoice.status == "paid", 1), else_=0)).label("paid"),
            func.sum(case((models.Invoice.status == "awaiting_confirmation", 1), else_=0)).label("awaiting"),
            func.sum(case((models.Invoice.status == "pending", 1), else_=0)).label("pending"),
            func.sum(case((models.Invoice.status == "cancelled", 1), else_=0)).label("cancelled"),
        )
        .filter(
            models.Invoice.issuer_id == data_owner_id,
            models.Invoice.invoice_type == "revenue",
            models.Invoice.created_at >= datetime.combine(start_date, datetime.min.time()),
        )
        .first()
    )
    
    total = stats.total or 0
    paid = stats.paid or 0
    awaiting = stats.awaiting or 0
    cancelled = stats.cancelled or 0
    
    return {
        "period": period,
        "funnel": {
            "created": total,
            "sent": total,  # All created invoices are "sent"
            "viewed": awaiting + paid,  # Assuming viewed if status changed
            "awaiting_confirmation": awaiting,
            "paid": paid,
            "cancelled": cancelled,
        },
        "conversion_rates": {
            "sent_to_viewed": ((awaiting + paid) / total * 100) if total > 0 else 0,
            "viewed_to_paid": (paid / (awaiting + paid) * 100) if (awaiting + paid) > 0 else 0,
            "overall": (paid / total * 100) if total > 0 else 0,
        },
    }
