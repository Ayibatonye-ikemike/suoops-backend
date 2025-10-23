from __future__ import annotations

import logging
from typing import Any

import asyncio

from celery import Task

from app.bot.nlp_service import NLPService
from app.bot.whatsapp_adapter import WhatsAppClient, WhatsAppHandler
from app.core.config import settings
from app.db.session import session_scope
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="whatsapp.process_inbound",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def process_whatsapp_inbound(self: Task, payload: dict[str, Any]) -> None:
    """
    Process inbound WhatsApp message.
    
    Handler will create invoice service on-demand with the correct user's Paystack credentials.
    """
    with session_scope() as db:
        handler = WhatsAppHandler(
            client=WhatsAppClient(settings.WHATSAPP_API_KEY),
            nlp=NLPService(),
            db=db,
        )
        asyncio.run(handler.handle_incoming(payload))


@celery_app.task(name="maintenance.send_overdue_reminders")
def send_overdue_reminders() -> None:
    logger.info("(stub) scanning for overdue invoices")
