from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:  # pragma: no cover
    from app.models import models
    from app.services.notification.service import NotificationService

logger = logging.getLogger(__name__)


class WhatsAppChannel:
    """Encapsulates WhatsApp messaging for invoices and receipts."""

    def __init__(self, service: "NotificationService") -> None:
        self._service = service

    async def send_invoice(
        self,
        invoice: "models.Invoice",
        recipient_phone: str,
        pdf_url: str | None,
    ) -> bool:
        try:
            if not self._service.whatsapp_key or not self._service.whatsapp_phone_number_id:
                logger.warning("WhatsApp not configured. Set WHATSAPP_API_KEY and WHATSAPP_PHONE_NUMBER_ID")
                return False
            from app.bot.whatsapp_client import WhatsAppClient
            client = WhatsAppClient(self._service.whatsapp_key)
            business_name = "Business"
            if hasattr(invoice, "issuer") and invoice.issuer:
                business_name = getattr(invoice.issuer, "business_name", None) or business_name
            customer_name = invoice.customer.name if invoice.customer else "Customer"
            message = (
                f"\U0001F4C4 New Invoice from {business_name}\n\n"
                f"Invoice ID: {invoice.invoice_id}\n"
                f"Amount: ₦{invoice.amount:,.2f}\n"
                f"Status: {invoice.status.upper()}\n"
            )
            if invoice.due_date:
                message += f"Due: {invoice.due_date.strftime('%B %d, %Y')}\n"
            frontend_url = getattr(settings, "FRONTEND_URL", "https://suoops.com")
            payment_link = f"{frontend_url.rstrip('/')}/pay/{invoice.invoice_id}"
            message += f"\n\U0001F517 View & Pay: {payment_link}"
            client.send_text(recipient_phone, message)
            if pdf_url and pdf_url.startswith("http"):
                client.send_document(
                    recipient_phone,
                    pdf_url,
                    f"Invoice_{invoice.invoice_id}.pdf",
                    f"Invoice {invoice.invoice_id} - ₦{invoice.amount:,.2f}",
                )
            return True
        except Exception as e:  # pragma: no cover - network failures
            logger.error("Failed to send invoice via WhatsApp: %s", e)
            return False

    async def send_receipt(
        self,
        invoice: "models.Invoice",
        recipient_phone: str,
        pdf_url: str | None,
    ) -> bool:
        try:
            if not self._service.whatsapp_key or not self._service.whatsapp_phone_number_id:
                logger.warning("WhatsApp not configured for receipt")
                return False
            from app.bot.whatsapp_client import WhatsAppClient
            client = WhatsAppClient(self._service.whatsapp_key)
            receipt_message = (
                "\U0001F389 Payment Received!\n\n"
                "Thank you for your payment!\n\n"
                f"\U0001F4C4 Invoice: {invoice.invoice_id}\n"
                f"\U0001F4B0 Amount Paid: ₦{invoice.amount:,.2f}\n"
                "\u2705 Status: PAID\n\n"
                "Your receipt is attached below."
            )
            client.send_text(recipient_phone, receipt_message)
            if pdf_url and pdf_url.startswith("http"):
                client.send_document(
                    recipient_phone,
                    pdf_url,
                    f"Receipt_{invoice.invoice_id}.pdf",
                    f"Payment Receipt - ₦{invoice.amount:,.2f}",
                )
            return True
        except Exception as e:  # pragma: no cover - network failures
            logger.error("Failed to send receipt via WhatsApp: %s", e)
            return False
