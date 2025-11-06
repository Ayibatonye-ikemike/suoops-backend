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
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.api.routes_auth import get_current_user_id
from app.services.tax_profile_service import TaxProfileService
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
    """
    Get user's tax profile and business classification.
    
    Returns:
    - Business size classification (small/medium/large)
    - Applicable tax rates
    - Registration status
    - Tax benefits
    """
    try:
        tax_service = TaxProfileService(db)
        profile = tax_service.get_tax_summary(current_user_id)
        return profile
    except Exception as e:
        logger.error(f"Error fetching tax profile: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch tax profile")


@router.post("/profile")
async def update_tax_profile(
    data: TaxProfileUpdate,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Update tax profile information.
    
    Automatically recalculates business size classification based on:
    - Annual turnover ≤ ₦100M AND assets ≤ ₦250M = Small (tax exempt)
    - Above thresholds = Medium/Large (taxable)
    """
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
        
        return {
            "message": "Tax profile updated successfully",
            "business_size": profile.business_size,
            "is_small_business": profile.is_small_business,
            "tax_rates": profile.tax_rates
        }
    except Exception as e:
        logger.error(f"Error updating tax profile: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update tax profile")


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
    Fiscalize an invoice for NRS compliance.
    
    Process:
    1. Generates unique fiscal code
    2. Creates digital signature
    3. Generates QR code
    4. Transmits to NRS (if configured)
    
    Returns fiscal data including QR code for display/printing.
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
            "fiscal_signature": fiscal_data.fiscal_signature[:32] + "...",  # Truncate for response
            "qr_code": fiscal_data.qr_code_data[:100] + "...",  # Truncate (full data in DB)
            "vat_breakdown": {
                "subtotal": float(fiscal_data.subtotal),
                "vat_rate": fiscal_data.vat_rate,
                "vat_amount": float(fiscal_data.vat_amount),
                "total": float(fiscal_data.total_amount)
            },
            "nrs_status": fiscal_data.nrs_validation_status,
            "nrs_transaction_id": fiscal_data.nrs_transaction_id
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error fiscalizing invoice: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fiscalize invoice")
