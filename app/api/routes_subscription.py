"""Subscription management and Paystack payment integration."""
import logging
from datetime import datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.core.rbac import staff_or_admin_required
from app.core.config import settings
from app.db.session import get_db
from app.models import models, schemas
from app.models.payment_models import PaymentTransaction, PaymentStatus, PaymentProvider
from app import metrics

logger = logging.getLogger(__name__)
router = APIRouter()


PLAN_PRICES = {
    "FREE": 0,
    "STARTER": 4500,   # ₦4,500/month - 100 invoices + Tax reports & automation
    "PRO": 8000,       # ₦8,000/month - 200 invoices + Custom logo branding
    "BUSINESS": 16000, # ₦16,000/month - 300 invoices + Voice (15 max) + Photo OCR (15 max) [5% quota]
    "ENTERPRISE": 50000, # ₦50,000/month - LEGACY (not actively sold)
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
            
            # Verify user ID matches (convert to int since metadata comes as string from JSON)
            if int(user_id) != current_user_id:
                raise HTTPException(status_code=403, detail="Payment reference does not belong to you")
            
            # Find payment transaction
            payment_transaction = db.query(PaymentTransaction).filter(
                PaymentTransaction.reference == reference
            ).one_or_none()
            
            if not payment_transaction:
                logger.warning(f"Payment transaction not found for reference: {reference}")
                # Still process the upgrade even if transaction record missing
            
            # Upgrade user's plan
            user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            old_plan = user.plan.value
            user.plan = models.SubscriptionPlan[plan]
            
            # Update payment transaction
            if payment_transaction:
                payment_transaction.status = PaymentStatus.SUCCESS
                payment_transaction.paid_at = datetime.utcnow()
                payment_transaction.paystack_transaction_id = payment.get("id")
                payment_transaction.payment_method = payment.get("channel")
                
                # Extract card/bank details if available
                authorization = payment.get("authorization", {})
                if authorization:
                    payment_transaction.card_last4 = authorization.get("last4")
                    payment_transaction.card_brand = authorization.get("brand")
                    payment_transaction.bank_name = authorization.get("bank")
                
                # Set billing period (30 days from now)
                payment_transaction.billing_start_date = datetime.utcnow()
                payment_transaction.billing_end_date = datetime.utcnow() + dt.timedelta(days=30)
                payment_transaction.payment_metadata = payment.get("metadata")
            
            db.commit()
            
            # Record metrics
            metrics.subscription_payment_success(plan.lower())
            metrics.subscription_upgrade(old_plan, plan.lower())
            
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


@router.get("/history")
async def get_payment_history(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
    status_filter: str | None = None,
):
    """
    Get payment history for the current user.
    
    **Parameters:**
    - limit: Max number of records to return (default: 50, max: 100)
    - offset: Number of records to skip for pagination (default: 0)
    - status_filter: Filter by payment status (pending, success, failed, cancelled, refunded)
    
    **Returns:**
    - payments: List of payment transactions
    - total: Total count of payments matching filter
    - summary: Aggregated stats (total_paid, successful_count, etc.)
    """
    # Validate limit
    limit = min(limit, 100)
    
    # Build query
    query = db.query(PaymentTransaction).filter(
        PaymentTransaction.user_id == current_user_id
    )
    
    # Apply status filter if provided
    if status_filter:
        try:
            status_enum = PaymentStatus(status_filter.lower())
            query = query.filter(PaymentTransaction.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status filter. Choose: pending, success, failed, cancelled, refunded"
            )
    
    # Get total count
    total = query.count()
    
    # Get paginated results, ordered by created_at descending (newest first)
    payments = query.order_by(PaymentTransaction.created_at.desc()).offset(offset).limit(limit).all()
    
    # Calculate summary stats
    successful_payments = db.query(PaymentTransaction).filter(
        PaymentTransaction.user_id == current_user_id,
        PaymentTransaction.status == PaymentStatus.SUCCESS
    ).all()
    
    total_paid_kobo = sum(p.amount for p in successful_payments)
    
    summary = {
        "total_paid": total_paid_kobo / 100,  # Convert to Naira
        "successful_count": len(successful_payments),
        "pending_count": db.query(PaymentTransaction).filter(
            PaymentTransaction.user_id == current_user_id,
            PaymentTransaction.status == PaymentStatus.PENDING
        ).count(),
        "failed_count": db.query(PaymentTransaction).filter(
            PaymentTransaction.user_id == current_user_id,
            PaymentTransaction.status.in_([PaymentStatus.FAILED, PaymentStatus.CANCELLED])
        ).count(),
    }
    
    # Format payments for response
    payments_list = [
        {
            "id": p.id,
            "reference": p.reference,
            "amount": p.amount_naira,
            "currency": p.currency,
            "status": p.status.value,
            "plan_before": p.plan_before,
            "plan_after": p.plan_after,
            "payment_method": p.payment_method,
            "card_last4": p.card_last4,
            "card_brand": p.card_brand,
            "bank_name": p.bank_name,
            "created_at": p.created_at.isoformat(),
            "paid_at": p.paid_at.isoformat() if p.paid_at else None,
            "billing_start_date": p.billing_start_date.isoformat() if p.billing_start_date else None,
            "billing_end_date": p.billing_end_date.isoformat() if p.billing_end_date else None,
            "failure_reason": p.failure_reason,
        }
        for p in payments
    ]
    
    return {
        "payments": payments_list,
        "total": total,
        "limit": limit,
        "offset": offset,
        "summary": summary,
    }


@router.get("/history/{payment_id}")
async def get_payment_detail(
    payment_id: int,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Get detailed information about a specific payment transaction.
    
    Includes full metadata from Paystack webhook.
    """
    payment = db.query(PaymentTransaction).filter(
        PaymentTransaction.id == payment_id,
        PaymentTransaction.user_id == current_user_id,  # Ensure user owns this payment
    ).one_or_none()
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    return {
        "id": payment.id,
        "reference": payment.reference,
        "amount": payment.amount_naira,
        "currency": payment.currency,
        "status": payment.status.value,
        "provider": payment.provider.value,
        "plan_before": payment.plan_before,
        "plan_after": payment.plan_after,
        "payment_method": payment.payment_method,
        "card_last4": payment.card_last4,
        "card_brand": payment.card_brand,
        "bank_name": payment.bank_name,
        "customer_email": payment.customer_email,
        "customer_phone": payment.customer_phone,
        "paystack_transaction_id": payment.paystack_transaction_id,
        "created_at": payment.created_at.isoformat(),
        "updated_at": payment.updated_at.isoformat(),
        "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
        "billing_start_date": payment.billing_start_date.isoformat() if payment.billing_start_date else None,
        "billing_end_date": payment.billing_end_date.isoformat() if payment.billing_end_date else None,
        "failure_reason": payment.failure_reason,
        "metadata": payment.payment_metadata,
        "ip_address": payment.ip_address,
    }
