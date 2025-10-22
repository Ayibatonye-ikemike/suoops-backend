from typing import Annotated, TypeAlias

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import logger
from app.db.session import get_db
from app.models import models
from app.queue.whatsapp_queue import enqueue_message

router = APIRouter()


@router.get("/whatsapp")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Webhook verification endpoint for WhatsApp Business API"""
    verify_token = getattr(settings, "WHATSAPP_VERIFY_TOKEN", "suopay_verify_2025")
    
    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        return PlainTextResponse(hub_challenge)
    
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    """Handle incoming WhatsApp messages.
    
    Messages are enqueued for async processing via Celery worker.
    """
    payload = await request.json()
    # enqueue for async processing via Celery worker
    enqueue_message(payload)
    return {"ok": True, "queued": True}


@router.post("/paystack")
async def paystack_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    """
    Handle Paystack webhook events for subscription payments.
    
    **Events handled:**
    - charge.success: Upgrade user's subscription plan
    
    **Security:**
    Verifies webhook signature using Paystack secret key.
    """
    # Get payload
    body = await request.body()
    payload = await request.json()
    
    # Verify webhook signature (Paystack security feature)
    signature = request.headers.get("x-paystack-signature")
    if not signature:
        logger.warning("Paystack webhook received without signature")
        raise HTTPException(status_code=400, detail="Missing signature")
    
    # Verify signature
    import hashlib
    import hmac
    
    expected_signature = hmac.new(
        settings.PAYSTACK_SECRET.encode(),
        body,
        hashlib.sha512
    ).hexdigest()
    
    if signature != expected_signature:
        logger.warning("Paystack webhook signature verification failed")
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    # Process event
    event = payload.get("event")
    data = payload.get("data", {})
    
    logger.info(f"Paystack webhook event: {event}")
    
    if event == "charge.success":
        # Extract subscription details from metadata
        metadata = data.get("metadata", {})
        user_id = metadata.get("user_id")
        plan = metadata.get("plan")
        reference = data.get("reference", "")
        
        # Validate data
        if not user_id or not plan:
            logger.error(f"Paystack webhook missing user_id or plan: {metadata}")
            return {"status": "error", "message": "Missing metadata"}
        
        # Check if this is a subscription payment (reference starts with SUB-)
        if not reference.startswith("SUB-"):
            logger.info(f"Ignoring non-subscription payment: {reference}")
            return {"status": "ok", "message": "Not a subscription payment"}
        
        # Get user
        user = db.query(models.User).filter(models.User.id == user_id).one_or_none()
        if not user:
            logger.error(f"User {user_id} not found for subscription payment")
            return {"status": "error", "message": "User not found"}
        
        # Upgrade plan
        old_plan = user.plan.value
        try:
            user.plan = models.SubscriptionPlan[plan.upper()]
            db.commit()
            
            logger.info(
                f"✅ Upgraded user {user_id} from {old_plan} to {plan} "
                f"via Paystack webhook (ref: {reference})"
            )
            
            return {
                "status": "success",
                "message": f"User {user_id} upgraded to {plan}",
                "old_plan": old_plan,
                "new_plan": plan,
            }
        except KeyError:
            logger.error(f"Invalid plan name: {plan}")
            return {"status": "error", "message": "Invalid plan"}
    
    # Other events (ignore for now)
    return {"status": "ok", "message": f"Event {event} received"}
