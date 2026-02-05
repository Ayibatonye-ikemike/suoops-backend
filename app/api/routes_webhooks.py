import hashlib
import hmac
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.rate_limit import RATE_LIMITS, limiter
from app.core.config import settings
from app.db.session import get_db
from app.models import models
from app.queue import whatsapp_queue

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/whatsapp")
@limiter.limit(RATE_LIMITS["webhook_whatsapp_verify"])
async def verify_whatsapp_webhook(
    request: Request,
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Webhook verification endpoint for WhatsApp Business API"""
    verify_token = getattr(settings, "WHATSAPP_VERIFY_TOKEN", "suoops_verify_2025")
    
    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        return PlainTextResponse(hub_challenge)
    
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp")
@limiter.limit(RATE_LIMITS["webhook_whatsapp_inbound"])
async def whatsapp_webhook(request: Request):
    """Handle incoming WhatsApp messages.
    
    Messages are enqueued for async processing via Celery worker.
    """
    payload = await request.json()
    # enqueue for async processing via Celery worker
    whatsapp_queue.enqueue_message(payload)
    return {"ok": True, "queued": True}


def _record_webhook(db: Session, provider: str, external_id: str, signature: str | None) -> bool:
    existing = (
        db.query(models.WebhookEvent)
        .filter(models.WebhookEvent.provider == provider, models.WebhookEvent.external_id == external_id)
        .one_or_none()
    )
    if existing:
        return True
    event = models.WebhookEvent(provider=provider, external_id=external_id, signature=signature)
    db.add(event)
    return False


def _handle_paystack_subscription(payload: dict, db: Session, signature: str | None) -> dict:
    """Handle Paystack subscription and charge events for recurring billing."""
    event_type = (payload.get("event") or "").lower()
    data = payload.get("data") or {}
    
    # Get reference - could be transaction reference or subscription code
    reference = data.get("reference") or data.get("subscription_code") or data.get("id")
    subscription_code = data.get("subscription_code")
    
    # For subscription.create events, get subscription code from data
    if event_type == "subscription.create":
        subscription_code = data.get("subscription_code")
        reference = subscription_code
    
    duplicate = False
    if reference:
        duplicate = _record_webhook(db, "paystack:subscription", f"{event_type}:{reference}", signature)
        if duplicate:
            logger.info("Paystack subscription webhook duplicate for %s:%s", event_type, reference)
            return {"status": "duplicate", "reference": reference}

    # Handle different subscription events
    if event_type == "subscription.create":
        # New subscription created - store subscription code
        return _handle_subscription_created(data, db)
    elif event_type == "subscription.disable":
        # Subscription cancelled
        return _handle_subscription_disabled(data, db)
    elif event_type == "subscription.not_renew":
        # Subscription won't renew (user requested cancellation)
        return _handle_subscription_not_renew(data, db)
    elif event_type == "invoice.payment_failed":
        # Recurring payment failed
        return _handle_invoice_payment_failed(data, db)
    elif event_type == "charge.success":
        # Successful payment (initial or recurring)
        return _handle_charge_success(data, db)
    else:
        db.commit()
        return {"status": "ignored", "event": event_type}


def _handle_subscription_created(data: dict, db: Session) -> dict:
    """Handle subscription.create event - user successfully subscribed."""
    subscription_code = data.get("subscription_code")
    customer = data.get("customer") or {}
    customer_email = customer.get("email")
    plan = data.get("plan") or {}
    plan_name = plan.get("name", "").upper()
    
    # Map plan name to our plan enum
    if "PRO" in plan_name:
        target_plan = "PRO"
    elif "BUSINESS" in plan_name:
        target_plan = "BUSINESS"
    else:
        logger.warning("Unknown plan in subscription.create: %s", plan_name)
        db.commit()
        return {"status": "error", "message": f"Unknown plan: {plan_name}"}
    
    # Find user by email
    user = db.query(models.User).filter(
        (models.User.email == customer_email) | 
        (models.User.email == customer_email.lower())
    ).first()
    
    if not user:
        logger.error("Subscription created but user not found: %s", customer_email)
        db.commit()
        return {"status": "error", "message": "User not found"}
    
    # Store subscription code on user (we'll add this field)
    if hasattr(user, 'paystack_subscription_code'):
        user.paystack_subscription_code = subscription_code
    if hasattr(user, 'paystack_customer_code'):
        user.paystack_customer_code = customer.get("customer_code")
    
    db.commit()
    
    logger.info(
        "✅ Subscription created: user %s, plan %s, subscription_code %s",
        user.id, target_plan, subscription_code
    )
    
    return {
        "status": "success",
        "event": "subscription.create",
        "user_id": user.id,
        "subscription_code": subscription_code,
        "plan": target_plan,
    }


def _handle_charge_success(data: dict, db: Session) -> dict:
    """Handle charge.success event - payment completed (initial or recurring)."""
    reference = data.get("reference")
    metadata = data.get("metadata") or {}
    user_id = metadata.get("user_id")
    plan = metadata.get("plan")
    
    # Check if this is a subscription payment
    subscription_code = data.get("subscription_code")
    is_subscription = subscription_code is not None or metadata.get("subscription_type") == "recurring"
    
    # If no user_id in metadata, try to find by email
    if not user_id:
        customer = data.get("customer") or {}
        customer_email = customer.get("email")
        if customer_email:
            user = db.query(models.User).filter(
                (models.User.email == customer_email) | 
                (models.User.email == customer_email.lower())
            ).first()
            if user:
                user_id = user.id
    
    if not user_id:
        logger.error("Paystack charge.success webhook missing user_id: %s", metadata)
        db.commit()
        return {"status": "error", "message": "Missing user_id"}

    user = db.query(models.User).filter(models.User.id == user_id).one_or_none()
    if not user:
        logger.error("Paystack charge.success webhook user %s not found", user_id)
        db.commit()
        return {"status": "error", "message": "User not found"}

    # Determine plan from metadata or existing subscription
    if not plan:
        # Try to get plan from subscription if available
        if is_subscription and user.plan.value.upper() in ["PRO", "BUSINESS"]:
            plan = user.plan.value.upper()
        else:
            plan = "PRO"  # Default to PRO for subscription charges

    try:
        new_plan = models.SubscriptionPlan[plan.upper()]
    except KeyError:
        logger.error("Paystack charge.success invalid plan '%s'", plan)
        db.commit()
        return {"status": "error", "message": "Invalid plan"}

    old_plan = user.plan.value
    old_balance = getattr(user, 'invoice_balance', 5)
    
    # Update user plan
    user.plan = new_plan
    
    # Store subscription code if available
    if subscription_code and hasattr(user, 'paystack_subscription_code'):
        user.paystack_subscription_code = subscription_code
    
    # Set subscription dates
    from datetime import datetime, timedelta, timezone as tz
    now = datetime.now(tz.utc)
    user.subscription_started_at = now
    user.subscription_expires_at = now + timedelta(days=32)  # ~1 month buffer
    
    # Add invoices included with plan
    invoices_added = new_plan.invoices_included
    if invoices_added > 0 and hasattr(user, 'invoice_balance'):
        user.invoice_balance += invoices_added
        logger.info(
            "Adding %d invoices to user %s balance (now %d)",
            invoices_added, user_id, getattr(user, 'invoice_balance', 0)
        )
    
    # Update payment transaction if exists
    from app.models.payment_models import PaymentStatus, PaymentTransaction
    transaction = (
        db.query(PaymentTransaction)
        .filter(PaymentTransaction.reference == reference)
        .one_or_none()
    )
    if transaction:
        transaction.status = PaymentStatus.SUCCESS
    
    db.commit()

    logger.info(
        "✅ Paystack charge.success: user %s %s -> %s, +%d invoices (ref: %s, subscription: %s)",
        user_id,
        old_plan,
        new_plan.value,
        invoices_added,
        reference,
        "recurring" if is_subscription else "one-time",
    )

    return {
        "status": "success",
        "event": "charge.success",
        "old_plan": old_plan,
        "new_plan": new_plan.value,
        "invoices_added": invoices_added,
        "invoice_balance": getattr(user, 'invoice_balance', old_balance),
        "reference": reference,
        "is_recurring": is_subscription,
    }


def _handle_subscription_disabled(data: dict, db: Session) -> dict:
    """Handle subscription.disable event - subscription cancelled."""
    subscription_code = data.get("subscription_code")
    customer = data.get("customer") or {}
    customer_email = customer.get("email")
    
    user = db.query(models.User).filter(
        (models.User.email == customer_email) | 
        (models.User.email == customer_email.lower())
    ).first()
    
    if user:
        # Clear subscription code but keep plan until expiry
        if hasattr(user, 'paystack_subscription_code'):
            user.paystack_subscription_code = None
        
        db.commit()
        logger.info("Subscription disabled for user %s (keeps plan until expiry)", user.id)
        return {"status": "success", "event": "subscription.disable", "user_id": user.id}
    
    db.commit()
    return {"status": "ignored", "event": "subscription.disable", "reason": "user not found"}


def _handle_subscription_not_renew(data: dict, db: Session) -> dict:
    """Handle subscription.not_renew event - subscription will not auto-renew."""
    subscription_code = data.get("subscription_code")
    customer = data.get("customer") or {}
    customer_email = customer.get("email")
    
    user = db.query(models.User).filter(
        (models.User.email == customer_email) | 
        (models.User.email == customer_email.lower())
    ).first()
    
    if user:
        logger.info("Subscription will not renew for user %s", user.id)
        db.commit()
        return {"status": "success", "event": "subscription.not_renew", "user_id": user.id}
    
    db.commit()
    return {"status": "ignored", "event": "subscription.not_renew", "reason": "user not found"}


def _handle_invoice_payment_failed(data: dict, db: Session) -> dict:
    """Handle invoice.payment_failed event - recurring charge failed."""
    subscription = data.get("subscription") or {}
    subscription_code = subscription.get("subscription_code")
    customer = data.get("customer") or {}
    customer_email = customer.get("email")
    
    user = db.query(models.User).filter(
        (models.User.email == customer_email) | 
        (models.User.email == customer_email.lower())
    ).first()
    
    if user:
        logger.warning(
            "⚠️ Payment failed for user %s subscription %s - Paystack will retry",
            user.id, subscription_code
        )
        # Paystack will retry, so we don't immediately downgrade
        # They handle dunning (retry attempts) automatically
        db.commit()
        return {"status": "success", "event": "invoice.payment_failed", "user_id": user.id}
    
    db.commit()
    return {"status": "ignored", "event": "invoice.payment_failed", "reason": "user not found"}


def _handle_paystack_invoice_pack(payload: dict, db: Session, signature: str | None) -> dict:
    """Handle invoice pack purchase payment confirmation."""
    event_type = (payload.get("event") or "").lower()
    data = payload.get("data") or {}
    reference = data.get("reference")

    if not reference or not reference.startswith("INVPACK-"):
        return {"status": "ignored", "reason": "not invoice pack"}

    duplicate = _record_webhook(db, "paystack:invoice_pack", reference, signature)
    if duplicate:
        logger.info("Paystack invoice pack webhook duplicate for %s", reference)
        return {"status": "duplicate", "reference": reference}

    if event_type != "charge.success":
        db.commit()
        return {"status": "ignored", "event": event_type}

    metadata = data.get("metadata") or {}
    user_id = metadata.get("user_id")
    invoices_to_add = int(metadata.get("invoices_to_add", 100))  # Ensure int from metadata

    if not user_id:
        logger.error("Paystack invoice pack webhook missing user_id: %s", metadata)
        db.commit()
        return {"status": "error", "message": "Missing user_id"}

    user = db.query(models.User).filter(models.User.id == user_id).one_or_none()
    if not user:
        logger.error("Paystack invoice pack webhook user %s not found", user_id)
        db.commit()
        return {"status": "error", "message": "User not found"}

    # Auto-upgrade FREE users to STARTER when they buy invoice packs
    # STARTER unlocks tax features and has no monthly subscription
    old_plan = user.plan.value
    upgraded_to_starter = False
    if user.plan == models.SubscriptionPlan.FREE:
        user.plan = models.SubscriptionPlan.STARTER
        upgraded_to_starter = True
        logger.info(
            "Auto-upgraded user %s from FREE to STARTER (invoice pack purchase)",
            user_id,
        )

    # Add invoices to balance (with safe access)
    old_balance = getattr(user, 'invoice_balance', 5)
    if hasattr(user, 'invoice_balance'):
        user.invoice_balance += invoices_to_add
    
    # Update payment transaction if exists
    from app.models.payment_models import PaymentStatus, PaymentTransaction
    transaction = (
        db.query(PaymentTransaction)
        .filter(PaymentTransaction.reference == reference)
        .one_or_none()
    )
    if transaction:
        transaction.status = PaymentStatus.SUCCESS
    
    db.commit()

    new_balance = getattr(user, 'invoice_balance', old_balance + invoices_to_add)
    logger.info(
        "✅ Invoice pack purchased: user %s added %d invoices (balance: %d → %d) ref: %s%s",
        user_id,
        invoices_to_add,
        old_balance,
        new_balance,
        reference,
        " [upgraded to STARTER]" if upgraded_to_starter else "",
    )

    result = {
        "status": "success",
        "invoices_added": invoices_to_add,
        "new_balance": new_balance,
        "reference": reference,
    }
    
    if upgraded_to_starter:
        result["upgraded_to_starter"] = True
        result["old_plan"] = old_plan
        result["new_plan"] = "STARTER"
    
    return result


@router.post("/paystack")
@limiter.limit(RATE_LIMITS["webhook_paystack"])
async def paystack_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    raw_body = await request.body()
    signature = request.headers.get("x-paystack-signature")
    if not signature:
        logger.warning("Paystack webhook received without signature")
        raise HTTPException(status_code=400, detail="Missing signature")

    expected_signature = hmac.new(
        settings.PAYSTACK_SECRET.encode(),
        raw_body,
        hashlib.sha512,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        logger.warning("Paystack webhook signature verification failed")
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        logger.error("Invalid Paystack webhook payload: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid payload") from exc

    event_type = payload.get("event")
    if not event_type:
        logger.info("Paystack webhook without event payload received; ignoring")
        return {"status": "ignored", "reason": "missing event"}

    # Check reference to determine payment type
    data = payload.get("data") or {}
    reference = data.get("reference") or ""
    
    # Route to appropriate handler based on reference or event type
    if reference.startswith("INVPACK-"):
        return _handle_paystack_invoice_pack(payload, db, signature)
    elif event_type in [
        "subscription.create", 
        "subscription.disable", 
        "subscription.not_renew",
        "invoice.payment_failed",
        "charge.success",
    ]:
        return _handle_paystack_subscription(payload, db, signature)
    else:
        logger.info("Paystack webhook event %s not handled", event_type)
        return {"status": "ignored", "event": event_type}
