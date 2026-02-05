"""Initialize subscription payment endpoint."""
import logging
from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import metrics
from app.api.routes_auth import get_current_user_id
from app.core.config import settings
from app.db.session import get_db
from app.models import models
from app.models.payment_models import PaymentProvider, PaymentStatus, PaymentTransaction
from app.services.payment_providers import calculate_amount_with_paystack_fee

from .constants import PLAN_PRICES, PAYSTACK_PLAN_CODES

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/initialize")
async def initialize_subscription_payment(
    plan: str,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Initialize Paystack recurring subscription for plan upgrade.
    
    **Flow:**
    1. User selects plan (PRO/BUSINESS)
    2. We create/get Paystack customer and initialize subscription
    3. User pays via Paystack checkout
    4. Paystack automatically charges monthly (auto-recurring)
    5. Webhooks handle: subscription.create, charge.success, invoice.payment_failed
    
    **Parameters:**
    - plan: Target subscription plan (FREE/STARTER not allowed)
    
    **Returns:**
    - authorization_url: Paystack checkout URL for subscription
    - reference: Subscription reference for tracking
    """
    # Validate plan
    plan = plan.upper()
    if plan not in PLAN_PRICES:
        raise HTTPException(status_code=400, detail=f"Invalid plan. Choose: {list(PLAN_PRICES.keys())}")
    
    if plan == "FREE":
        raise HTTPException(status_code=400, detail="Cannot upgrade to FREE plan. Already default.")
    
    # STARTER has no monthly subscription fee (pay-per-invoice only)
    if plan == "STARTER":
        raise HTTPException(
            status_code=400, 
            detail="STARTER has no monthly fee. Use the switch-to-starter endpoint or buy invoice packs."
        )
    
    # Check if plan has a Paystack plan code
    if plan not in PAYSTACK_PLAN_CODES:
        raise HTTPException(status_code=400, detail=f"Plan {plan} is not available for subscription yet.")
    
    # Get user
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get user email (required for Paystack subscriptions)
    user_email = user.email or (f"{user.phone}@suoops.com" if user.phone else None)
    if not user_email:
        raise HTTPException(
            status_code=400, 
            detail="No email address found. Please add your email in settings."
        )
    
    # Check if already on this plan with active subscription
    if user.plan.value.upper() == plan:
        # Check if they have an active subscription
        if hasattr(user, 'paystack_subscription_code') and user.paystack_subscription_code:
            raise HTTPException(status_code=400, detail=f"Already subscribed to {plan} plan with active billing")
        # If no active subscription, allow re-subscription
    
    plan_code = PAYSTACK_PLAN_CODES[plan]
    
    # Initialize Paystack subscription
    try:
        async with httpx.AsyncClient() as client:
            # First, create or get customer
            customer_response = await client.post(
                "https://api.paystack.co/customer",
                headers={
                    "Authorization": f"Bearer {settings.PAYSTACK_SECRET}",
                    "Content-Type": "application/json",
                },
                json={
                    "email": user_email,
                    "first_name": user.name.split()[0] if user.name else "",
                    "last_name": " ".join(user.name.split()[1:]) if user.name and len(user.name.split()) > 1 else "",
                    "phone": user.phone,
                    "metadata": {
                        "user_id": current_user_id,
                    },
                },
                timeout=10.0,
            )
            
            if customer_response.status_code not in [200, 201]:
                # Customer may already exist, try to fetch
                customer_response = await client.get(
                    f"https://api.paystack.co/customer/{user_email}",
                    headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET}"},
                    timeout=10.0,
                )
            
            customer_data = customer_response.json()
            customer_code = customer_data.get("data", {}).get("customer_code")
            
            # Initialize subscription transaction
            # This creates a payment page for the subscription
            timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
            reference = f"SUBSCRIP-{current_user_id}-{plan}-{timestamp}"
            
            response = await client.post(
                "https://api.paystack.co/transaction/initialize",
                headers={
                    "Authorization": f"Bearer {settings.PAYSTACK_SECRET}",
                    "Content-Type": "application/json",
                },
                json={
                    "email": user_email,
                    "plan": plan_code,  # This makes it a subscription!
                    "callback_url": f"{settings.FRONTEND_URL}/dashboard/subscription/success",
                    "metadata": {
                        "user_id": current_user_id,
                        "plan": plan,
                        "subscription_type": "recurring",
                        "customer_code": customer_code,
                        "custom_fields": [
                            {
                                "display_name": "Plan",
                                "variable_name": "plan",
                                "value": plan,
                            },
                            {
                                "display_name": "Billing",
                                "variable_name": "billing_type",
                                "value": "Monthly Auto-Recurring",
                            },
                        ],
                    },
                },
                timeout=10.0,
            )
            
            if response.status_code != 200:
                logger.error(f"Paystack subscription initialization failed: {response.text}")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to initialize subscription. Please try again."
                )
            
            data = response.json()
            
            if not data.get("status"):
                raise HTTPException(
                    status_code=500,
                    detail=data.get("message", "Subscription initialization failed")
                )
            
            payment_data = data["data"]
            
            # Save payment transaction to database
            payment_transaction = PaymentTransaction(
                user_id=current_user_id,
                reference=payment_data["reference"],
                amount=PLAN_PRICES[plan] * 100,  # Store in kobo
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
            
            logger.info(f"Initialized recurring subscription for user {current_user_id}: {plan} - {payment_data['reference']}")
            
            return {
                "authorization_url": payment_data["authorization_url"],
                "access_code": payment_data["access_code"],
                "reference": payment_data["reference"],
                "amount": PLAN_PRICES[plan],
                "plan": plan,
                "billing_type": "recurring",
                "message": "You will be charged ₦{:,}/month automatically.".format(PLAN_PRICES[plan]),
            }
            
    except httpx.RequestError as e:
        logger.error(f"Paystack request error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Payment service unavailable. Please try again later."
        )
