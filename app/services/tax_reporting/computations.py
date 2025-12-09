"""Tax computation functions and constants.

Pure computation logic for Nigerian Personal Income Tax (PIT)
and profit calculations. No database access in helper functions.
"""
import logging
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# Nigerian Personal Income Tax (PIT) Bands for 2026
# Progressive taxation on profit (revenue - expenses)
PIT_BANDS = [
    (800_000, 0.00),         # First ₦800,000: 0%
    (3_000_000, 0.15),       # Next ₦2.2M (₦800K-₦3M): 15%
    (12_000_000, 0.18),      # Next ₦9M (₦3M-₦12M): 18%
    (25_000_000, 0.21),      # Next ₦13M (₦12M-₦25M): 21%
    (50_000_000, 0.23),      # Next ₦25M (₦25M-₦50M): 23%
    (float('inf'), 0.25),    # Above ₦50M: 25%
]


def compute_personal_income_tax(profit: Decimal) -> dict:
    """
    Calculate Nigerian Personal Income Tax (PIT) using progressive bands.
    
    Per 2026 Nigerian Tax Law:
    - Small businesses (turnover <₦50M) are exempt from CIT
    - Owners pay PIT on profit using progressive rates
    - Tax is charged on profit (Revenue - Expenses), not revenue
    
    Args:
        profit: Taxable profit (Revenue - Expenses)
        
    Returns:
        dict with pit_amount, effective_rate, band_label
    """
    if profit <= 0:
        return {
            "pit_amount": Decimal("0"),
            "effective_rate": Decimal("0"),
            "band_label": "0% (No profit)",
        }
    
    profit_float = float(profit)
    tax_amount = Decimal("0")
    previous_threshold = 0
    
    # Calculate tax using progressive bands
    for threshold, rate in PIT_BANDS:
        if profit_float <= previous_threshold:
            break
            
        taxable_in_band = min(profit_float, threshold) - previous_threshold
        tax_in_band = Decimal(str(taxable_in_band * rate))
        tax_amount += tax_in_band
        
        previous_threshold = threshold
    
    # Determine which band the profit falls into
    for threshold, rate in PIT_BANDS:
        if profit_float <= threshold:
            band_label = f"{int(rate * 100)}%"
            break
    else:
        band_label = "25%"
    
    # Calculate effective rate
    effective_rate = (tax_amount / profit * 100) if profit > 0 else Decimal("0")
    
    return {
        "pit_amount": tax_amount.quantize(Decimal("0.01")),
        "effective_rate": effective_rate.quantize(Decimal("0.01")),
        "band_label": band_label,
    }


def compute_revenue_by_date_range(
    db: Session,
    user_id: int,
    start_date: date,
    end_date: date,
    basis: str = "paid",
) -> Decimal:
    """
    Compute total revenue from REVENUE invoices for a date range.
    
    Uses unified Invoice model filtered by invoice_type='revenue'.
    
    Args:
        db: Database session
        user_id: User ID
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
        basis: 'paid' (only paid invoices) or 'all' (all non-refunded)
        
    Returns:
        Total revenue for the period
    """
    from app.models.models import Invoice
    
    # Convert dates to datetime with timezone
    start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    q = db.query(Invoice).filter(
        Invoice.issuer_id == user_id,
        Invoice.invoice_type == "revenue",  # Only revenue invoices
        Invoice.created_at >= start_dt,
        Invoice.created_at <= end_dt,
    )
    
    if basis == "paid":
        q = q.filter(Invoice.status == "paid")
    else:
        q = q.filter(Invoice.status != "refunded")
    
    invoices = q.all()
    total = Decimal("0")
    for inv in invoices:
        amount = Decimal(str(inv.amount))
        if inv.discount_amount:
            amount -= Decimal(str(inv.discount_amount))
        total += amount
    return total


def compute_expenses_by_date_range(
    db: Session,
    user_id: int,
    start_date: date,
    end_date: date,
) -> Decimal:
    """
    Compute total expenses from EXPENSE invoices for a date range.
    
    Uses unified Invoice model filtered by invoice_type='expense'.
    No longer uses separate Expense table.
    
    Args:
        db: Database session
        user_id: User ID
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
        
    Returns:
        Total expenses for the period
    """
    from app.models.models import Invoice
    
    # Convert dates to datetime with timezone
    start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    result = db.query(func.sum(Invoice.amount)).filter(
        Invoice.issuer_id == user_id,
        Invoice.invoice_type == "expense",  # Only expense invoices
        Invoice.created_at >= start_dt,
        Invoice.created_at <= end_dt,
        Invoice.status == "paid",  # Only count paid expenses
    ).scalar()
    
    return result or Decimal("0")


def compute_actual_profit_by_date_range(
    db: Session,
    user_id: int,
    start_date: date,
    end_date: date,
    basis: str = "paid",
) -> Decimal:
    """
    Compute ACTUAL profit: Revenue - Expenses.
    
    This is the correct taxable profit calculation per 2026 Nigerian Tax Law.
    
    Args:
        db: Database session
        user_id: User ID
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
        basis: 'paid' (only paid invoices) or 'all' (all non-refunded)
        
    Returns:
        Actual profit (Revenue - Expenses) for the period
    """
    revenue = compute_revenue_by_date_range(db, user_id, start_date, end_date, basis)
    expenses = compute_expenses_by_date_range(db, user_id, start_date, end_date)
    
    profit = revenue - expenses
    
    logger.info(
        f"Profit calculation for user {user_id} ({start_date} to {end_date}): "
        f"Revenue={revenue}, Expenses={expenses}, Profit={profit}"
    )
    
    return profit
