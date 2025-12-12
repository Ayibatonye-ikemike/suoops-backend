"""User profile and settings management endpoints."""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.core.cache import cached
from app.db.session import get_db
from app.models import models, schemas
from app.core.encryption import decrypt_value
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
    from app.utils.feature_gate import FeatureGate
    
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Use FeatureGate for accurate monthly count (auto-resets each month)
    # This also checks subscription expiry and downgrades to FREE if expired
    gate = FeatureGate(db, current_user_id)
    monthly_invoice_count = gate.get_monthly_invoice_count()
    
    # Re-fetch user after FeatureGate may have updated plan
    db.refresh(user)

    # If pilot encryption stored encrypted email, attempt decrypt
    email_plain = decrypt_value(user.email) if user.email else None
    return schemas.UserOut(
        id=user.id,
        phone=user.phone,
        phone_verified=user.phone_verified,
        email=email_plain,
        name=user.name,
        plan=user.plan.value,
        invoices_this_month=monthly_invoice_count,  # Use accurate count, not stored field
        logo_url=user.logo_url,
        subscription_expires_at=user.subscription_expires_at,
        subscription_started_at=user.usage_reset_at,  # When current billing cycle started
    )


@router.get("/me/features")
async def get_feature_access(
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
    
    async def _produce():
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
    # Cache per-user feature access for 20s to reduce DB pressure during polling
    return await cached(f"user:{current_user_id}:features", 20, _produce)


"""Logo, phone, and bank endpoints moved to dedicated modules.

Remaining responsibilities:
- Profile retrieval
- Feature access introspection
"""

