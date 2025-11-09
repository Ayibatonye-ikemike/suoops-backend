"""User profile and settings management endpoints."""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.db.session import get_db
from app.models import models, schemas
from app.services.otp_service import OTPService
from app.storage.s3_client import s3_client

logger = logging.getLogger(__name__)
router = APIRouter()
otp_service = OTPService()



@router.get("/me", response_model=schemas.UserOut)
def get_profile(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """Return current user's core profile and subscription details."""
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return schemas.UserOut(
        id=user.id,
        phone=user.phone,
        email=user.email,
        name=user.name,
        plan=user.plan.value,
        invoices_this_month=user.invoices_this_month,
        logo_url=user.logo_url,
    )


@router.get("/me/features")
def get_feature_access(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Get current user's feature access and subscription limits.
    
    Returns detailed information about:
    - Current subscription plan
    - Monthly invoice usage and limits
    - Premium feature access (OCR, voice, etc)
    - Upgrade options
    """
    from app.utils.feature_gate import FeatureGate
    
    gate = FeatureGate(db, current_user_id)
    user = gate.user
    plan = user.plan
    
    can_create, limit_message = gate.can_create_invoice()
    monthly_count = gate.get_monthly_invoice_count()
    
    return {
        "user_id": user.id,
        "current_plan": plan.value,
        "plan_price": plan.price,
        "is_free_tier": gate.is_free_tier(),
        "features": plan.features,
        "invoice_usage": {
            "used_this_month": monthly_count,
            "limit": plan.invoice_limit,
            "remaining": (plan.invoice_limit - monthly_count) if plan.invoice_limit else None,
            "can_create_more": can_create,
            "limit_message": limit_message,
        },
        "upgrade_available": gate.is_free_tier(),
        "upgrade_url": "/subscription/initialize" if gate.is_free_tier() else None,
    }


"""Logo, phone, and bank endpoints moved to dedicated modules.

Remaining responsibilities:
- Profile retrieval
- Feature access introspection
"""

