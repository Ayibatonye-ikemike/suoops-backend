"""Switch to non-paid plans (like STARTER) without payment."""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.db.session import get_db
from app.models import models

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/switch-to-starter")
async def switch_to_starter(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Switch to STARTER plan (no payment required).
    
    STARTER plan has no monthly subscription fee.
    Users pay per invoice pack (₦2,500 for 100 invoices).
    
    This endpoint is for:
    - FREE users who want tax features without a monthly commitment
    - Users who want to downgrade from PRO/BUSINESS to pay-per-invoice
    
    Note: This does NOT add invoices. Users must purchase invoice packs separately.
    
    **Returns:**
    - message: Success message
    - old_plan: Previous plan
    - new_plan: STARTER
    """
    # Get user
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    old_plan = user.plan.value
    
    # Check if already on STARTER
    if user.plan == models.SubscriptionPlan.STARTER:
        raise HTTPException(status_code=400, detail="Already on STARTER plan")
    
    # Switch to STARTER
    user.plan = models.SubscriptionPlan.STARTER
    
    # Clear subscription expiry since STARTER has no subscription
    user.subscription_expires_at = None
    
    db.commit()
    
    logger.info(f"User {current_user_id} switched from {old_plan} to STARTER")
    
    return {
        "status": "success",
        "message": "Switched to STARTER plan! You can now access tax features. Purchase invoice packs to create invoices.",
        "old_plan": old_plan,
        "new_plan": "STARTER",
    }
