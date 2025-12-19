import hashlib
import hmac
import json
import logging
from typing import Annotated, TypeAlias

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.api.rate_limit import limiter, RATE_LIMITS
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
    event_type = (payload.get("event") or "").lower()
    data = payload.get("data") or {}
    reference = data.get("reference") or data.get("id") or data.get("subscription_code")

    duplicate = False
    if reference:
        duplicate = _record_webhook(db, "paystack:subscription", reference, signature)
        if duplicate:
            logger.info("Paystack subscription webhook duplicate for %s", reference)
            return {"status": "duplicate", "reference": reference}

    if event_type != "charge.success":
        db.commit()
        return {"status": "ignored", "event": event_type}

    metadata = data.get("metadata") or {}
    user_id = metadata.get("user_id")
    plan = metadata.get("plan")

    if not user_id or not plan:
        logger.error("Paystack subscription webhook missing metadata: %s", metadata)
        db.commit()
        return {"status": "error", "message": "Missing metadata"}

    user = db.query(models.User).filter(models.User.id == user_id).one_or_none()
    if not user:
        logger.error("Paystack subscription webhook user %s not found", user_id)
        db.commit()
        return {"status": "error", "message": "User not found"}

    try:
        new_plan = models.SubscriptionPlan[plan.upper()]
    except KeyError:
        logger.error("Paystack subscription webhook invalid plan '%s'", plan)
        db.commit()
        return {"status": "error", "message": "Invalid plan"}

    old_plan = user.plan.value
    old_balance = getattr(user, 'invoice_balance', 5)
    user.plan = new_plan
    
    # Pro and Business plans include 100 invoices with subscription
    invoices_added = new_plan.invoices_included
    if invoices_added > 0 and hasattr(user, 'invoice_balance'):
        user.invoice_balance += invoices_added
        logger.info(
            "Adding %d invoices to user %s balance (now %d)",
            invoices_added, user_id, getattr(user, 'invoice_balance', 0)
        )
    
    db.commit()

    logger.info(
        "✅ Paystack subscription: user %s %s -> %s, +%d invoices (ref: %s)",
        user_id,
        old_plan,
        new_plan.value,
        invoices_added,
        reference,
    )

    return {
        "status": "success",
        "old_plan": old_plan,
        "new_plan": new_plan.value,
        "invoices_added": invoices_added,
        "invoice_balance": getattr(user, 'invoice_balance', old_balance),
        "reference": reference,
    }


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
    from app.models.payment_models import PaymentTransaction, PaymentStatus
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
    
    if reference.startswith("INVPACK-"):
        return _handle_paystack_invoice_pack(payload, db, signature)
    else:
        return _handle_paystack_subscription(payload, db, signature)
