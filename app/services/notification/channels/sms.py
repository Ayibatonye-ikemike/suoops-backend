from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from app.core.config import settings

if TYPE_CHECKING:  # pragma: no cover
    from app.models import models
    from app.services.notification.service import NotificationService

logger = logging.getLogger(__name__)


class SMSChannel:
    """Encapsulates SMS sending via configured provider (Brevo or Termii)."""

    def __init__(self, service: "NotificationService") -> None:
        self._service = service

    async def send_invoice(self, invoice: "models.Invoice", recipient_phone: str) -> bool:
        business_name = "Business"
        if hasattr(invoice, "issuer") and invoice.issuer:
            business_name = getattr(invoice.issuer, "business_name", None) or business_name
        frontend_url = getattr(settings, "FRONTEND_URL", "https://suoops.com")
        payment_link = f"{frontend_url.rstrip('/')}/pay/{invoice.invoice_id}"
        message = (
            f"New invoice from {business_name}: {invoice.invoice_id}\n"
            f"Amount: ₦{invoice.amount:,.2f}\n"
            f"Pay here: {payment_link}"
        )
        return await self._dispatch(recipient_phone, message, receipt=False)

    async def send_receipt(self, invoice: "models.Invoice", recipient_phone: str) -> bool:
        business_name = "Business"
        if hasattr(invoice, "issuer") and invoice.issuer:
            business_name = getattr(invoice.issuer, "business_name", None) or business_name
        message = (
            f"Payment received! Thank you for paying invoice {invoice.invoice_id}\n"
            f"Amount: ₦{invoice.amount:,.2f}\n"
            f"Status: PAID\n- {business_name}"
        )
        return await self._dispatch(recipient_phone, message, receipt=True)

    async def _dispatch(self, to: str, message: str, receipt: bool) -> bool:
        provider = self._service.sms_provider
        if provider == "brevo":
            if not self._service.brevo_api_key:
                logger.warning("SMS not configured%s. Set BREVO_API_KEY", " for receipt" if receipt else "")
                return False
            return await self._send_brevo_sms(to, message)
        if provider == "termii":
            if not self._service.termii_api_key:
                logger.warning("SMS not configured%s. Set TERMII_API_KEY", " for receipt" if receipt else "")
                return False
            return await self._send_termii_sms(to, message)
        logger.warning("Unsupported SMS provider: %s", provider)
        return False

    async def _send_brevo_sms(self, to: str, message: str) -> bool:  # pragma: no cover - external service
        try:
            url = "https://api.brevo.com/v3/transactionalSMS/send"
            phone = to.replace("+", "").replace(" ", "").replace("-", "")
            payload = {
                "sender": self._service.brevo_sender_name,
                "recipient": phone,
                "content": message,
                "type": "transactional",
            }
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "api-key": self._service.brevo_api_key,
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                if data.get("messageId"):
                    logger.info("Brevo SMS sent successfully to %s (messageId: %s)", to, data.get("messageId"))
                    return True
                logger.warning("Brevo SMS failed: %s", data)
                return False
        except Exception as e:
            # SMS is optional - log as warning to avoid Sentry noise
            logger.warning("Failed to send Brevo SMS: %s", e)
            return False

    async def _send_termii_sms(self, to: str, message: str) -> bool:  # pragma: no cover - external service
        try:
            url = "https://api.ng.termii.com/api/sms/send"
            phone = to.replace("+", "")
            payload = {
                "to": phone,
                "from": self._service.termii_sender_id,
                "sms": message,
                "type": "plain",
                "channel": "generic",
                "api_key": self._service.termii_api_key,
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                if data.get("message_id"):
                    logger.info("Termii SMS sent successfully to %s", to)
                    return True
                logger.error("Termii SMS failed: %s", data)
                return False
        except Exception as e:
            logger.error("Failed to send Termii SMS: %s", e)
            return False
