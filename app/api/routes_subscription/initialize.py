"""Initialize subscription payment endpoint."""
import logging
from datetime import datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.core.config import settings
from app.db.session import get_db
from app.models import models
from app.models.payment_models import PaymentTransaction, PaymentStatus, PaymentProvider
from app import metrics

from .constants import PLAN_PRICES

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/initialize")
async def initialize_subscription_payment(
    plan: str,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Initialize Paystack payment for subscription upgrade.
    
    **Flow:**
    1. User selects plan (STARTER/PRO/BUSINESS)
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
    
    # STARTER has no monthly subscription fee (pay-per-invoice only)
    # Use /subscriptions/switch-to-starter endpoint instead
    if plan == "STARTER":
        raise HTTPException(
            status_code=400, 
            detail="STARTER has no monthly fee. Use the switch-to-starter endpoint or buy invoice packs."
        )
    
    # Get user
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get user email (prefer actual email, fallback to phone-based email)
    user_email = user.email or (f"{user.phone}@suoops.com" if user.phone else None)
    if not user_email:
        raise HTTPException(
            status_code=400, 
            detail="No email address found. Please add your email in settings."
        )
    
    # Check if already on this plan
    if user.plan.value.upper() == plan:
        raise HTTPException(status_code=400, detail=f"Already subscribed to {plan} plan")
    
    # Get price
    amount_naira = PLAN_PRICES[plan]
    amount_kobo = amount_naira * 100  # Paystack uses kobo (smallest unit)
    
    # Generate unique reference with current timestamp to avoid duplicates
    timestamp = int(datetime.utcnow().timestamp() * 1000)  # milliseconds for uniqueness
    reference = f"SUB-{current_user_id}-{plan}-{timestamp}"
    
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
                    "email": user_email,
                    "amount": amount_kobo,
                    "reference": reference,
                    "callback_url": f"{settings.FRONTEND_URL}/dashboard/subscription/success",
                    "metadata": {
                        "user_id": current_user_id,
                        "plan": plan,
                        "email": user_email,
                        "phone": user.phone,
                        "custom_fields": [
                            {
                                "display_name": "Plan",
                                "variable_name": "plan",
                                "value": plan,
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
            
            # Save payment transaction to database
            payment_transaction = PaymentTransaction(
                user_id=current_user_id,
                reference=reference,
                amount=amount_kobo,
                currency="NGN",
                plan_before=user.plan.value,
                plan_after=plan.lower(),
                status=PaymentStatus.PENDING,
                provider=PaymentProvider.PAYSTACK,
                paystack_authorization_url=payment_data["authorization_url"],
                paystack_access_code=payment_data["access_code"],
                customer_email=user_email,
                customer_phone=user.phone,
            )
            db.add(payment_transaction)
            db.commit()
            
            # Record metrics
            metrics.subscription_payment_initiated(plan.lower())
            
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
