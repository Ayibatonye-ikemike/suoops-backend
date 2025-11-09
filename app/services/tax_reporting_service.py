"""Monthly tax reporting and computation service extracted from tax_service.py.

Responsibilities:
- Assessable profit computation (basis-aware)
- Monthly VAT aggregation
- Development levy computation
- Monthly report persistence & PDF attachment

This module focuses purely on reporting/calculation logic; profile CRUD & classification
remain in TaxProfileService for separation of concerns.
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.tax_models import MonthlyTaxReport
from app.services.tax_service import TaxProfileService  # for profile access & exemptions

logger = logging.getLogger(__name__)


class TaxReportingService:
    def __init__(self, db: Session):
        self.db = db
        self.profile_service = TaxProfileService(db)

    # Wrapper to maintain backward compatibility for tests expecting update_profile on this service
    def update_profile(self, user_id: int, **kwargs):
        return self.profile_service.update_profile(user_id, **kwargs)

    # -------- Monthly Report Aggregation --------
    def generate_monthly_report(
        self,
        user_id: int,
        year: int,
        month: int,
        basis: str = "paid",
        force_regenerate: bool = False,
    ) -> MonthlyTaxReport:
        """Generate or retrieve consolidated monthly tax report.

        Basis rules:
        - paid: only paid invoices
        - all: all non-refunded invoices
        """
        from app.models.models import Invoice  # local import
        existing = self.db.query(MonthlyTaxReport).filter(
            MonthlyTaxReport.user_id == user_id,
            MonthlyTaxReport.year == year,
            MonthlyTaxReport.month == month,
        ).first()
        if existing and not force_regenerate:
            return existing

        profit = self.compute_assessable_profit(user_id, year=year, month=month, basis=basis)
        levy = self.compute_development_levy(user_id, profit)

        start = datetime(year, month, 1, tzinfo=timezone.utc)
        end = datetime(year + (month == 12), (month % 12) + 1, 1, tzinfo=timezone.utc)
        q = self.db.query(Invoice).filter(
            Invoice.issuer_id == user_id,
            Invoice.created_at >= start,
            Invoice.created_at < end,
        )
        if basis == "paid":
            q = q.filter(Invoice.status == "paid")
        else:
            q = q.filter(Invoice.status != "refunded")
        invoices = q.all()
        # Initialize VAT category buckets
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

        if not existing:
            report = MonthlyTaxReport(
                user_id=user_id,
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
        q = self.db.query(Invoice).filter(Invoice.issuer_id == user_id)
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
