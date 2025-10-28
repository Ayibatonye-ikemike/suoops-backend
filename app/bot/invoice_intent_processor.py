from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.bot.whatsapp_client import WhatsAppClient
from app.core.config import settings
from app.services.invoice_service import build_invoice_service

logger = logging.getLogger(__name__)


class InvoiceIntentProcessor:
    """Handle the invoice creation intent extracted from NLP results."""

    def __init__(self, db: Session, client: WhatsAppClient):
        self.db = db
        self.client = client

    async def handle(self, sender: str, parse: Any, payload: dict[str, Any]) -> None:
        if getattr(parse, "intent", None) != "create_invoice":
            self.client.send_text(
                sender,
                "Sorry, I didn't understand. Try:\n"
                "• Text: \"Invoice Joy 12000 for wigs due tomorrow\"\n"
                "• Voice: Send a voice note with invoice details",
            )
            return

        data = getattr(parse, "entities", {})
        customer_phone = data.get("customer_phone")
        if not customer_phone:
            self.client.send_text(
                sender,
                "⚠️ Please include the customer's phone number in your message.\n\n"
                "Example: Invoice Jane +2348087654321 50000 for logo design",
            )
            return

        issuer_id = self._resolve_issuer_id(sender)
        if issuer_id is None:
            logger.warning("Unable to resolve issuer for WhatsApp sender: %s", sender)
            self.client.send_text(
                sender,
                "❌ Unable to identify your business account.\n\n"
                "Please ensure your WhatsApp number is registered in your profile at "
                "suoops.com/dashboard/settings",
            )
            return

        invoice_service = build_invoice_service(self.db, user_id=issuer_id)

        if not self._enforce_quota(invoice_service, issuer_id, sender):
            return

        await self._create_invoice(invoice_service, issuer_id, sender, data, payload)

    def _enforce_quota(self, invoice_service, issuer_id: int, sender: str) -> bool:
        try:
            quota_check = invoice_service.check_invoice_quota(issuer_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to check quota: %s", exc)
            return True

        limit = quota_check.get("limit")
        remaining = (limit - quota_check.get("used", 0)) if limit else None

        if quota_check.get("can_create") and remaining is not None and 0 < remaining <= 5:
            self.client.send_text(sender, quota_check.get("message", ""))

        if quota_check.get("can_create"):
            return True

        limit_message = (
            "🚫 Invoice Limit Reached!\n\n"
            f"Plan: {quota_check.get('plan', '').upper()}\n"
            f"Used: {quota_check.get('used')}/{quota_check.get('limit')} invoices this month\n\n"
            f"{quota_check.get('message', '')}\n\n"
            "📞 Contact us to upgrade your plan."
        )
        self.client.send_text(sender, limit_message)
        return False

    async def _create_invoice(
        self,
        invoice_service,
        issuer_id: int,
        sender: str,
        data: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        try:
            invoice = invoice_service.create_invoice(issuer_id=issuer_id, data=data)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to create invoice")
            error_msg = str(exc)
            if "invoice_limit_reached" in error_msg or "403" in error_msg:
                self.client.send_text(
                    sender,
                    "🚫 You've reached your monthly invoice limit.\n\n"
                    "Upgrade your plan to create more invoices.",
                )
            else:
                self.client.send_text(sender, f"Error: {exc}")
            return

        self._notify_business(sender, invoice)
        self._notify_customer(invoice, data, issuer_id)

    def _notify_business(self, sender: str, invoice) -> None:
        customer_name = getattr(invoice.customer, "name", "N/A") if invoice.customer else "N/A"
        business_message = (
            f"✅ Invoice {invoice.invoice_id} created!\n\n"
            f"💰 Amount: ₦{invoice.amount:,.2f}\n"
            f"👤 Customer: {customer_name}\n"
            f" Status: {invoice.status}\n\n"
            "📧 Invoice sent to customer!"
        )
        self.client.send_text(sender, business_message)

    def _notify_customer(self, invoice, data: dict[str, Any], issuer_id: int) -> None:
        customer_phone = data.get("customer_phone")
        if not customer_phone:
            logger.warning("No customer phone for invoice %s", invoice.invoice_id)
            return

        issuer = self._load_issuer(issuer_id)
        customer_name = getattr(invoice.customer, "name", "valued customer") if invoice.customer else "valued customer"
        amount_text = f"₦{invoice.amount:,.2f}"
        payment_hint = self._build_payment_hint(issuer)

        template_sent = self._send_template(customer_phone, invoice.invoice_id, customer_name, amount_text, payment_hint)

        if not template_sent:
            self.client.send_text(customer_phone, self._build_fallback_message(invoice, issuer))

        if invoice.pdf_url and invoice.pdf_url.startswith("http"):
            self.client.send_document(
                customer_phone,
                invoice.pdf_url,
                f"Invoice_{invoice.invoice_id}.pdf",
                f"Invoice {invoice.invoice_id} - {amount_text}",
            )

    def _load_issuer(self, issuer_id: int):
        from app.models import models

        return self.db.query(models.User).filter(models.User.id == issuer_id).one_or_none()

    def _build_payment_hint(self, issuer) -> str:
        if not issuer or not issuer.bank_name or not issuer.account_number:
            return "Please contact the business for payment details."

        hint = f"{issuer.bank_name} {issuer.account_number}"
        if getattr(issuer, "account_name", None):
            hint += f" ({issuer.account_name})"
        return hint

    def _send_template(
        self,
        customer_phone: str,
        invoice_id: str,
        customer_name: str,
        amount_text: str,
        payment_hint: str,
    ) -> bool:
        template_name = getattr(settings, "WHATSAPP_TEMPLATE_INVOICE", None)
        if not template_name:
            return False

        components = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": customer_name},
                    {"type": "text", "text": invoice_id},
                    {"type": "text", "text": amount_text},
                    {"type": "text", "text": payment_hint},
                ],
            }
        ]

        return self.client.send_template(
            customer_phone,
            template_name=template_name,
            language=getattr(settings, "WHATSAPP_TEMPLATE_LANGUAGE", "en_US"),
            components=components,
        )

    def _build_fallback_message(self, invoice, issuer) -> str:
        customer_name = getattr(invoice.customer, "name", "there") if invoice.customer else "there"
        amount_text = f"₦{invoice.amount:,.2f}"
        message = (
            f"Hello {customer_name}! 👋\n\n"
            "You have a new invoice.\n\n"
            f"📄 Invoice: {invoice.invoice_id}\n"
            f"💰 Amount: {amount_text}\n\n"
        )

        if issuer and issuer.bank_name and issuer.account_number:
            message += (
                "💳 Payment Details (Bank Transfer):\n"
                f"Bank: {issuer.bank_name}\n"
                f"Account: {issuer.account_number}\n"
            )
            if getattr(issuer, "account_name", None):
                message += f"Name: {issuer.account_name}\n"
            message += "\n📝 After payment, your receipt will be sent automatically."
        else:
            message += "💳 Please contact the business for payment details."

        return message

    def _resolve_issuer_id(self, sender_phone: str | None) -> int | None:
        from app.models import models

        if not sender_phone:
            return None

        clean_digits = "".join(ch for ch in sender_phone if ch.isdigit())
        candidates: set[str] = {sender_phone}

        if sender_phone.startswith("+"):
            candidates.add(sender_phone[1:])

        if clean_digits:
            candidates.add(clean_digits)
            if clean_digits.startswith("234"):
                candidates.add(f"+{clean_digits}")

        candidates = {c for c in candidates if c}
        if not candidates:
            return None

        user = (
            self.db.query(models.User)
            .filter(models.User.phone.in_(list(candidates)))
            .first()
        )

        if user:
            user_identifier = getattr(user, "email", None) or user.phone
            logger.info(
                "Resolved WhatsApp %s → User ID %s (%s)",
                sender_phone,
                user.id,
                user_identifier,
            )
            return user.id

        logger.warning("No user found for WhatsApp number: %s", sender_phone)
        return None
