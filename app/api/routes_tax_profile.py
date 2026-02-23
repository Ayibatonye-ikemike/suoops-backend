"""Tax profile & small business endpoints split from routes_tax.py for modularity.
Requires STARTER or PRO plan for access.
"""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.db.session import get_db
from app.services.tax_service import TaxProfileService
from app.utils.feature_gate import require_plan_feature

router = APIRouter(prefix="/tax", tags=["tax-profile"])


class TaxProfileUpdate(BaseModel):
    annual_turnover: Optional[Decimal] = Field(None, ge=0)
    fixed_assets: Optional[Decimal] = Field(None, ge=0)
    tin: Optional[str] = Field(None, max_length=20)
    vat_registration_number: Optional[str] = Field(None, max_length=20)
    vat_registered: Optional[bool] = None
    business_type: Optional[str] = Field(None, pattern="^(goods|services|mixed)$")
    vat_apply_to: Optional[str] = Field(None, pattern="^(all|selected)$")
    withholding_vat_applies: Optional[bool] = None


@router.get("/profile")
def get_tax_profile(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Get user's tax profile. Requires STARTER or PRO plan."""
    require_plan_feature(db, current_user_id, "tax_reports", "Tax Reports")
    try:
        service = TaxProfileService(db)
        return service.get_tax_summary(current_user_id)
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail="Failed to fetch tax profile") from e


@router.post("/profile")
def update_tax_profile(
    data: TaxProfileUpdate,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Update user's tax profile. Requires STARTER or PRO plan."""
    require_plan_feature(db, current_user_id, "tax_reports", "Tax Reports")
    try:
        service = TaxProfileService(db)
        service.update_profile(
            user_id=current_user_id,
            annual_turnover=data.annual_turnover,
            fixed_assets=data.fixed_assets,
            tin=data.tin,
            vat_registration_number=data.vat_registration_number,
            vat_registered=data.vat_registered,
            business_type=data.business_type,
            vat_apply_to=data.vat_apply_to,
            withholding_vat_applies=data.withholding_vat_applies,
        )
        return {"message": "Tax profile updated successfully", "summary": service.get_tax_summary(current_user_id)}
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail="Failed to update tax profile") from e


@router.get("/small-business-check")
def small_business_check(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Check small business eligibility. Requires STARTER or PRO plan."""
    require_plan_feature(db, current_user_id, "tax_reports", "Tax Reports")
    try:
        service = TaxProfileService(db)
        return service.check_small_business_eligibility(current_user_id)
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail="Failed small business check") from e


@router.get("/compliance")
def tax_compliance(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Get tax compliance summary. Requires STARTER or PRO plan."""
    require_plan_feature(db, current_user_id, "tax_reports", "Tax Reports")
    try:
        service = TaxProfileService(db)
        summary = service.get_compliance_summary(current_user_id)
        service.update_compliance_check(current_user_id)
        return summary
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail="Failed compliance summary") from e
