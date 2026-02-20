"""
Messaging and WhatsApp Tasks.

Celery tasks for WhatsApp processing, reminders, OCR, and payment sync.
"""
from __future__ import annotations

import asyncio
import gc
import logging
from datetime import date, datetime, timedelta, timezone
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
def send_overdue_reminders() -> dict[str, Any]:
    """Send reminders for overdue invoices.

    Queries all pending invoices past their due date, groups by issuer,
    and sends a WhatsApp/email notification to the business owner.
    """
    from sqlalchemy import func
    from sqlalchemy.orm import joinedload

    from app.models.models import Invoice, User

    sent = 0
    failed = 0

    try:
        with session_scope() as db:
            today = date.today()

            # Get overdue invoices grouped by issuer
            overdue_invoices = (
                db.query(Invoice)
                .options(joinedload(Invoice.customer))
                .filter(
                    Invoice.status == "pending",
                    Invoice.invoice_type == "revenue",
                    Invoice.due_date != None,  # noqa: E711
                    Invoice.due_date < datetime.combine(today, datetime.min.time()),
                )
                .all()
            )

            if not overdue_invoices:
                logger.info("No overdue invoices found")
                return {"success": True, "sent": 0, "total_overdue": 0}

            # Group by issuer
            by_issuer: dict[int, list[Invoice]] = {}
            for inv in overdue_invoices:
                by_issuer.setdefault(inv.issuer_id, []).append(inv)

            logger.info(
                "Found %d overdue invoices for %d users",
                len(overdue_invoices),
                len(by_issuer),
            )

            for issuer_id, invoices in by_issuer.items():
                user = db.query(User).filter(User.id == issuer_id).first()
                if not user or not user.phone:
                    continue

                total_owed = sum(inv.amount for inv in invoices)
                oldest_days = max(
                    (today - inv.due_date.date()).days for inv in invoices if inv.due_date
                )

                message = (
                    f"⚠️ You have {len(invoices)} overdue invoice(s) "
                    f"totalling ₦{total_owed:,.0f}.\n"
                    f"Oldest is {oldest_days} day(s) past due.\n\n"
                    "💡 Send payment reminders to your customers from the "
                    "SuoOps dashboard to get paid faster!"
                )

                try:
                    from app.bot.whatsapp_client import WhatsAppClient

                    client = WhatsAppClient(settings.WHATSAPP_API_KEY)
                    client.send_text(user.phone, message)
                    sent += 1
                except Exception as e:
                    logger.warning("Failed to send overdue reminder to user %s: %s", issuer_id, e)
                    failed += 1

        logger.info("Overdue reminders complete: sent=%d failed=%d", sent, failed)
        return {
            "success": True,
            "sent": sent,
            "failed": failed,
            "total_overdue": len(overdue_invoices),
        }

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
def sync_provider_status(self: Task, provider: str, reference: str) -> dict[str, Any]:
    """Sync payment provider status with retries on transient errors.

    Calls Paystack verify endpoint and updates the local invoice status
    to match what the payment provider reports.
    """
    import requests as http_requests

    from app.models.models import Invoice

    logger.info("Syncing provider status | provider=%s reference=%s", provider, reference)

    if provider != "paystack":
        logger.warning("Unsupported provider: %s", provider)
        return {"success": False, "error": f"Unsupported provider: {provider}"}

    paystack_key = settings.PAYSTACK_SECRET_KEY
    if not paystack_key:
        logger.error("PAYSTACK_SECRET_KEY not configured, cannot verify")
        return {"success": False, "error": "Paystack key not configured"}

    try:
        resp = http_requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {paystack_key}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("Paystack verify call failed for %s: %s", reference, e)
        raise  # triggers Celery retry

    tx_data = data.get("data", {})
    tx_status = tx_data.get("status", "unknown")  # success / failed / abandoned
    logger.info(
        "Paystack status for %s: %s (gateway_response=%s)",
        reference,
        tx_status,
        tx_data.get("gateway_response"),
    )

    # Map Paystack status to local invoice status
    status_map = {
        "success": "paid",
        "failed": "failed",
        "abandoned": "pending",
        "reversed": "failed",
    }
    new_status = status_map.get(tx_status)
    if not new_status:
        logger.warning("Unknown Paystack status '%s' for reference %s", tx_status, reference)
        return {"success": False, "error": f"Unknown provider status: {tx_status}"}

    with session_scope() as db:
        invoice = (
            db.query(Invoice)
            .filter(Invoice.invoice_id == reference)
            .first()
        )
        if not invoice:
            logger.warning("No invoice found for reference %s", reference)
            return {"success": False, "error": "Invoice not found"}

        old_status = invoice.status
        if old_status == new_status:
            logger.info("Invoice %s already %s, no update needed", invoice.invoice_id, new_status)
            return {"success": True, "status": new_status, "changed": False}

        invoice.status = new_status
        if new_status == "paid":
            invoice.status_updated_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            "Invoice %s status synced: %s → %s (ref=%s)",
            invoice.invoice_id,
            old_status,
            new_status,
            reference,
        )

    return {"success": True, "status": new_status, "changed": True, "old_status": old_status}


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


# ── Daily Business Summary ───────────────────────────────────────────


@celery_app.task(
    name="summary.send_daily_summaries",
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_kwargs={"max_retries": 2},
)
def send_daily_summaries() -> dict[str, Any]:
    """Send daily business summary to all active users via WhatsApp.

    Runs every evening (18:00 UTC / 19:00 WAT).  Skips users with zero
    activity for the day so it never feels like spam.
    """
    from sqlalchemy import func as sqlfunc
    from sqlalchemy.orm import joinedload

    from app.models.models import Invoice, User

    sent = 0
    failed = 0

    try:
        with session_scope() as db:
            today = date.today()
            start_of_day = datetime.combine(today, datetime.min.time())

            # Get users who have at least one invoice and a phone number
            # Only PRO users get daily summaries
            active_users = (
                db.query(User)
                .filter(
                    User.phone != None,  # noqa: E711
                    User.plan == "pro",
                )
                .join(Invoice, Invoice.issuer_id == User.id)
                .group_by(User.id)
                .having(sqlfunc.count(Invoice.id) > 0)
                .all()
            )

            for user in active_users:
                try:
                    # Revenue collected today
                    revenue_today = (
                        db.query(sqlfunc.coalesce(sqlfunc.sum(Invoice.amount), 0))
                        .filter(
                            Invoice.issuer_id == user.id,
                            Invoice.invoice_type == "revenue",
                            Invoice.status == "paid",
                            Invoice.paid_at >= start_of_day,
                        )
                        .scalar()
                    )

                    # Expenses recorded today
                    expenses_today = (
                        db.query(sqlfunc.coalesce(sqlfunc.sum(Invoice.amount), 0))
                        .filter(
                            Invoice.issuer_id == user.id,
                            Invoice.invoice_type == "expense",
                            Invoice.created_at >= start_of_day,
                        )
                        .scalar()
                    )

                    # Total outstanding
                    outstanding = (
                        db.query(sqlfunc.coalesce(sqlfunc.sum(Invoice.amount), 0))
                        .filter(
                            Invoice.issuer_id == user.id,
                            Invoice.invoice_type == "revenue",
                            Invoice.status.in_(["pending", "awaiting_confirmation"]),
                        )
                        .scalar()
                    )

                    # Overdue count
                    overdue_count = (
                        db.query(sqlfunc.count(Invoice.id))
                        .filter(
                            Invoice.issuer_id == user.id,
                            Invoice.invoice_type == "revenue",
                            Invoice.status == "pending",
                            Invoice.due_date != None,  # noqa: E711
                            Invoice.due_date < start_of_day,
                        )
                        .scalar()
                    ) or 0

                    # Skip if nothing happened and nothing is overdue
                    if (
                        float(revenue_today) == 0
                        and float(expenses_today) == 0
                        and overdue_count == 0
                    ):
                        continue

                    message = _format_daily_summary(
                        revenue_today, expenses_today, outstanding, overdue_count
                    )

                    from app.bot.whatsapp_client import WhatsAppClient

                    client = WhatsAppClient(settings.WHATSAPP_API_KEY)
                    client.send_text(user.phone, message)
                    sent += 1

                except Exception as e:
                    logger.warning("Failed daily summary for user %s: %s", user.id, e)
                    failed += 1

        logger.info("Daily summaries: sent=%d failed=%d", sent, failed)
        return {"success": True, "sent": sent, "failed": failed}

    except Exception as exc:
        logger.error("Daily summary task failed: %s", exc)
        raise


def _format_daily_summary(
    revenue: Any, expenses: Any, outstanding: Any, overdue_count: int
) -> str:
    """Format the daily WhatsApp summary message."""
    rev = float(revenue)
    exp = float(expenses)
    net = rev - exp
    out = float(outstanding)

    msg = "📊 *Today's Business Summary*\n\n"

    if rev > 0:
        msg += f"💰 Cash In: ₦{rev:,.0f}\n"
    if exp > 0:
        msg += f"💸 Expenses: ₦{exp:,.0f}\n"
    if rev > 0 or exp > 0:
        emoji = "📈" if net >= 0 else "📉"
        msg += f"{emoji} Net: ₦{net:,.0f}\n"

    msg += "\n"

    if out > 0:
        msg += f"⏳ Outstanding: ₦{out:,.0f}\n"
    if overdue_count > 0:
        s = "s" if overdue_count != 1 else ""
        msg += (
            f"⚠️ Overdue: {overdue_count} invoice{s}\n"
            "💡 Send reminders from your dashboard to collect faster!\n"
        )

    msg += "\n🔗 suoops.com/dashboard"
    return msg
