"""Subscription management and Paystack payment integration."""
import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.core.config import settings
from app.db.session import get_db
from app.models import models, schemas

logger = logging.getLogger(__name__)
router = APIRouter()


PLAN_PRICES = {
    "FREE": 0,
    "STARTER": 2500,  # ₦2,500/month
    "PRO": 7500,       # ₦7,500/month
    "BUSINESS": 15000, # ₦15,000/month
    "ENTERPRISE": 50000, # ₦50,000/month
}


@router.post("/initialize")
async def initialize_subscription_payment(
    plan: str,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Initialize Paystack payment for subscription upgrade.
    
    **Flow:**
    1. User selects plan (STARTER/PRO/BUSINESS/ENTERPRISE)
    2. We generate Paystack payment link
    3. User pays via Paystack
    4. Webhook confirms payment
    5. We upgrade user's plan automatically
    
    **Parameters:**
    - plan: Target subscription plan (FREE not allowed - it's default)
    
    **Returns:**
    - authorization_url: Paystack checkout URL
    - reference: Payment reference for tracking
    - amount: Amount in kobo (₦ x 100)
    """
    # Validate plan
    plan = plan.upper()
    if plan not in PLAN_PRICES:
        raise HTTPException(status_code=400, detail=f"Invalid plan. Choose: {list(PLAN_PRICES.keys())}")
    
    if plan == "FREE":
        raise HTTPException(status_code=400, detail="Cannot upgrade to FREE plan. Already default.")
    
    # Get user
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if already on this plan
    if user.plan.value.upper() == plan:
        raise HTTPException(status_code=400, detail=f"Already subscribed to {plan} plan")
    
    # Get price
    amount_naira = PLAN_PRICES[plan]
    amount_kobo = amount_naira * 100  # Paystack uses kobo (smallest unit)
    
    # Generate unique reference
    reference = f"SUB-{current_user_id}-{plan}-{int(user.created_at.timestamp())}"
    
    # Initialize Paystack transaction
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.paystack.co/transaction/initialize",
                headers={
                    "Authorization": f"Bearer {settings.PAYSTACK_SECRET}",
                    "Content-Type": "application/json",
                },
                json={
                    "email": f"{user.phone}@suoops.com",  # Paystack requires email
                    "amount": amount_kobo,
                    "reference": reference,
                    "callback_url": f"{settings.FRONTEND_URL}/dashboard/subscription/success",
                    "metadata": {
                        "user_id": current_user_id,
                        "plan": plan,
                        "phone": user.phone,
                        "custom_fields": [
                            {
                                "display_name": "Plan",
                                "variable_name": "plan",
                                "value": plan,
                            },
                            {
                                "display_name": "Phone",
                                "variable_name": "phone",
                                "value": user.phone,
                            },
                        ],
                    },
                },
                timeout=10.0,
            )
            
            if response.status_code != 200:
                logger.error(f"Paystack initialization failed: {response.text}")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to initialize payment. Please try again."
                )
            
            data = response.json()
            
            if not data.get("status"):
                raise HTTPException(
                    status_code=500,
                    detail=data.get("message", "Payment initialization failed")
                )
            
            payment_data = data["data"]
            
            logger.info(f"Initialized subscription payment for user {current_user_id}: {plan} - {reference}")
            
            return {
                "authorization_url": payment_data["authorization_url"],
                "access_code": payment_data["access_code"],
                "reference": payment_data["reference"],
                "amount": amount_naira,
                "plan": plan,
            }
            
    except httpx.RequestError as e:
        logger.error(f"Paystack request error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Payment service unavailable. Please try again later."
        )


@router.get("/verify/{reference}")
async def verify_subscription_payment(
    reference: str,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Verify Paystack payment status.
    
    Called by frontend after user returns from Paystack checkout.
    If payment successful, upgrade plan immediately.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.paystack.co/transaction/verify/{reference}",
                headers={
                    "Authorization": f"Bearer {settings.PAYSTACK_SECRET}",
                },
                timeout=10.0,
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Payment verification failed")
            
            data = response.json()
            
            if not data.get("status"):
                raise HTTPException(status_code=400, detail="Invalid payment reference")
            
            payment = data["data"]
            
            # Check if payment was successful
            if payment["status"] != "success":
                return {
                    "status": payment["status"],
                    "message": "Payment not completed yet"
                }
            
            # Extract plan from metadata
            metadata = payment.get("metadata", {})
            plan = metadata.get("plan")
            user_id = metadata.get("user_id")
            
            # Verify user ID matches
            if user_id != current_user_id:
                raise HTTPException(status_code=403, detail="Payment reference does not belong to you")
            
            # Upgrade user's plan
            user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            old_plan = user.plan.value
            user.plan = models.SubscriptionPlan[plan]
            db.commit()
            
            logger.info(f"Upgraded user {current_user_id} from {old_plan} to {plan}")
            
            return {
                "status": "success",
                "message": f"Successfully upgraded to {plan} plan!",
                "old_plan": old_plan,
                "new_plan": plan,
                "amount_paid": payment["amount"] / 100,  # Convert kobo to naira
            }
            
    except httpx.RequestError as e:
        logger.error(f"Paystack verification error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Payment verification unavailable. Please contact support."
        )
