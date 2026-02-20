"""Analytics calculation service for business metrics."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, case, extract, func, or_
from sqlalchemy.orm import Session

from app.models import models
from app.models.schemas import (
    AgingReport,
    CustomerMetrics,
    InvoiceMetrics,
    MonthlyTrend,
    RevenueMetrics,
)


def calculate_revenue_metrics(
    db: Session,
    user_id: int,
    start_date: date,
    end_date: date,
    conversion_rate: Decimal,
) -> RevenueMetrics:
    """Calculate total revenue, paid, pending, and overdue amounts.

    Uses a single SQL aggregation query instead of loading all invoices
    into Python memory.
    """
    end_dt = datetime.combine(end_date, datetime.max.time())
    start_dt = datetime.combine(start_date, datetime.min.time())

    # Single query with conditional aggregation
    row = (
        db.query(
            func.coalesce(func.sum(models.Invoice.amount), 0).label("total"),
            func.coalesce(
                func.sum(case((models.Invoice.status == "paid", models.Invoice.amount), else_=0)),
                0,
            ).label("paid"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                models.Invoice.status == "pending",
                                models.Invoice.due_date != None,  # noqa: E711
                                models.Invoice.due_date < end_dt,
                            ),
                            models.Invoice.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("overdue"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                models.Invoice.status == "pending",
                                or_(
                                    models.Invoice.due_date == None,  # noqa: E711
                                    models.Invoice.due_date >= end_dt,
                                ),
                            ),
                            models.Invoice.amount,
                        ),
                        (models.Invoice.status == "awaiting_confirmation", models.Invoice.amount),
                        else_=0,
                    )
                ),
                0,
            ).label("pending"),
            func.count(models.Invoice.id).label("cnt"),
        )
        .filter(
            models.Invoice.issuer_id == user_id,
            models.Invoice.invoice_type == "revenue",
            models.Invoice.created_at >= start_dt,
            models.Invoice.created_at <= end_dt,
        )
        .first()
    )

    total_revenue = Decimal(str(row.total)) / conversion_rate
    paid_revenue = Decimal(str(row.paid)) / conversion_rate
    overdue_revenue = Decimal(str(row.overdue)) / conversion_rate
    pending_revenue = Decimal(str(row.pending)) / conversion_rate
    count = row.cnt or 0

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
            models.Invoice.created_at < start_dt,
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
        average_invoice_value=float(total_revenue / count) if count else 0.0,
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
            func.sum(case((models.Invoice.status == "failed", 1), else_=0)).label("failed"),
            func.sum(case((models.Invoice.status == "awaiting_confirmation", 1), else_=0)).label("awaiting"),
            func.sum(case((models.Invoice.status == "cancelled", 1), else_=0)).label("cancelled"),
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
    failed = invoices.failed or 0
    awaiting = invoices.awaiting or 0
    cancelled = invoices.cancelled or 0
    
    # Calculate conversion rate (paid / total)
    conversion_rate = (paid / total * 100) if total > 0 else 0.0
    
    return InvoiceMetrics(
        total_invoices=total,
        paid_invoices=paid,
        pending_invoices=pending,
        failed_invoices=failed,
        awaiting_confirmation=awaiting,
        cancelled_invoices=cancelled,
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
    """Calculate accounts receivable aging buckets.

    Uses SQL CASE bucketing instead of loading all unpaid invoices into memory.
    """
    cutoff_30 = datetime.combine(reference_date - timedelta(days=30), datetime.min.time())
    cutoff_60 = datetime.combine(reference_date - timedelta(days=60), datetime.min.time())
    cutoff_90 = datetime.combine(reference_date - timedelta(days=90), datetime.min.time())

    base_filter = [
        models.Invoice.issuer_id == user_id,
        models.Invoice.invoice_type == "revenue",
        models.Invoice.status.in_(["pending", "awaiting_confirmation"]),
    ]

    row = (
        db.query(
            # Current bucket: no due_date OR due_date within last 30 days or in future
            func.coalesce(
                func.sum(
                    case(
                        (
                            or_(
                                models.Invoice.due_date == None,  # noqa: E711
                                models.Invoice.due_date >= cutoff_30,
                            ),
                            models.Invoice.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("current_bucket"),
            # 31-60 days
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                models.Invoice.due_date < cutoff_30,
                                models.Invoice.due_date >= cutoff_60,
                            ),
                            models.Invoice.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("days_31_60"),
            # 61-90 days
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                models.Invoice.due_date < cutoff_60,
                                models.Invoice.due_date >= cutoff_90,
                            ),
                            models.Invoice.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("days_61_90"),
            # Over 90 days
            func.coalesce(
                func.sum(
                    case(
                        (models.Invoice.due_date < cutoff_90, models.Invoice.amount),
                        else_=0,
                    )
                ),
                0,
            ).label("over_90"),
        )
        .filter(*base_filter)
        .first()
    )

    current = Decimal(str(row.current_bucket)) / conversion_rate
    d31_60 = Decimal(str(row.days_31_60)) / conversion_rate
    d61_90 = Decimal(str(row.days_61_90)) / conversion_rate
    over_90 = Decimal(str(row.over_90)) / conversion_rate
    total_outstanding = current + d31_60 + d61_90 + over_90

    return AgingReport(
        current=float(current),
        days_31_60=float(d31_60),
        days_61_90=float(d61_90),
        over_90_days=float(over_90),
        total_outstanding=float(total_outstanding),
    )


def calculate_monthly_trends(
    db: Session,
    user_id: int,
    end_date: date,
    conversion_rate: Decimal,
) -> list[MonthlyTrend]:
    """Calculate revenue and invoice trends for last 12 months.

    Uses a single GROUP BY query instead of 36 individual queries (3 per month).
    """
    # Determine the 12-month window (current month + 11 prior months)
    end_month = end_date.replace(day=1)
    # Go back 11 months from end_month to get exactly 12 months total
    start_month_raw = end_month.month - 11
    start_year = end_month.year
    if start_month_raw <= 0:
        start_month_raw += 12
        start_year -= 1
    month_start = date(start_year, start_month_raw, 1)
    end_dt = datetime.combine(end_date, datetime.max.time())
    start_dt = datetime.combine(month_start, datetime.min.time())

    yr_col = extract("year", models.Invoice.created_at).label("yr")
    mo_col = extract("month", models.Invoice.created_at).label("mo")

    rows = (
        db.query(
            yr_col,
            mo_col,
            models.Invoice.invoice_type,
            func.coalesce(
                func.sum(
                    case((models.Invoice.status == "paid", models.Invoice.amount), else_=0)
                ),
                0,
            ).label("paid_amount"),
            func.coalesce(func.sum(models.Invoice.amount), 0).label("total_amount"),
            func.count(models.Invoice.id).label("cnt"),
        )
        .filter(
            models.Invoice.issuer_id == user_id,
            models.Invoice.invoice_type.in_(["revenue", "expense"]),
            models.Invoice.created_at >= start_dt,
            models.Invoice.created_at <= end_dt,
        )
        .group_by(yr_col, mo_col, models.Invoice.invoice_type)
        .all()
    )

    # Build lookup: (year, month) → {revenue, expenses, count}
    data: dict[tuple[int, int], dict] = {}
    for row in rows:
        key = (int(row.yr), int(row.mo))
        entry = data.setdefault(key, {"revenue": Decimal("0"), "expenses": Decimal("0"), "count": 0})
        if row.invoice_type == "revenue":
            entry["revenue"] = Decimal(str(row.paid_amount))
            entry["count"] = row.cnt
        elif row.invoice_type == "expense":
            entry["expenses"] = Decimal(str(row.total_amount))

    # Build ordered trend list for the 12-month window
    trends: list[MonthlyTrend] = []
    cursor = month_start
    while cursor <= end_date:
        key = (cursor.year, cursor.month)
        entry = data.get(key, {"revenue": Decimal("0"), "expenses": Decimal("0"), "count": 0})

        revenue_converted = entry["revenue"] / conversion_rate
        expenses_converted = entry["expenses"] / conversion_rate
        profit = revenue_converted - expenses_converted

        trends.append(
            MonthlyTrend(
                month=cursor.strftime("%b %Y"),
                revenue=float(revenue_converted),
                expenses=float(expenses_converted),
                profit=float(profit),
                invoice_count=entry["count"],
            )
        )

        # Advance to next month
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)

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
    """Get currency conversion rate (NGN to target currency).

    Uses the ``NGN_USD_RATE`` env-var when available so ops can update it
    without a deploy.  Falls back to a reasonable default and logs a
    warning so the team knows to set it.
    """
    if currency != "USD":
        return Decimal("1")

    import os

    rate_str = os.getenv("NGN_USD_RATE")
    if rate_str:
        try:
            return Decimal(rate_str)
        except Exception:  # noqa: BLE001
            import logging as _log
            _log.getLogger(__name__).warning(
                "Invalid NGN_USD_RATE value '%s', falling back to default", rate_str
            )

    import logging as _log

    _log.getLogger(__name__).warning(
        "NGN_USD_RATE env var not set – using default 1600. "
        "Set NGN_USD_RATE to the current Naira/USD rate."
    )
    return Decimal("1600")


# ── Cash-First Dashboard ─────────────────────────────────────────────


def calculate_cash_position(db: Session, user_id: int) -> dict:
    """Cash-first dashboard: collected, outstanding, overdue, expected inflow.

    Gives business owners an instant snapshot of *money movement* rather
    than abstract accounting metrics.
    """
    today = date.today()
    week_ago = today - timedelta(days=7)
    next_week = today + timedelta(days=7)
    start_of_today = datetime.combine(today, datetime.min.time())
    start_of_week = datetime.combine(week_ago, datetime.min.time())
    end_of_next_week = datetime.combine(next_week, datetime.max.time())

    base = [
        models.Invoice.issuer_id == user_id,
        models.Invoice.invoice_type == "revenue",
    ]

    # Cash collected this week
    cash_this_week = (
        db.query(func.coalesce(func.sum(models.Invoice.amount), 0))
        .filter(
            *base,
            models.Invoice.status == "paid",
            models.Invoice.paid_at >= start_of_week,
        )
        .scalar()
    )

    # Cash collected today
    cash_today = (
        db.query(func.coalesce(func.sum(models.Invoice.amount), 0))
        .filter(
            *base,
            models.Invoice.status == "paid",
            models.Invoice.paid_at >= start_of_today,
        )
        .scalar()
    )

    # Total outstanding (unpaid revenue invoices)
    outstanding = (
        db.query(func.coalesce(func.sum(models.Invoice.amount), 0))
        .filter(
            *base,
            models.Invoice.status.in_(["pending", "awaiting_confirmation"]),
        )
        .scalar()
    )

    # Overdue amount + count
    overdue_filters = [
        *base,
        models.Invoice.status == "pending",
        models.Invoice.due_date != None,  # noqa: E711
        models.Invoice.due_date < start_of_today,
    ]
    overdue_amount = (
        db.query(func.coalesce(func.sum(models.Invoice.amount), 0))
        .filter(*overdue_filters)
        .scalar()
    )
    overdue_count = (
        db.query(func.count(models.Invoice.id))
        .filter(*overdue_filters)
        .scalar()
    ) or 0

    # Expected inflow next 7 days
    expected_inflow = (
        db.query(func.coalesce(func.sum(models.Invoice.amount), 0))
        .filter(
            *base,
            models.Invoice.status.in_(["pending", "awaiting_confirmation"]),
            models.Invoice.due_date != None,  # noqa: E711
            models.Invoice.due_date >= start_of_today,
            models.Invoice.due_date <= end_of_next_week,
        )
        .scalar()
    )

    # Invoices created today
    invoices_today = (
        db.query(func.count(models.Invoice.id))
        .filter(*base, models.Invoice.created_at >= start_of_today)
        .scalar()
    ) or 0

    # Expenses today
    expenses_today = (
        db.query(func.coalesce(func.sum(models.Invoice.amount), 0))
        .filter(
            models.Invoice.issuer_id == user_id,
            models.Invoice.invoice_type == "expense",
            models.Invoice.created_at >= start_of_today,
        )
        .scalar()
    )

    return {
        "cash_collected_today": float(cash_today),
        "cash_collected_this_week": float(cash_this_week),
        "total_outstanding": float(outstanding),
        "total_overdue": float(overdue_amount),
        "overdue_count": overdue_count,
        "expected_inflow_7_days": float(expected_inflow),
        "invoices_created_today": invoices_today,
        "expenses_today": float(expenses_today),
        "net_today": float(cash_today) - float(expenses_today),
    }


# ── Customer Insights ────────────────────────────────────────────────


def calculate_customer_insights(
    db: Session,
    user_id: int,
    limit: int = 20,
) -> dict:
    """Customer value, payment speed, dormancy insights.

    Segments customers into VIP / Active / New / At-Risk / Dormant so the
    business knows who to nurture and who to re-engage.
    """
    today = date.today()

    customer_stats = (
        db.query(
            models.Customer.id,
            models.Customer.name,
            models.Customer.phone,
            func.sum(models.Invoice.amount).label("total_spent"),
            func.count(models.Invoice.id).label("invoice_count"),
            func.max(models.Invoice.created_at).label("last_invoice_date"),
            func.sum(
                case((models.Invoice.status == "paid", 1), else_=0)
            ).label("paid_count"),
        )
        .join(models.Invoice, models.Invoice.customer_id == models.Customer.id)
        .filter(
            models.Invoice.issuer_id == user_id,
            models.Invoice.invoice_type == "revenue",
        )
        .group_by(models.Customer.id, models.Customer.name, models.Customer.phone)
        .order_by(func.sum(models.Invoice.amount).desc())
        .limit(limit)
        .all()
    )

    customers = []
    for row in customer_stats:
        last_dt = row.last_invoice_date
        days_since_last = (today - last_dt.date()).days if last_dt else 999

        total = float(row.total_spent or 0)
        count = row.invoice_count or 0
        paid = row.paid_count or 0

        # Status segmentation
        if count == 1 and days_since_last < 30:
            status = "new"
        elif days_since_last > 90:
            status = "dormant"
        elif total >= 100_000 and count >= 3:
            status = "vip"
        elif days_since_last <= 30:
            status = "active"
        else:
            status = "at_risk"

        payment_rate = round(paid / count * 100, 1) if count else 0.0

        customers.append(
            {
                "id": row.id,
                "name": row.name,
                "phone": row.phone,
                "total_spent": total,
                "invoice_count": count,
                "paid_count": paid,
                "payment_rate": payment_rate,
                "last_purchase_days_ago": days_since_last,
                "status": status,
            }
        )

    status_counts: dict[str, int] = {}
    for c in customers:
        status_counts[c["status"]] = status_counts.get(c["status"], 0) + 1

    dormant = [c for c in customers if c["status"] in ("dormant", "at_risk")]

    return {
        "customers": customers,
        "summary": status_counts,
        "dormant_customers": dormant,
        "total_analyzed": len(customers),
    }


# ── Professionalism Score ────────────────────────────────────────────


def calculate_professionalism_score(db: Session, user_id: int) -> dict:
    """Score how professional the business looks to customers (0-100).

    Five checks, 20 points each:
    1. Has logo
    2. Has bank details
    3. Uses due dates on invoices
    4. Sends receipts on payment
    5. Includes payment instructions
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return {"score": 0, "checks": {}, "tips": []}

    checks: dict[str, bool] = {}
    tips: list[str] = []

    # 1. Has logo (+20)
    has_logo = bool(user.logo_url)
    checks["has_logo"] = has_logo
    if not has_logo:
        tips.append("Upload your business logo to look more credible on invoices.")

    # 2. Has bank details (+20)
    has_bank = bool(user.bank_name and user.account_number)
    checks["has_bank_details"] = has_bank
    if not has_bank:
        tips.append("Add your bank details so customers know where to pay.")

    # 3. Uses due dates on invoices (+20)
    recent_invoices = (
        db.query(models.Invoice)
        .filter(
            models.Invoice.issuer_id == user_id,
            models.Invoice.invoice_type == "revenue",
        )
        .order_by(models.Invoice.created_at.desc())
        .limit(10)
        .all()
    )
    with_due_date = sum(1 for inv in recent_invoices if inv.due_date)
    due_ratio = with_due_date / len(recent_invoices) if recent_invoices else 0
    checks["uses_due_dates"] = due_ratio >= 0.7
    if due_ratio < 0.7:
        tips.append("Set due dates on your invoices — businesses that do collect 30 %% faster.")

    # 4. Sends receipts on payment (+20)
    paid_invoices = (
        db.query(models.Invoice)
        .filter(
            models.Invoice.issuer_id == user_id,
            models.Invoice.invoice_type == "revenue",
            models.Invoice.status == "paid",
        )
        .order_by(models.Invoice.created_at.desc())
        .limit(10)
        .all()
    )
    with_receipt = sum(1 for inv in paid_invoices if inv.receipt_pdf_url)
    receipt_ratio = with_receipt / len(paid_invoices) if paid_invoices else 0
    checks["sends_receipts"] = receipt_ratio >= 0.7
    if receipt_ratio < 0.7:
        tips.append("Send receipts when customers pay — it builds trust and repeat business.")

    # 5. Includes payment instructions (+20)
    with_notes = sum(1 for inv in recent_invoices if inv.notes)
    notes_ratio = with_notes / len(recent_invoices) if recent_invoices else 0
    checks["has_payment_instructions"] = notes_ratio >= 0.5
    if notes_ratio < 0.5:
        tips.append("Include payment instructions on invoices for clarity.")

    score = sum(20 for v in checks.values() if v)
    if score >= 80:
        level = "Excellent"
    elif score >= 60:
        level = "Good"
    elif score >= 40:
        level = "Fair"
    else:
        level = "Needs Work"

    return {"score": score, "checks": checks, "tips": tips, "level": level}


# ── Margin & Discount Insights ───────────────────────────────────────


def calculate_margin_insights(
    db: Session,
    user_id: int,
    start_date: date,
    end_date: date,
) -> dict:
    """Discount leakage and product margin analysis.

    Shows how much revenue is lost to discounts and which products have
    thin margins — so the business can price more profitably.
    """
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())
    period_filter = [
        models.Invoice.issuer_id == user_id,
        models.Invoice.invoice_type == "revenue",
        models.Invoice.created_at >= start_dt,
        models.Invoice.created_at <= end_dt,
    ]

    # ── Discount leakage ──
    disc_row = (
        db.query(
            func.count(models.Invoice.id).label("disc_count"),
            func.coalesce(func.sum(models.Invoice.discount_amount), 0).label("total_discounts"),
        )
        .filter(*period_filter, models.Invoice.discount_amount > 0)
        .first()
    )

    total_rev = (
        db.query(func.coalesce(func.sum(models.Invoice.amount), 0))
        .filter(*period_filter)
        .scalar()
    )

    total_discounts = float(disc_row.total_discounts) if disc_row else 0.0
    total_revenue = float(total_rev) if total_rev else 0.0
    disc_count = disc_row.disc_count if disc_row else 0

    # Top discounted customers
    top_discounted = (
        db.query(
            models.Customer.name,
            func.count(models.Invoice.id).label("count"),
            func.sum(models.Invoice.discount_amount).label("total_discount"),
        )
        .join(models.Customer, models.Invoice.customer_id == models.Customer.id)
        .filter(*period_filter, models.Invoice.discount_amount > 0)
        .group_by(models.Customer.name)
        .order_by(func.sum(models.Invoice.discount_amount).desc())
        .limit(5)
        .all()
    )

    # ── Product margins (from inventory) ──
    product_margins: list[dict] = []
    try:
        from app.models.inventory_models import Product

        products = (
            db.query(Product)
            .filter(
                Product.user_id == user_id,
                Product.cost_price > 0,
                Product.selling_price > 0,
                Product.is_active.is_(True),
            )
            .all()
        )
        for p in products:
            margin = float(
                (p.selling_price - p.cost_price) / p.selling_price * 100
            )
            product_margins.append(
                {
                    "name": p.name,
                    "cost_price": float(p.cost_price),
                    "selling_price": float(p.selling_price),
                    "margin_percent": round(margin, 1),
                    "stock": p.quantity_in_stock,
                }
            )
        product_margins.sort(key=lambda x: x["margin_percent"])
    except Exception:
        pass  # Inventory module may not be in use

    return {
        "total_discounts": total_discounts,
        "discount_count": disc_count,
        "total_revenue": total_revenue,
        "discount_as_percent_of_revenue": (
            round(total_discounts / total_revenue * 100, 1) if total_revenue else 0.0
        ),
        "top_discounted_customers": [
            {
                "name": c.name,
                "count": c.count,
                "total_discount": float(c.total_discount),
            }
            for c in (top_discounted or [])
        ],
        "product_margins": product_margins[:10],
        "low_margin_count": sum(1 for p in product_margins if p["margin_percent"] < 20),
    }
