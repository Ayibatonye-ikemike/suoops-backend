from typing import Annotated, TypeAlias

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import WebhookEvent
from app.queue.whatsapp_queue import enqueue_message
from app.services.invoice_service import InvoiceService, get_invoice_service
from app.services.payment_service import PaymentService

router = APIRouter()

InvoiceServiceDep: TypeAlias = Annotated[InvoiceService, Depends(get_invoice_service)]
SessionDep: TypeAlias = Annotated[Session, Depends(get_db)]


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    payload = await request.json()
    # enqueue for async processing via Celery worker
    enqueue_message(payload)
    return {"ok": True, "queued": True}


@router.post("/paystack")
async def paystack_webhook(
    request: Request,
    svc: InvoiceServiceDep,
    db: SessionDep,
):
    raw = await request.body()
    sig = request.headers.get("x-paystack-signature")
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
    svc.handle_payment_webhook({"reference": reference, "status": status})
    rec = WebhookEvent(provider="paystack", external_id=external_id, signature=sig)
    db.add(rec)
    db.commit()
    return {"ok": True}


@router.post("/flutterwave")
async def flutterwave_webhook(
    request: Request,
    svc: InvoiceServiceDep,
    db: SessionDep,
):
    raw = await request.body()
    sig = request.headers.get("verif-hash")
    payment_service = PaymentService()
    if not payment_service.verify_webhook(raw, sig, provider="flutterwave"):
        raise HTTPException(status_code=400, detail="Invalid signature")
    event = await request.json()
    data = event.get("data", {})
    external_id = str(data.get("id") or data.get("tx_ref") or data.get("flw_ref"))
    existing = (
        db.query(WebhookEvent)
        .filter(WebhookEvent.provider == "flutterwave", WebhookEvent.external_id == external_id)
        .one_or_none()
    )
    if existing:
        return {"ok": True, "duplicate": True}
    reference = data.get("tx_ref") or data.get("flw_ref")
    status = data.get("status")
    svc.handle_payment_webhook({"reference": reference, "status": status})
    rec = WebhookEvent(provider="flutterwave", external_id=external_id, signature=sig)
    db.add(rec)
    db.commit()
    return {"ok": True}
