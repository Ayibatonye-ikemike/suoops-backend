"""Status update and public retrieval helpers."""
from __future__ import annotations

import asyncio
import datetime as dt
import logging

from sqlalchemy.orm import Session, joinedload, selectinload

from app import metrics
from app.core.exceptions import InvoiceNotFoundError, InvalidInvoiceStatusError
from app.models import models

logger = logging.getLogger(__name__)


class InvoiceStatusMixin:
    db: Session

    def update_status(self, issuer_id: int, invoice_id: str, status: str) -> models.Invoice:
        if status not in {"pending", "awaiting_confirmation", "paid", "failed"}:
            raise InvalidInvoiceStatusError(new_status=status)

        invoice = (
            self.db.query(models.Invoice)
            .options(joinedload(models.Invoice.customer), joinedload(models.Invoice.issuer))
            .filter(models.Invoice.invoice_id == invoice_id, models.Invoice.issuer_id == issuer_id)
            .one_or_none()
        )
        if not invoice:
            raise InvoiceNotFoundError(invoice_id)

        previous_status = invoice.status
        if previous_status == status:
            return invoice

        invoice.status = status
        if status == "paid" and invoice.paid_at is None:
            invoice.paid_at = dt.datetime.now(dt.timezone.utc)
        self.db.commit()

        if invoice.paid_at and invoice.paid_at.tzinfo is None:
            invoice.paid_at = invoice.paid_at.replace(tzinfo=dt.timezone.utc)
            self.db.commit()

        if status == "paid" and previous_status != "paid":
            self._handle_manual_payment(invoice)

        if self.cache:
            self.cache.invalidate_invoice(invoice_id)
            self.cache.invalidate_user_invoices(issuer_id)

        return self.get_invoice(issuer_id, invoice_id)

    def confirm_transfer(self, invoice_id: str) -> models.Invoice:
        invoice = (
            self.db.query(models.Invoice)
            .options(selectinload(models.Invoice.customer))
            .filter(models.Invoice.invoice_id == invoice_id)
            .one_or_none()
        )
        if not invoice:
            raise ValueError("Invoice not found")

        if invoice.status in {"paid", "awaiting_confirmation"}:
            return invoice

        previous_status = invoice.status
        invoice.status = "awaiting_confirmation"
        self.db.commit()
        logger.info(
            "Invoice %s status transitioned %s → awaiting_confirmation after customer confirmation",
            invoice_id,
            previous_status,
        )
        self._notify_business_of_transfer(invoice)
        return invoice

    def get_public_invoice(self, invoice_id: str) -> tuple[models.Invoice, models.User]:
        invoice = (
            self.db.query(models.Invoice)
            .options(selectinload(models.Invoice.customer), selectinload(models.Invoice.lines))
            .filter(models.Invoice.invoice_id == invoice_id)
            .one_or_none()
        )
        if not invoice:
            raise ValueError("Invoice not found")

        issuer = self.db.query(models.User).filter(models.User.id == invoice.issuer_id).one_or_none()
        if not issuer:
            raise ValueError("Invoice issuer not found")
        return invoice, issuer

    def _handle_manual_payment(self, invoice: models.Invoice) -> None:
        metrics.invoice_paid()
        try:
            if not invoice.receipt_pdf_url:
                invoice.receipt_pdf_url = self.pdf_service.generate_receipt_pdf(invoice)
                self.db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to generate receipt PDF for %s: %s", invoice.invoice_id, exc)

        logger.info("Invoice %s manually marked as paid, sending receipt", invoice.invoice_id)
        try:
            from app.services.notification.service import NotificationService

            service = NotificationService()
            customer_email = getattr(invoice.customer, "email", None) if invoice.customer else None
            customer_phone = getattr(invoice.customer, "phone", None) if invoice.customer else None

            async def _run():  # pragma: no cover - network IO
                return await service.send_receipt_notification(
                    invoice=invoice,
                    customer_email=customer_email,
                    customer_phone=customer_phone,
                    pdf_url=invoice.pdf_url,
                )

            results = asyncio.run(_run())
            logger.info(
                "Receipt sent for invoice %s - Email: %s, WhatsApp: %s, SMS: %s",
                invoice.invoice_id,
                results["email"],
                results["whatsapp"],
                results["sms"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send receipt notifications for %s: %s", invoice.invoice_id, exc)

    def _notify_business_of_transfer(self, invoice: models.Invoice) -> None:
        try:
            user = self.db.query(models.User).filter(models.User.id == invoice.issuer_id).one_or_none()
        except Exception as exc:  # noqa: BLE001
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

        try:
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
                    except Exception as exc:  # noqa: BLE001
                        logger.error("Failed email notify business %s: %s", invoice.invoice_id, exc)
                if user.phone:
                    try:
                        results["sms"] = await service.send_receipt_sms(invoice, user.phone)
                    except Exception as exc:  # noqa: BLE001
                        logger.error("Failed SMS notify business %s: %s", invoice.invoice_id, exc)
                logger.info(
                    "Business notification for invoice %s - Email: %s, SMS: %s",
                    invoice.invoice_id,
                    results["email"],
                    results["sms"],
                )

            asyncio.run(_run())
        except Exception as exc:  # noqa: BLE001
            logger.error("Notification dispatch failed for invoice %s: %s", invoice.invoice_id, exc)
