"""
Messaging and WhatsApp Tasks.

Celery tasks for WhatsApp processing, reminders, OCR, and payment sync.
"""
from __future__ import annotations

import asyncio
import gc
import logging
from typing import Any

from celery import Task

from app.core.config import settings
from app.db.session import session_scope
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="whatsapp.process_inbound",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def process_whatsapp_inbound(self: Task, payload: dict[str, Any]) -> None:
    """Process inbound WhatsApp message.

    Heavy NLP / adapter imports are done lazily to keep baseline worker RSS low.
    """
    from app.bot.nlp_service import NLPService
    from app.bot.whatsapp_adapter import WhatsAppClient, WhatsAppHandler

    with session_scope() as db:
        handler = WhatsAppHandler(
            client=WhatsAppClient(settings.WHATSAPP_API_KEY),
            nlp=NLPService(),
            db=db,
        )
        asyncio.run(handler.handle_incoming(payload))

    gc.collect()


@celery_app.task(
    name="maintenance.send_overdue_reminders",
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def send_overdue_reminders() -> None:
    """Send reminders for overdue invoices."""
    try:
        logger.info("(stub) scanning for overdue invoices")
    except Exception as exc:
        logger.warning("Reminder task transient failure: %s", exc)
        raise


@celery_app.task(
    bind=True,
    name="payments.sync_provider_status",
    autoretry_for=(Exception,),
    retry_backoff=10,
    retry_jitter=True,
    retry_kwargs={"max_retries": 4},
)
def sync_provider_status(self: Task, provider: str, reference: str) -> None:
    """Sync payment provider status with retries on transient errors."""
    logger.info("Syncing provider status | provider=%s reference=%s", provider, reference)


@celery_app.task(
    bind=True,
    name="ocr.parse_image",
    autoretry_for=(Exception,),
    retry_backoff=15,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def ocr_parse_image(
    self: Task, image_bytes_b64: str, context: str | None = None
) -> dict[str, Any]:
    """Run OCR parse with retries (handles rate limits/timeouts)."""
    import base64
    from app.services.ocr_service import OCRService

    raw = base64.b64decode(image_bytes_b64)
    service = OCRService()
    result = asyncio.run(service.parse_receipt(raw, context))

    if not result.get("success"):
        if "timeout" in str(result.get("error", "")).lower():
            raise Exception(result["error"])

    return result
