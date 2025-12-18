from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.config import settings
from app.services.notification.channels.email import EmailChannel
from app.services.notification.channels.whatsapp import WhatsAppChannel
from app.services.notification.channels.sms import SMSChannel

if TYPE_CHECKING:  # pragma: no cover
    from app.models import models

logger = logging.getLogger(__name__)


class NotificationService:
    """Facade for sending notifications via Email, WhatsApp, and SMS.

    Public methods preserved for compatibility while delegating to channel classes.
    """

    def __init__(self) -> None:
        # WhatsApp setup
        self.whatsapp_key = getattr(settings, "WHATSAPP_API_KEY", None)
        self.whatsapp_phone_number_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", None)
        # SMS provider setup
        self.sms_provider = getattr(settings, "SMS_PROVIDER", "brevo")
        self.brevo_api_key = getattr(settings, "BREVO_API_KEY", None)
        self.brevo_sender_name = getattr(settings, "BREVO_SENDER_NAME", "SuoOps")
        self.termii_api_key = getattr(settings, "TERMII_API_KEY", None)
        self.termii_sender_id = getattr(settings, "TERMII_SENDER_ID", "SuoOps")
        self.termii_device_id = getattr(settings, "TERMII_DEVICE_ID", "TID")
        # Channels
        self.email = EmailChannel(self)
        self.whatsapp = WhatsAppChannel(self)
        self.sms = SMSChannel(self)

    def _get_smtp_config(self) -> dict[str, str | int] | None:
        """Get SMTP configuration for Brevo email sending.
        
        Returns:
            dict with host, port, user, password or None if not configured
        """
        provider = getattr(settings, "EMAIL_PROVIDER", "brevo").lower()
        
        if provider == "brevo":
            # Brevo (formerly Sendinblue) SMTP configuration
            # https://developers.brevo.com/docs/send-emails-with-smtp
            host = getattr(settings, "SMTP_HOST", "smtp-relay.brevo.com")
            port = getattr(settings, "SMTP_PORT", 587)
            
            # Try SMTP_USER first (actual SMTP credential), fallback to BREVO_SMTP_LOGIN
            user = getattr(settings, "SMTP_USER", None) or getattr(settings, "BREVO_SMTP_LOGIN", None)
            
            # Brevo SMTP password is separate from API key - use SMTP_PASSWORD first
            password = getattr(settings, "SMTP_PASSWORD", None) or getattr(settings, "BREVO_API_KEY", None)
            
            if not all([user, password]):
                logger.warning("Brevo email not configured. Set SMTP_USER/BREVO_SMTP_LOGIN and SMTP_PASSWORD/BREVO_API_KEY")
                return None
                
            logger.info("Using Brevo SMTP for email: %s", host)
            return {
                "host": host,
                "port": port,
                "user": user,
                "password": password,
                "provider": "Brevo"
            }
        
        logger.warning("Unsupported EMAIL_PROVIDER: %s. Only 'brevo' is supported.", provider)
        return None

    # --- Email ---
    async def send_invoice_email(
        self,
        invoice: "models.Invoice",
        recipient_email: str,
        pdf_url: str | None = None,
        subject: str = "New Invoice",
    ) -> bool:
        return await self.email.send_invoice(invoice, recipient_email, pdf_url, subject)

    async def send_receipt_email(
        self,
        invoice: "models.Invoice",
        recipient_email: str,
        pdf_url: str | None = None,
    ) -> bool:
        return await self.email.send_receipt(invoice, recipient_email, pdf_url)

    async def send_email(self, to_email: str, subject: str, body: str) -> bool:
        return await self.email.send_simple(to_email, subject, body)

    # --- WhatsApp ---
    async def send_invoice_whatsapp(
        self,
        invoice: "models.Invoice",
        recipient_phone: str,
        pdf_url: str | None = None,
    ) -> bool:
        return await self.whatsapp.send_invoice(invoice, recipient_phone, pdf_url)

    async def send_receipt_whatsapp(
        self,
        invoice: "models.Invoice",
        recipient_phone: str,
        pdf_url: str | None = None,
    ) -> bool:
        return await self.whatsapp.send_receipt(invoice, recipient_phone, pdf_url)

    # --- SMS ---
    async def send_invoice_sms(self, invoice: "models.Invoice", recipient_phone: str) -> bool:
        return await self.sms.send_invoice(invoice, recipient_phone)

    async def send_receipt_sms(self, invoice: "models.Invoice", recipient_phone: str) -> bool:
        return await self.sms.send_receipt(invoice, recipient_phone)

    # --- Composite ---
    async def send_invoice_notification(
        self,
        invoice: "models.Invoice",
        customer_email: str | None = None,
        customer_phone: str | None = None,
        pdf_url: str | None = None,
    ) -> dict[str, bool]:
        results = {"email": False, "whatsapp": False, "sms": False}
        if customer_email:
            results["email"] = await self.send_invoice_email(invoice, customer_email, pdf_url)
        if customer_phone:
            results["whatsapp"] = await self.send_invoice_whatsapp(invoice, customer_phone, pdf_url)
            results["sms"] = await self.send_invoice_sms(invoice, customer_phone)
        logger.info(
            "Invoice notification sent - Email: %s, WhatsApp: %s, SMS: %s",
            results["email"],
            results["whatsapp"],
            results["sms"],
        )
        return results

    async def send_receipt_notification(
        self,
        invoice: "models.Invoice",
        customer_email: str | None = None,
        customer_phone: str | None = None,
        pdf_url: str | None = None,
    ) -> dict[str, bool]:
        results = {"email": False, "whatsapp": False, "sms": False}
        if customer_email:
            results["email"] = await self.send_receipt_email(
                invoice,
                customer_email,
                invoice.receipt_pdf_url or pdf_url,
            )
        if customer_phone:
            results["whatsapp"] = await self.send_receipt_whatsapp(invoice, customer_phone, invoice.receipt_pdf_url or pdf_url)
            results["sms"] = await self.send_receipt_sms(invoice, customer_phone)
        logger.info(
            "Receipt notification sent - Email: %s, WhatsApp: %s, SMS: %s",
            results["email"],
            results["whatsapp"],
            results["sms"],
        )
        return results
