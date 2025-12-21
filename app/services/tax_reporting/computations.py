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


# Nigerian Company Income Tax (CIT) Rates
# Based on annual gross turnover
CIT_RATES = {
    "small": 0.00,    # ≤₦50M turnover: 0% (exempt)
    "other": 0.30,    # >₦50M turnover: 30%
}

# Development Levy rate (4% of assessable profits for non-small companies)
DEVELOPMENT_LEVY_RATE = 0.04

# Minimum tax rate (0.5% of gross turnover less franked investment income)
MINIMUM_TAX_RATE = 0.005

# Maximum capital allowance claimable (66.67% of assessable profit)
MAX_CAPITAL_ALLOWANCE_RATIO = 0.6667


def compute_company_income_tax(
    profit: Decimal,
    annual_turnover: Optional[Decimal] = None,
    capital_allowances: Optional[Decimal] = None,
) -> dict:
    """
    Calculate Nigerian Company Income Tax (CIT) based on profit and turnover.
    
    CIT Calculation Steps:
    1. Start with accounting profit (profit parameter)
    2. Compute assessable profit (after adjustments - simplified here)
    3. Deduct capital allowances (capped at 66.67% of assessable profit)
    4. Apply CIT rate based on company size (turnover threshold)
    
    CIT Rates (2024 Tax Reform):
    - Small Company (turnover ≤₦50M): 0% (EXEMPT)
    - Other Companies (turnover >₦50M): 30%
    
    Additional Levies:
    - Development Levy: 4% of assessable profits (non-small companies)
    - Minimum Tax: 0.5% of gross turnover (if CIT < minimum tax)
    
    Args:
        profit: Taxable profit (Revenue - Expenses)
        annual_turnover: Annual gross turnover for size classification
        capital_allowances: Capital allowances (tax depreciation) to deduct
        
    Returns:
        dict with cit_amount, development_levy, minimum_tax, effective_rate, 
        company_size, notes
    """
    if profit <= 0:
        return {
            "cit_amount": Decimal("0"),
            "development_levy": Decimal("0"),
            "minimum_tax": Decimal("0"),
            "effective_rate": Decimal("0"),
            "company_size": "small",
            "taxable_profit": Decimal("0"),
            "notes": "No profit - no CIT liability",
        }
    
    turnover = float(annual_turnover or 0)
    
    # Determine company size based on turnover
    if turnover <= 50_000_000:
        company_size = "small"
        cit_rate = CIT_RATES["small"]
    else:
        company_size = "other"
        cit_rate = CIT_RATES["other"]
    
    # Calculate taxable profit after capital allowances
    assessable_profit = profit
    
    if capital_allowances and capital_allowances > 0:
        # Cap capital allowances at 66.67% of assessable profit
        max_allowance = assessable_profit * Decimal(str(MAX_CAPITAL_ALLOWANCE_RATIO))
        actual_allowance = min(capital_allowances, max_allowance)
        taxable_profit = assessable_profit - actual_allowance
    else:
        taxable_profit = assessable_profit
    
    if taxable_profit < Decimal("0"):
        taxable_profit = Decimal("0")
    
    # Calculate CIT
    cit_amount = taxable_profit * Decimal(str(cit_rate))
    
    # Calculate Development Levy (4% for non-small companies)
    if company_size == "small":
        development_levy = Decimal("0")
    else:
        development_levy = assessable_profit * Decimal(str(DEVELOPMENT_LEVY_RATE))
    
    # Calculate Minimum Tax (0.5% of turnover)
    # Applies if CIT is less than minimum tax
    minimum_tax = Decimal("0")
    if company_size != "small" and turnover > 0:
        min_tax_amount = Decimal(str(turnover)) * Decimal(str(MINIMUM_TAX_RATE))
        if cit_amount < min_tax_amount:
            minimum_tax = min_tax_amount - cit_amount
            # Note: In practice, company pays the higher of CIT or minimum tax
    
    # Calculate effective rate
    if profit > 0:
        total_tax = cit_amount + development_levy
        effective_rate = (total_tax / profit * 100)
    else:
        effective_rate = Decimal("0")
    
    # Generate notes
    notes = []
    if company_size == "small":
        notes.append("Small company (turnover ≤₦50M): CIT exempt")
    else:
        notes.append(f"CIT rate: {int(cit_rate * 100)}%")
        if development_levy > 0:
            notes.append(f"Development levy: 4% of assessable profit")
        if minimum_tax > 0:
            notes.append(f"Minimum tax applies (CIT < 0.5% of turnover)")
    
    return {
        "cit_amount": cit_amount.quantize(Decimal("0.01")),
        "development_levy": development_levy.quantize(Decimal("0.01")),
        "minimum_tax": minimum_tax.quantize(Decimal("0.01")),
        "effective_rate": effective_rate.quantize(Decimal("0.01")),
        "company_size": company_size,
        "taxable_profit": taxable_profit.quantize(Decimal("0.01")),
        "notes": "; ".join(notes),
    }


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
