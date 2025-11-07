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
            from app.models.models import Invoice
            q = db.query(Invoice).filter(Invoice.issuer_id == current_user_id, Invoice.status == "paid")
            if year and month:
                # Filter by month boundaries (assuming created_at is timezone-aware)
                from datetime import datetime, timezone
                start = datetime(year, month, 1, tzinfo=timezone.utc)
                if month == 12:
                    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
                else:
                    end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
                q = q.filter(Invoice.created_at >= start, Invoice.created_at < end)
            invoices = q.all()
            computed_profit = sum(float(inv.amount) for inv in invoices)
            profit_to_use = Decimal(str(computed_profit))
            source = "paid_invoices"
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
