"""
Referral API routes for managing referral codes, tracking referrals, and claiming rewards.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUserDep, DbDep
from app.services.referral_service import ReferralService


router = APIRouter(prefix="/referrals", tags=["Referrals"])


# ==================== SCHEMAS ====================

class ReferralCodeResponse(BaseModel):
    """Response with user's referral code."""
    code: str
    referral_link: str
    is_active: bool


class ReferralStatsResponse(BaseModel):
    """Referral statistics for a user."""
    referral_code: str
    referral_link: str
    total_referrals: int
    pending_referrals: int
    free_signups: int
    paid_signups: int
    rewards_earned: int
    pending_rewards: int
    pending_rewards_list: list[dict]
    progress: dict


class RecentReferralResponse(BaseModel):
    """Recent referral entry."""
    id: int
    referred_name: str
    type: str
    status: str
    created_at: str
    completed_at: str | None


class ApplyRewardRequest(BaseModel):
    """Request to apply a reward."""
    reward_id: int


class ApplyRewardResponse(BaseModel):
    """Response after applying a reward."""
    success: bool
    message: str


class ValidateCodeRequest(BaseModel):
    """Request to validate a referral code."""
    code: str = Field(..., min_length=6, max_length=20)


class ValidateCodeResponse(BaseModel):
    """Response after validating a referral code."""
    valid: bool
    referrer_name: str | None = None
    error: str | None = None


# ==================== ENDPOINTS ====================

@router.get("/code", response_model=ReferralCodeResponse)
async def get_referral_code(
    user_id: CurrentUserDep,
    db: DbDep,
):
    """
    Get or create the current user's referral code.
    
    Every user gets a unique referral code they can share.
    """
    service = ReferralService(db)
    referral_code = service.get_or_create_referral_code(user_id)
    
    return ReferralCodeResponse(
        code=referral_code.code,
        referral_link=f"https://suoops.ng/register?ref={referral_code.code}",
        is_active=referral_code.is_active,
    )


@router.get("/stats", response_model=ReferralStatsResponse)
async def get_referral_stats(
    user_id: CurrentUserDep,
    db: DbDep,
):
    """
    Get referral statistics for the current user.
    
    Includes:
    - Total referrals (completed)
    - Pending referrals (awaiting verification)
    - Free vs paid signups
    - Rewards earned and pending
    - Progress towards next reward
    """
    service = ReferralService(db)
    stats = service.get_referral_stats(user_id)
    return ReferralStatsResponse(**stats)


@router.get("/recent", response_model=list[RecentReferralResponse])
async def get_recent_referrals(
    user_id: CurrentUserDep,
    db: DbDep,
    limit: int = 10,
):
    """
    Get recent referrals for the current user.
    """
    service = ReferralService(db)
    referrals = service.get_recent_referrals(user_id, limit=min(limit, 50))
    return [RecentReferralResponse(**r) for r in referrals]


@router.post("/apply-reward", response_model=ApplyRewardResponse)
async def apply_reward(
    user_id: CurrentUserDep,
    db: DbDep,
    request: ApplyRewardRequest,
):
    """
    Apply a pending reward to the user's account.
    
    This will:
    - Upgrade user to Starter plan (if on Free)
    - Add 1 month to their subscription
    """
    service = ReferralService(db)
    success, message = service.apply_reward(user_id, request.reward_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )
    
    return ApplyRewardResponse(success=True, message=message)


@router.post("/validate", response_model=ValidateCodeResponse)
async def validate_referral_code(
    db: DbDep,
    request: ValidateCodeRequest,
):
    """
    Validate a referral code (public endpoint for signup form).
    
    This endpoint is used to check if a referral code is valid
    before the user completes registration.
    """
    from sqlalchemy import select
    from app.models.models import User
    from app.models.referral_models import ReferralCode
    
    code = request.code.upper().strip()
    
    # Look up the code
    referral_code = db.execute(
        select(ReferralCode)
        .where(ReferralCode.code == code)
        .where(ReferralCode.is_active == True)
    ).scalar_one_or_none()
    
    if not referral_code:
        return ValidateCodeResponse(
            valid=False,
            error="Invalid referral code",
        )
    
    # Get referrer's name (for display)
    referrer = db.execute(
        select(User).where(User.id == referral_code.user_id)
    ).scalar_one_or_none()
    
    return ValidateCodeResponse(
        valid=True,
        referrer_name=referrer.name if referrer else None,
    )
