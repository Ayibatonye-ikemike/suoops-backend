"""
Tax and VAT Compliance API Routes.

Endpoints:
- GET/POST /tax/profile - Tax profile management
- GET /tax/vat/summary - VAT compliance dashboard
- GET /tax/vat/calculate - VAT calculator
- POST /tax/vat/return - Generate VAT return
- POST /tax/invoice/{id}/fiscalize - Fiscalize invoice

All endpoints require authentication.
"""
import logging
from decimal import Decimal
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.api.routes_auth import get_current_user_id
from app.services.tax_service import TaxProfileService  # Use unified tax profile & summary service
from app.models.tax_models import MonthlyTaxReport
from app.metrics import tax_profile_updated, vat_calculation_record, compliance_check_record
from app.services.vat_service import VATService
from app.services.fiscalization_service import FiscalizationService, VATCalculator
from app.models.models import Invoice

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tax", tags=["tax"])


# Pydantic schemas for request/response
class TaxProfileUpdate(BaseModel):
    """Tax profile update request"""
    annual_turnover: Optional[Decimal] = Field(None, ge=0, description="Annual turnover in Naira")
    fixed_assets: Optional[Decimal] = Field(None, ge=0, description="Fixed assets value in Naira")
    tin: Optional[str] = Field(None, max_length=20, description="Tax Identification Number")
    vat_registration_number: Optional[str] = Field(None, max_length=20, description="VAT registration number")
    vat_registered: Optional[bool] = Field(None, description="VAT registration status")


@router.get("/profile")
async def get_tax_profile(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Return comprehensive tax profile summary including classification and benefits."""
    try:
        tax_service = TaxProfileService(db)
        return tax_service.get_tax_summary(current_user_id)
    except Exception as e:
        logger.exception("Failed to fetch tax profile summary")
        raise HTTPException(status_code=500, detail="Failed to fetch tax profile") from e


@router.post("/profile")
async def update_tax_profile(
    data: TaxProfileUpdate,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Update tax profile and return updated classification & rates."""
    try:
        tax_service = TaxProfileService(db)
        profile = tax_service.update_profile(
            user_id=current_user_id,
            annual_turnover=data.annual_turnover,
            fixed_assets=data.fixed_assets,
            tin=data.tin,
            vat_registration_number=data.vat_registration_number,
            vat_registered=data.vat_registered
        )
        tax_profile_updated()
        return {
            "message": "Tax profile updated successfully",
            "summary": tax_service.get_tax_summary(current_user_id)
        }
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as e:
        logger.exception("Failed to update tax profile")
        raise HTTPException(status_code=500, detail="Failed to update tax profile") from e


@router.get("/small-business-check")
async def small_business_check(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Return small business eligibility, remaining thresholds and benefits (unified service)."""
    try:
        tax_service = TaxProfileService(db)
        return tax_service.check_small_business_eligibility(current_user_id)
    except Exception as e:
        logger.exception("Failed small business eligibility check")
        raise HTTPException(status_code=500, detail="Failed small business check") from e


@router.get("/compliance")
async def tax_compliance(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Return tax compliance summary (TIN/VAT/NRS registration status & next actions)."""
    try:
        tax_service = TaxProfileService(db)
        summary = tax_service.get_compliance_summary(current_user_id)
        tax_service.update_compliance_check(current_user_id)
        compliance_check_record()
        return summary
    except Exception as e:
        logger.exception("Failed tax compliance summary")
        raise HTTPException(status_code=500, detail="Failed compliance summary") from e


class FiscalizationStatus(BaseModel):
    """Accreditation / fiscalization readiness status response."""
    accredited: bool
    generated_count: int
    pending_external_count: int
    timestamp: str


@router.get("/config")
async def tax_config(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Expose tax constants for frontend (thresholds, rates)."""
    try:
        service = TaxProfileService(db)
        return service.get_tax_constants()
    except Exception as e:
        logger.exception("Failed to fetch tax config")
        raise HTTPException(status_code=500, detail="Failed tax config") from e


class DevelopmentLevyResponse(BaseModel):
    """Development levy computation response."""
    user_id: int
    business_size: str
    is_small_business: bool
    assessable_profit: float
    levy_rate_percent: float
    levy_applicable: bool
    levy_amount: float
    exemption_reason: str | None
    period: str | None = None
    source: str | None = None

class AlertEventOut(BaseModel):
    id: int
    category: str
    severity: str
    message: str
    created_at: str | None
    model_config = dict(from_attributes=True)


@router.get("/fiscalization/status", response_model=FiscalizationStatus)
async def get_fiscalization_status(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Return provisional fiscalization readiness metrics.

    - accredited: Whether external gateway accreditation flag is enabled (FIRS readiness)
    - generated_count: Number of invoices with provisional fiscal data (QR/code) generated internally
    - pending_external_count: Number of fiscalized invoices not yet transmitted externally (always all until accredited)
    - timestamp: UTC ISO8601 timestamp of status generation
    """
    try:
        # Accreditation flag from config (fallback False if missing)
        from app.core.config import settings  # local import to avoid circulars
        accredited = bool(getattr(settings, "FISCALIZATION_ACCREDITED", False))

        # Count fiscalized invoices
        from app.models.tax_models import FiscalInvoice
        from app.models.models import Invoice

        generated_count = db.query(FiscalInvoice).join(Invoice).filter(Invoice.issuer_id == current_user_id).count()
        # Pending external = all generated if not accredited; else those without transmitted_at
        pending_external_count = db.query(FiscalInvoice).join(Invoice).filter(
            Invoice.issuer_id == current_user_id,
            ~FiscalInvoice.transmitted_at.isnot(None)  # transmitted_at is NULL
        ).count()

        return FiscalizationStatus(
            accredited=accredited,
            generated_count=generated_count,
            pending_external_count=pending_external_count if accredited else generated_count,
            timestamp=datetime.utcnow().isoformat() + "Z",
        )
    except Exception as e:
        logger.exception("Failed fiscalization status")
        raise HTTPException(status_code=500, detail="Failed fiscalization status") from e


@router.get("/levy", response_model=DevelopmentLevyResponse)
async def development_levy(
    profit: float | None = Query(None, ge=0, description="Override assessable profit base (Naira)"),
    year: int | None = Query(None, ge=2024, le=2030, description="Year for profit computation"),
    month: int | None = Query(None, ge=1, le=12, description="Month for profit computation (1-12)"),
    basis: str = Query("paid", pattern="^(paid|all)$", description="Profit basis: paid or all"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Compute development levy (4% for non-small businesses).

    If profit override not provided, compute from PAID invoices for optional period.
    """
    try:
        tax_service = TaxProfileService(db)
        # Auto compute profit from paid invoices if not provided
        computed_profit = None
        source = "override"
        if profit is None:
            computed_profit = tax_service.compute_assessable_profit(
                current_user_id,
                year=year,
                month=month,
                basis=basis,
            )
            profit_to_use = computed_profit
            source = f"{basis}_invoices"
        else:
            profit_to_use = Decimal(str(profit))
        result = tax_service.compute_development_levy(current_user_id, profit_to_use)
        period = f"{year:04d}-{month:02d}" if year and month else None
        result["period"] = period
        result["source"] = source
        return DevelopmentLevyResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed development levy calculation")
        raise HTTPException(status_code=500, detail="Failed levy calculation") from e


@router.post("/reports/generate", response_model=dict)
def generate_monthly_tax_report(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    basis: str = Query("paid", pattern="^(paid|all)$"),
    force: bool = Query(False),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    service = TaxProfileService(db)
    report = service.generate_monthly_report(current_user_id, year, month, basis=basis, force_regenerate=force)
    return {
        "year": report.year,
        "month": report.month,
        "assessable_profit": float(report.assessable_profit or 0),
        "levy_amount": float(report.levy_amount or 0),
        "vat_collected": float(report.vat_collected or 0),
        "taxable_sales": float(report.taxable_sales or 0),
        "zero_rated_sales": float(report.zero_rated_sales or 0),
        "exempt_sales": float(report.exempt_sales or 0),
        "pdf_url": report.pdf_url,
        "basis": basis,
    }

@router.get("/admin/alerts", response_model=list[AlertEventOut])
def list_recent_alerts(
    limit: int = Query(50, ge=1, le=200),
    category: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """Return recent alert events (temporary: all authenticated users).

    Future enhancement: restrict to admin roles.
    """
    try:
        from app.models.alert_models import AlertEvent
    except Exception:
        raise HTTPException(status_code=500, detail="Alert model unavailable")
    q = db.query(AlertEvent).order_by(AlertEvent.created_at.desc())
    if category:
        q = q.filter(AlertEvent.category == category)
    records = q.limit(limit).all()
    return [
        AlertEventOut(
            id=r.id,
            category=r.category,
            severity=r.severity,
            message=r.message,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in records
    ]


@router.get("/reports/{year}/{month}/download")
def download_monthly_tax_report(
    year: int,
    month: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    report = db.query(MonthlyTaxReport).filter(
        MonthlyTaxReport.user_id == current_user_id,
        MonthlyTaxReport.year == year,
        MonthlyTaxReport.month == month,
    ).first()
    if not report or not report.pdf_url:
        raise HTTPException(status_code=404, detail="Report or PDF not found. Generate first.")
    return {"pdf_url": report.pdf_url}

@router.get("/reports/{year}/{month}/csv")
def download_monthly_tax_report_csv(
    year: int,
    month: int,
    basis: str = Query("paid", pattern="^(paid|all)$"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Generate (on-demand) CSV export for a monthly tax report.

    Unlike the PDF (which may be pre-generated & cached), CSV is generated fresh to reflect
    any recent changes (e.g., refunds). It excludes refunded invoices similarly to the PDF.
    """
    from io import StringIO
    from app.storage.s3_client import s3_client
    report = db.query(MonthlyTaxReport).filter(
        MonthlyTaxReport.user_id == current_user_id,
        MonthlyTaxReport.year == year,
        MonthlyTaxReport.month == month,
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found. Generate first.")
    # Recompute profit & VAT if basis provided (keeps CSV consistent with chosen basis)
    service = TaxProfileService(db)
    refreshed = service.generate_monthly_report(current_user_id, year, month, basis=basis, force_regenerate=True)
    buf = StringIO()
    headers = [
        "year","month","basis","assessable_profit","levy_amount","vat_collected",
        "taxable_sales","zero_rated_sales","exempt_sales","generated_at"
    ]
    buf.write(",".join(headers) + "\n")
    row = [
        str(refreshed.year),
        f"{refreshed.month:02d}",
        basis,
        f"{float(refreshed.assessable_profit or 0):.2f}",
        f"{float(refreshed.levy_amount or 0):.2f}",
        f"{float(refreshed.vat_collected or 0):.2f}",
        f"{float(refreshed.taxable_sales or 0):.2f}",
        f"{float(refreshed.zero_rated_sales or 0):.2f}",
        f"{float(refreshed.exempt_sales or 0):.2f}",
        (refreshed.generated_at.isoformat() if refreshed.generated_at else ""),
    ]
    buf.write(",".join(row) + "\n")
    data = buf.getvalue().encode("utf-8")
    key = f"tax-reports/{current_user_id}/{year}-{month:02d}-{basis}.csv"
    url = s3_client.upload_bytes(data, key, content_type="text/csv")
    return {"csv_url": url, "basis": basis}


@router.get("/vat/summary")
async def get_vat_summary(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Get VAT summary and compliance status.
    
    Returns:
    - Current month VAT calculations
    - Recent VAT returns (last 3 months)
    - Compliance status
    - Next recommended action
    """
    try:
        vat_service = VATService(db)
        summary = vat_service.get_vat_summary(current_user_id)
        vat_calculation_record()
        return summary
    except Exception as e:
        logger.error(f"Error fetching VAT summary: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch VAT summary")


@router.get("/vat/calculate")
async def calculate_vat(
    amount: float = Query(..., gt=0, description="Amount in Naira"),
    category: str = Query("standard", description="VAT category: standard, zero_rated, exempt, export")
):
    """
    Calculate VAT for an amount.
    
    Categories:
    - standard: 7.5% VAT
    - zero_rated: 0% VAT (medical, education, basic food)
    - exempt: No VAT (financial services)
    - export: 0% VAT (exports)
    
    Example:
        GET /tax/vat/calculate?amount=10000&category=standard
        Returns: {"subtotal": 9302.33, "vat_rate": 7.5, "vat_amount": 697.67, "total": 10000}
    """
    try:
        result = VATCalculator.calculate(Decimal(str(amount)), category)
        vat_calculation_record()
        return {
            "subtotal": float(result["subtotal"]),
            "vat_rate": float(result["vat_rate"]),
            "vat_amount": float(result["vat_amount"]),
            "total": float(result["total"]),
            "category": category
        }
    except Exception as e:
        logger.error(f"Error calculating VAT: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid VAT calculation parameters")


@router.post("/vat/return")
async def generate_vat_return(
    year: int = Query(..., ge=2024, le=2030, description="Year"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Generate VAT return for a specific month.
    
    Calculates:
    - Output VAT (collected from customers)
    - Input VAT (paid to suppliers)
    - Net VAT payable
    - Zero-rated and exempt sales
    
    Example:
        POST /tax/vat/return?year=2026&month=1
    """
    try:
        vat_service = VATService(db)
        vat_return = vat_service.generate_vat_return(current_user_id, year, month)
        
        return {
            "tax_period": vat_return.tax_period,
            "output_vat": float(vat_return.output_vat),
            "input_vat": float(vat_return.input_vat),
            "net_vat": float(vat_return.net_vat),
            "zero_rated_sales": float(vat_return.zero_rated_sales),
            "exempt_sales": float(vat_return.exempt_sales),
            "total_invoices": vat_return.total_invoices,
            "fiscalized_invoices": vat_return.fiscalized_invoices,
            "status": vat_return.status,
            "message": "VAT return generated successfully"
        }
    except Exception as e:
        logger.error(f"Error generating VAT return: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate VAT return")


@router.post("/invoice/{invoice_id}/fiscalize")
async def fiscalize_invoice(
    invoice_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Fiscalize an invoice (provisional FIRS readiness).
    
    Process:
    1. Generate unique fiscal code
    2. Create digital signature
    3. Generate QR code
    4. Optionally attempt external transmission (only if accredited & configured)
    
    Returns fiscal data including QR code (truncated) for display/printing.
    """
    try:
        # Verify invoice ownership
        invoice = db.query(Invoice).filter(
            Invoice.id == invoice_id,
            Invoice.issuer_id == current_user_id
        ).first()
        
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")
        
        if invoice.is_fiscalized:
            return {
                "message": "Invoice already fiscalized",
                "fiscal_code": invoice.fiscal_code,
                "status": "already_fiscalized"
            }
        
        # Fiscalize invoice
        fiscal_service = FiscalizationService(db)
        fiscal_data = await fiscal_service.fiscalize_invoice(invoice_id)
        
        return {
            "message": "Invoice fiscalized successfully",
            "fiscal_code": fiscal_data.fiscal_code,
            "fiscal_signature": fiscal_data.fiscal_signature[:32] + "...",  # Truncated
            "qr_code": fiscal_data.qr_code_data[:100] + "...",  # Truncated
            "vat_breakdown": {
                "subtotal": float(fiscal_data.subtotal),
                "vat_rate": fiscal_data.vat_rate,
                "vat_amount": float(fiscal_data.vat_amount),
                "total": float(fiscal_data.total_amount)
            },
            "fiscalization_status": fiscal_data.firs_validation_status,
            "fiscalization_transaction_id": fiscal_data.firs_transaction_id
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error fiscalizing invoice: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fiscalize invoice")
