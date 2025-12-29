"""User profile and settings management endpoints."""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.core.cache import cached
from app.db.session import get_db
from app.models import models, schemas
from app.core.encryption import decrypt_value
from app.services.otp_service import OTPService
from app.storage.s3_client import s3_client
from app.services.account_deletion_service import AccountDeletionService

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

    # Use FeatureGate for subscription expiry check (downgrades to FREE if expired)
    gate = FeatureGate(db, current_user_id)
    
    # Re-fetch user after FeatureGate may have updated plan
    db.refresh(user)

    # If pilot encryption stored encrypted email, attempt decrypt
    email_plain = decrypt_value(user.email) if user.email else None
    
    # Safely get invoice_balance (may not exist if migration hasn't run)
    invoice_balance = gate.get_invoice_balance()  # Uses safe access internally
    
    return schemas.UserOut(
        id=user.id,
        phone=user.phone,
        phone_verified=user.phone_verified,
        email=email_plain,
        name=user.name,
        plan=user.plan.value,
        invoice_balance=invoice_balance,  # New billing model: available invoices
        invoices_this_month=0,  # Deprecated, kept for backward compat
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


@router.patch("/me", response_model=UpdateProfileResponse)
def update_profile(
    request: UpdateProfileRequest,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Update the current user's profile information.
    
    Currently supports:
    - Name updates
    
    Returns updated profile data.
    """
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update name
    user.name = request.name.strip()
    
    try:
        db.commit()
        db.refresh(user)
        
        return UpdateProfileResponse(
            success=True,
            message="Profile updated successfully",
            name=user.name
        )
    except Exception as e:
        logger.error(f"Profile update failed for user {current_user_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to update profile. Please try again."
        )


class DeleteAccountRequest(BaseModel):
    """Request to delete user account."""
    confirmation: str  # Must be "DELETE MY ACCOUNT" to confirm


class UpdateProfileRequest(BaseModel):
    """Request to update user profile."""
    name: str = Field(..., min_length=1, max_length=120, description="User's full name")


class UpdateProfileResponse(BaseModel):
    """Response after profile update."""
    success: bool
    message: str
    name: str


class DeleteAccountResponse(BaseModel):
    """Response after account deletion."""
    success: bool
    message: str
    deleted_items: dict | None = None


@router.delete("/me", response_model=DeleteAccountResponse)
def delete_own_account(
    request: DeleteAccountRequest,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Delete the current user's account and all associated data.
    
    This action is IRREVERSIBLE. All data including invoices, customers,
    inventory, and settings will be permanently deleted.
    
    Requires confirmation text "DELETE MY ACCOUNT" to proceed.
    """
    # Require explicit confirmation
    if request.confirmation != "DELETE MY ACCOUNT":
        raise HTTPException(
            status_code=400,
            detail="Invalid confirmation. Type 'DELETE MY ACCOUNT' to confirm deletion."
        )
    
    try:
        service = AccountDeletionService(db)
        result = service.delete_account(
            user_id=current_user_id,
            deleted_by_user_id=current_user_id
        )
        
        return DeleteAccountResponse(
            success=True,
            message="Your account has been permanently deleted.",
            deleted_items=result.get("deleted_items")
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Account deletion failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to delete account. Please contact support."
        )


@router.delete("/admin/{user_id}", response_model=DeleteAccountResponse)
def admin_delete_account(
    user_id: int,
    request: DeleteAccountRequest,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Admin endpoint to delete any user account.
    
    Requires admin role and confirmation text "DELETE MY ACCOUNT".
    """
    # Check admin permission
    service = AccountDeletionService(db)
    can_delete, reason = service.can_delete_account(current_user_id, user_id)
    
    if not can_delete:
        raise HTTPException(status_code=403, detail=reason)
    
    # Require explicit confirmation
    if request.confirmation != "DELETE MY ACCOUNT":
        raise HTTPException(
            status_code=400,
            detail="Invalid confirmation. Type 'DELETE MY ACCOUNT' to confirm deletion."
        )
    
    try:
        result = service.delete_account(
            user_id=user_id,
            deleted_by_user_id=current_user_id
        )
        
        return DeleteAccountResponse(
            success=True,
            message=f"Account {user_id} has been permanently deleted.",
            deleted_items=result.get("deleted_items")
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Admin account deletion failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to delete account. Please check logs."
        )


"""Logo, phone, and bank endpoints moved to dedicated modules.

Remaining responsibilities:
- Profile retrieval
- Feature access introspection
"""

