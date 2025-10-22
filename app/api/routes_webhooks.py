from typing import Annotated, TypeAlias

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.models import WebhookEvent
from app.queue.whatsapp_queue import enqueue_message
from app.services.invoice_service import build_invoice_service
from app.services.payment_service import PaymentService

router = APIRouter()

SessionDep: TypeAlias = Annotated[Session, Depends(get_db)]


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
    payload = await request.json()
    # enqueue for async processing via Celery worker
    enqueue_message(payload)
    return {"ok": True, "queued": True}


@router.post("/paystack")
async def paystack_webhook(
    request: Request,
    db: SessionDep,
):
    """
    Handle Paystack webhook events.
    
    Note: In multi-tenant setup, we need to identify which business this webhook is for.
    For now, we use None which falls back to platform default credentials.
    TODO: Extract business identifier from webhook data and route to correct Paystack account.
    """
    raw = await request.body()
    sig = request.headers.get("x-paystack-signature")
    
    # Verify webhook signature using platform credentials (for now)
    payment_service = PaymentService()
    if not payment_service.verify_webhook(raw, sig, provider="paystack"):
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    event = await request.json()
    data = event.get("data", {})
    external_id = str(data.get("id") or data.get("reference"))
    
    # Idempotency check
    existing = (
        db.query(WebhookEvent)
        .filter(WebhookEvent.provider == "paystack", WebhookEvent.external_id == external_id)
        .one_or_none()
    )
    if existing:
        return {"ok": True, "duplicate": True}
    
    reference = data.get("reference")
    status = data.get("status")
    
    # Build service without user_id (falls back to platform default)
    # TODO: Determine user_id from payment reference and use their credentials
    svc = build_invoice_service(db, user_id=None)
    svc.handle_payment_webhook({"reference": reference, "status": status})
    
    rec = WebhookEvent(provider="paystack", external_id=external_id, signature=sig)
    db.add(rec)
    db.commit()
    return {"ok": True}


@router.post("/flutterwave")
async def flutterwave_webhook(
    request: Request,
    db: SessionDep,
):
    """
    Handle Flutterwave webhook events.
    
    Note: In multi-tenant setup, we need to identify which business this webhook is for.
    For now, we use None which falls back to platform default credentials.
    TODO: Extract business identifier from webhook data and route to correct Flutterwave account.
    """
    raw = await request.body()
    sig = request.headers.get("verif-hash")
    
    # Verify webhook signature using platform credentials (for now)
    payment_service = PaymentService()
    if not payment_service.verify_webhook(raw, sig, provider="flutterwave"):
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    event = await request.json()
    data = event.get("data", {})
    external_id = str(data.get("id") or data.get("tx_ref") or data.get("flw_ref"))
    
    # Idempotency check
    existing = (
        db.query(WebhookEvent)
        .filter(WebhookEvent.provider == "flutterwave", WebhookEvent.external_id == external_id)
        .one_or_none()
    )
    if existing:
        return {"ok": True, "duplicate": True}
    
    reference = data.get("tx_ref") or data.get("flw_ref")
    status = data.get("status")
    
    # Build service without user_id (falls back to platform default)
    # TODO: Determine user_id from payment reference and use their credentials
    svc = build_invoice_service(db, user_id=None)
    svc.handle_payment_webhook({"reference": reference, "status": status})
    
    rec = WebhookEvent(provider="flutterwave", external_id=external_id, signature=sig)
    db.add(rec)
    db.commit()
    return {"ok": True}
