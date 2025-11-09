"""Legacy notification helper wrappers.

TODO(dead-code): Replace test monkeypatch usage of this module and then remove.
Direct calls should use `NotificationService` facade methods instead.
"""
from __future__ import annotations

import asyncio
import logging
from sqlalchemy.orm import Session

from app.models import models

logger = logging.getLogger(__name__)


def send_receipt_to_customer(invoice: models.Invoice) -> None:
    """Send payment receipt to customer via available channels.

    Synchronous wrapper maintained for legacy callers; uses asyncio.run internally.
    """
    if not invoice.customer:
        logger.info("Cannot send receipt: no customer on invoice %s", invoice.invoice_id)
        return
    customer_email = getattr(invoice.customer, "email", None)
    customer_phone = getattr(invoice.customer, "phone", None)
    if not customer_email and not customer_phone:
        logger.info("Cannot send receipt: no contact info for invoice %s", invoice.invoice_id)
        return
    from app.services.notification.service import NotificationService
    service = NotificationService()

    async def _run():  # pragma: no cover - network IO
        return await service.send_receipt_notification(
            invoice=invoice,
            customer_email=customer_email,
            customer_phone=customer_phone,
            pdf_url=invoice.pdf_url,
        )
    try:
        results = asyncio.run(_run())
        logger.info(
            "Receipt sent for invoice %s - Email: %s, WhatsApp: %s, SMS: %s",
            invoice.invoice_id,
            results["email"],
            results["whatsapp"],
            results["sms"],
        )
    except Exception as e:  # pragma: no cover - best effort logging
        logger.error("Failed to send receipt notifications: %s", e)


def notify_business_of_customer_confirmation(db: Session, invoice: models.Invoice) -> None:
    """Notify business owner that customer confirmed transfer.

    Maintained for legacy import sites; should be replaced with direct facade usage.
    """
    try:
        user = db.query(models.User).filter(models.User.id == invoice.issuer_id).one_or_none()
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to load issuer for invoice %s: %s", invoice.invoice_id, exc)
        return
    if not user:
        logger.warning("Cannot notify business for invoice %s: issuer missing", invoice.invoice_id)
        return
    message = (
        "Customer reported a transfer.\n\n"
        f"Invoice: {invoice.invoice_id}\n"
        f"Amount: ₦{invoice.amount:,.2f}\n\n"
        "Please confirm the funds and mark the invoice as paid to send their receipt."
    )
    from app.services.notification.service import NotificationService
    service = NotificationService()

    async def _run():  # pragma: no cover - network IO
        results = {"email": False, "sms": False}
        if user.email:
            try:
                results["email"] = await service.send_email(
                    to_email=user.email,
                    subject=f"Payment Confirmation - Invoice {invoice.invoice_id}",
                    body=message,
                )
            except Exception as exc:  # pragma: no cover
                logger.error("Failed email notify business %s: %s", invoice.invoice_id, exc)
        if user.phone:
            try:
                # Reuse SMS channel (if configured) rather than private method.
                results["sms"] = await service.send_receipt_sms(invoice, user.phone)
            except Exception as exc:  # pragma: no cover
                logger.error("Failed SMS notify business %s: %s", invoice.invoice_id, exc)
        logger.info(
            "Business notification for invoice %s - Email: %s, SMS: %s",
            invoice.invoice_id,
            results["email"],
            results["sms"],
        )

    try:
        asyncio.run(_run())
    except Exception as e:  # pragma: no cover
        logger.error("Notification dispatch failed for invoice %s: %s", invoice.invoice_id, e)

__all__ = ["send_receipt_to_customer", "notify_business_of_customer_confirmation"]
