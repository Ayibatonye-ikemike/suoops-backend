"""Tax reporting and computation service with multi-period aggregation support.

Responsibilities:
- Assessable profit computation (basis-aware) for multiple time periods
- VAT aggregation for day/week/month/year periods
- Development levy computation
- Report persistence & PDF attachment
- Period type: day, week, month, year

This module focuses purely on reporting/calculation logic; profile CRUD & classification
remain in TaxProfileService for separation of concerns.
"""
import logging
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.tax_models import MonthlyTaxReport
from app.services.tax_service import TaxProfileService  # for profile access & exemptions

logger = logging.getLogger(__name__)


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


class TaxReportingService:
    def __init__(self, db: Session):
        self.db = db
        self.profile_service = TaxProfileService(db)

    # Wrapper to maintain backward compatibility for tests expecting update_profile on this service
    def update_profile(self, user_id: int, **kwargs):
        return self.profile_service.update_profile(user_id, **kwargs)
    
    # -------- Period Date Range Calculation --------
    def _calculate_period_range(
        self,
        period_type: str,
        year: Optional[int] = None,
        month: Optional[int] = None,
        day: Optional[int] = None,
        week: Optional[int] = None,
    ) -> Tuple[date, date]:
        """Calculate start_date and end_date for a given period type.
        
        Args:
            period_type: 'day', 'week', 'month', or 'year'
            year: Required for all period types
            month: Required for 'month' and 'day'
            day: Required for 'day' period type
            week: Required for 'week' period type (ISO week number)
            
        Returns:
            Tuple of (start_date, end_date) inclusive
        """
        if not year:
            raise ValueError("year is required for all period types")
            
        if period_type == "day":
            if not month or not day:
                raise ValueError("month and day required for daily reports")
            try:
                target_date = date(year, month, day)
                return (target_date, target_date)
            except ValueError as e:
                raise ValueError(f"Invalid date: {year}-{month}-{day}") from e
                
        elif period_type == "week":
            if not week:
                raise ValueError("week number required for weekly reports")
            # ISO 8601 week calculation: week 1 is first week with Thursday
            # Use datetime.fromisocalendar for accurate ISO week dates
            try:
                start_dt = datetime.fromisocalendar(year, week, 1)  # Monday
                end_dt = datetime.fromisocalendar(year, week, 7)    # Sunday
                return (start_dt.date(), end_dt.date())
            except ValueError as e:
                raise ValueError(f"Invalid ISO week: {year}-W{week:02d}") from e
                
        elif period_type == "month":
            if not month:
                raise ValueError("month required for monthly reports")
            try:
                start_dt = datetime(year, month, 1)
                # Calculate last day of month
                if month == 12:
                    end_dt = datetime(year, 12, 31)
                else:
                    end_dt = datetime(year, month + 1, 1) - timedelta(days=1)
                return (start_dt.date(), end_dt.date())
            except ValueError as e:
                raise ValueError(f"Invalid month: {year}-{month}") from e
                
        elif period_type == "year":
            return (date(year, 1, 1), date(year, 12, 31))
            
        else:
            raise ValueError(f"Invalid period_type: {period_type}. Must be day/week/month/year")

    # -------- Report Generation (Multi-Period Support) --------
    def generate_report(
        self,
        user_id: int,
        period_type: str = "month",
        year: Optional[int] = None,
        month: Optional[int] = None,
        day: Optional[int] = None,
        week: Optional[int] = None,
        basis: str = "paid",
        force_regenerate: bool = False,
    ) -> MonthlyTaxReport:
        """Generate or retrieve tax report for any period type.

        Args:
            user_id: User ID
            period_type: 'day', 'week', 'month', or 'year'
            year: Required for all period types
            month: Required for month/day reports
            day: Required for day reports
            week: Required for week reports (ISO week number)
            basis: 'paid' (only paid invoices) or 'all' (all non-refunded)
            force_regenerate: Force regeneration even if report exists
            
        Returns:
            MonthlyTaxReport instance with calculated data
            
        Basis rules:
        - paid: only paid invoices
        - all: all non-refunded invoices
        """
        # Calculate date range for the period
        start_date, end_date = self._calculate_period_range(
            period_type=period_type,
            year=year,
            month=month,
            day=day,
            week=week,
        )
        
        # Check for existing report
        existing = self.db.query(MonthlyTaxReport).filter(
            MonthlyTaxReport.user_id == user_id,
            MonthlyTaxReport.period_type == period_type,
            MonthlyTaxReport.start_date == start_date,
            MonthlyTaxReport.end_date == end_date,
        ).first()
        
        if existing and not force_regenerate:
            return existing

        # Compute profit and levy for the period
        profit = self.compute_assessable_profit_by_date_range(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            basis=basis,
        )
        levy = self.compute_development_levy(user_id, profit)

        # Query invoices in the period (ONLY REVENUE INVOICES for VAT)
        from app.models.models import Invoice
        start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
        
        q = self.db.query(Invoice).filter(
            Invoice.issuer_id == user_id,
            Invoice.invoice_type == "revenue",  # Only revenue invoices have VAT
            Invoice.created_at >= start_dt,
            Invoice.created_at <= end_dt,
        )
        if basis == "paid":
            q = q.filter(Invoice.status == "paid")
        else:
            q = q.filter(Invoice.status != "refunded")
        invoices = q.all()
        
        # Aggregate VAT by category
        taxable_sales = Decimal("0")
        zero_rated_sales = Decimal("0")
        exempt_sales = Decimal("0")
        vat_collected = Decimal("0")
        
        for inv in invoices:
            amount = Decimal(str(inv.amount))
            if inv.discount_amount:
                amount -= Decimal(str(inv.discount_amount))
            cat = (inv.vat_category or "standard").lower()
            if cat in {"standard"}:
                taxable_sales += amount
                if inv.vat_amount:
                    vat_collected += Decimal(str(inv.vat_amount))
            elif cat in {"zero_rated", "export"}:
                zero_rated_sales += amount
            elif cat in {"exempt"}:
                exempt_sales += amount
            else:
                taxable_sales += amount

        # Create or update report
        if not existing:
            report = MonthlyTaxReport(
                user_id=user_id,
                period_type=period_type,
                start_date=start_date,
                end_date=end_date,
                year=year,
                month=month,
                assessable_profit=profit,
                levy_amount=Decimal(str(levy["levy_amount"])),
                vat_collected=vat_collected,
                taxable_sales=taxable_sales,
                zero_rated_sales=zero_rated_sales,
                exempt_sales=exempt_sales,
                pdf_url=None,
            )
            self.db.add(report)
        else:
            report = existing
            report.assessable_profit = profit
            report.levy_amount = Decimal(str(levy["levy_amount"]))
            report.vat_collected = vat_collected
            report.taxable_sales = taxable_sales
            report.zero_rated_sales = zero_rated_sales
            report.exempt_sales = exempt_sales
        
        self.db.commit()
        self.db.refresh(report)
        return report

    def generate_monthly_report(
        self,
        user_id: int,
        year: int,
        month: int,
        basis: str = "paid",
        force_regenerate: bool = False,
    ) -> MonthlyTaxReport:
        """Backward-compatible wrapper for monthly reports.
        
        Delegates to generate_report with period_type='month'.
        
        Basis rules:
        - paid: only paid invoices
        - all: all non-refunded invoices
        """
        return self.generate_report(
            user_id=user_id,
            period_type="month",
            year=year,
            month=month,
            basis=basis,
            force_regenerate=force_regenerate,
        )

    def attach_report_pdf(self, report: MonthlyTaxReport, pdf_url: str) -> MonthlyTaxReport:
        report.pdf_url = pdf_url
        self.db.commit()
        self.db.refresh(report)
        return report

    # -------- Development Levy --------
    def compute_development_levy(self, user_id: int, assessable_profit: Decimal):
        if assessable_profit < 0:
            raise ValueError("assessable_profit must be >= 0")
        profile = self.profile_service.get_or_create_profile(user_id)
        applies = not profile.is_small_business
        rate = Decimal("0.04") if applies else Decimal("0")
        amount = (assessable_profit * rate).quantize(Decimal("0.01"))
        return {
            "user_id": user_id,
            "business_size": profile.business_size,
            "is_small_business": profile.is_small_business,
            "assessable_profit": float(assessable_profit),
            "levy_rate_percent": float(rate * 100),
            "levy_applicable": applies,
            "levy_amount": float(amount),
            "exemption_reason": "small_business" if not applies else None,
        }

    # -------- Assessable Profit --------
    def compute_assessable_profit(
        self,
        user_id: int,
        year: Optional[int] = None,
        month: Optional[int] = None,
        basis: str = "paid",
    ) -> Decimal:
        from app.models.models import Invoice
        q = self.db.query(Invoice).filter(
            Invoice.issuer_id == user_id,
            Invoice.invoice_type == "revenue"  # Only revenue invoices for profit calculation
        )
        if basis == "paid":
            q = q.filter(Invoice.status == "paid")
        else:
            q = q.filter(Invoice.status != "refunded")
        # Apply due_date gating only for global (non-monthly) computations.
        # Monthly report tests expect current-month invoices included even if due date is in future.
        if not (year and month):
            now = datetime.now(timezone.utc)
            q = q.filter((Invoice.due_date.is_(None)) | (Invoice.due_date <= now))
        if year and month:
            start = datetime(year, month, 1, tzinfo=timezone.utc)
            end = datetime(year + (month == 12), (month % 12) + 1, 1, tzinfo=timezone.utc)
            q = q.filter(Invoice.created_at >= start, Invoice.created_at < end)
        invoices = q.all()
        total = Decimal("0")
        for inv in invoices:
            amount = Decimal(str(inv.amount))
            if inv.discount_amount:
                amount -= Decimal(str(inv.discount_amount))
            total += amount
        return total

    def compute_assessable_profit_by_date_range(
        self,
        user_id: int,
        start_date: date,
        end_date: date,
        basis: str = "paid",
    ) -> Decimal:
        """Compute assessable profit (ACTUAL PROFIT = Revenue - Expenses) for a date range.
        
        Per 2026 Nigerian Tax Law: Profit = Revenue - Expenses
        
        Args:
            user_id: User ID
            start_date: Start date of period (inclusive)
            end_date: End date of period (inclusive)
            basis: 'paid' (only paid invoices) or 'all' (all non-refunded)
            
        Returns:
            Actual profit (Revenue - Expenses) for the period
        """
        return compute_actual_profit_by_date_range(
            self.db,
            user_id,
            start_date,
            end_date,
            basis,
        )
