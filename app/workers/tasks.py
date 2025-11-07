from __future__ import annotations

import asyncio
import logging
from typing import Any

from celery import Task

from app.bot.nlp_service import NLPService
from app.bot.whatsapp_adapter import WhatsAppClient, WhatsAppHandler
from app.core.config import settings
from app.db.session import session_scope
from app.workers.celery_app import celery_app
from app.db.session import session_scope
from app.services.tax_service import TaxProfileService
from app.storage.s3_client import s3_client
from app.services.pdf_service import PDFService
from app.models.tax_models import MonthlyTaxReport
from app.models.models import User

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


@celery_app.task(
    name="maintenance.send_overdue_reminders",
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def send_overdue_reminders() -> None:
    try:
        logger.info("(stub) scanning for overdue invoices")
        # Simulate potential transient failure placeholder
    except Exception as exc:  # noqa: BLE001
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
    with session_scope() as db:
        logger.info("Syncing provider status | provider=%s reference=%s", provider, reference)
        # Placeholder: would call PaymentService/Provider API
        # raise Exception("transient") to exercise retry logic if needed


@celery_app.task(
    bind=True,
    name="ocr.parse_image",
    autoretry_for=(Exception,),
    retry_backoff=15,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def ocr_parse_image(self: Task, image_bytes_b64: str, context: str | None = None) -> dict[str, Any]:
    """Run OCR parse with retries (handles rate limits/timeouts)."""
    import base64
    from app.services.ocr_service import OCRService
    raw = base64.b64decode(image_bytes_b64)
    service = OCRService()
    result = asyncio.run(service.parse_receipt(raw, context))
    if not result.get("success"):
        # Escalate failure for retry if transient network issues (heuristic)
        if "timeout" in str(result.get("error", "")).lower():
            raise Exception(result["error"])  # noqa: TRY002
    return result


@celery_app.task(
    bind=True,
    name="tax.generate_previous_month_reports",
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def generate_previous_month_reports(self: Task, basis: str = "paid") -> None:
    """Generate monthly tax reports (PDF) for all users for the previous month.

    Intended to run on the 1st day of the month via a scheduler (e.g. cron hitting Celery beat).
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    prev_month = now.month - 1 or 12
    year = now.year - 1 if prev_month == 12 and now.month == 1 else (now.year if prev_month != 12 or now.month != 1 else now.year)
    with session_scope() as db:
        tax_service = TaxProfileService(db)
        pdf_service = PDFService(s3_client)
        users = db.query(User).all()
        failures = 0
        for user in users:
            try:
                report = tax_service.generate_monthly_report(user.id, year, prev_month, basis=basis, force_regenerate=False)
                if not report.pdf_url:
                    pdf_url = pdf_service.generate_monthly_tax_report_pdf(report, basis=basis)
                    tax_service.attach_report_pdf(report, pdf_url)
                logger.info("Generated monthly tax report for user=%s period=%s-%02d", user.id, year, prev_month)
            except Exception as e:  # noqa: BLE001
                failures += 1
                logger.exception("Failed generating report for user %s: %s", user.id, e)
                tax_service.record_alert(
                    category="tax.report",
                    message=f"Monthly report generation failed for user {user.id}: {e}",
                    severity="error",
                )
        if failures:
            tax_service.record_alert(
                category="tax.report.summary",
                message=f"Monthly report generation completed with {failures} failures",
                severity="warning" if failures < len(users) else "error",
            )
