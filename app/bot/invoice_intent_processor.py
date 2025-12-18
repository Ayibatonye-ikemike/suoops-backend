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
    
    async def _send_invoice_notifications(
        self,
        invoice,
        customer_email: str | None = None,
        customer_phone: str | None = None
    ) -> dict[str, bool]:
        """
        Send invoice notifications via all available channels (Email, WhatsApp, SMS).
        
        Args:
            invoice: Invoice model instance
            customer_email: Customer email address (optional)
            customer_phone: Customer phone number (optional)
        
        Returns:
            dict: Status of each channel {"email": bool, "whatsapp": bool, "sms": bool}
        """
        try:
            from app.services.notification_service import NotificationService
            
            notification_service = NotificationService()
            results = await notification_service.send_invoice_notification(
                invoice=invoice,
                customer_email=customer_email,
                customer_phone=customer_phone,
                pdf_url=invoice.pdf_url,
            )
            
            logger.info("Invoice %s notifications - Email: %s, WhatsApp: %s, SMS: %s",
                       invoice.invoice_id, results["email"], results["whatsapp"], results["sms"])
            
            return results
        except Exception as exc:  # noqa: BLE001
            logger.error("Error sending invoice notifications: %s", exc)
            return {"email": False, "whatsapp": False, "sms": False}

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

        # Send notifications via all channels (Email, WhatsApp, SMS)
        customer_email = data.get("customer_email")
        customer_phone = data.get("customer_phone")
        
        results = await self._send_invoice_notifications(
            invoice,
            customer_email=customer_email,
            customer_phone=customer_phone
        )

        self._notify_business(sender, invoice, customer_email, results)
        self._notify_customer(invoice, data, issuer_id)

    def _notify_business(
        self,
        sender: str,
        invoice,
        customer_email: str | None = None,
        notification_results: dict[str, bool] | None = None
    ) -> None:
        customer_name = getattr(invoice.customer, "name", "N/A") if invoice.customer else "N/A"
        business_message = (
            f"✅ Invoice {invoice.invoice_id} created!\n\n"
            f"💰 Amount: ₦{invoice.amount:,.2f}\n"
            f"👤 Customer: {customer_name}\n"
            f"📊 Status: {invoice.status}\n"
        )
        
        # Show notification status
        if notification_results:
            sent_channels = []
            if notification_results.get("email"):
                sent_channels.append("📧 Email")
            if notification_results.get("whatsapp"):
                sent_channels.append("💬 WhatsApp")
            if notification_results.get("sms"):
                sent_channels.append("📱 SMS")
            
            if sent_channels:
                business_message += f"\n✉️ Sent via: {', '.join(sent_channels)}"
        elif customer_email:
            business_message += "\n📧 Notifications sent to customer!"
        else:
            business_message += "\n📧 WhatsApp invoice sent to customer!"
        
        self.client.send_text(sender, business_message)

    def _notify_customer(self, invoice, data: dict[str, Any], issuer_id: int) -> None:
        customer_phone = data.get("customer_phone")
        logger.info("[NOTIFY] customer_phone from data: %s, invoice: %s", customer_phone, invoice.invoice_id)
        if not customer_phone:
            logger.warning("No customer phone for invoice %s", invoice.invoice_id)
            return

        issuer = self._load_issuer(issuer_id)
        customer_name = getattr(invoice.customer, "name", "valued customer") if invoice.customer else "valued customer"
        amount_text = f"₦{invoice.amount:,.2f}"
        items_text = self._build_items_text(invoice)

        logger.info("[NOTIFY] Sending template to %s for invoice %s", customer_phone, invoice.invoice_id)
        template_sent = self._send_template(customer_phone, invoice.invoice_id, customer_name, amount_text, items_text)
        logger.info("[NOTIFY] Template sent result: %s", template_sent)

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

    def _build_items_text(self, invoice) -> str:
        """Build a text summary of invoice line items for WhatsApp template."""
        if not invoice.lines:
            # Fallback if no lines - use customer name or generic
            customer_name = getattr(invoice.customer, "name", "Service") if invoice.customer else "Service"
            return f"Service for {customer_name}"
        
        # Build items list (limit to avoid WhatsApp character limits)
        items = []
        for line in invoice.lines[:3]:  # Max 3 items to keep message short
            desc = line.description[:30] if len(line.description) > 30 else line.description
            if line.quantity > 1:
                items.append(f"{line.quantity}x {desc}")
            else:
                items.append(desc)
        
        if len(invoice.lines) > 3:
            items.append(f"...and {len(invoice.lines) - 3} more")
        
        return ", ".join(items)

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
        items_text: str,
    ) -> bool:
        template_name = getattr(settings, "WHATSAPP_TEMPLATE_INVOICE", None)
        logger.info("[TEMPLATE] template_name=%s, language=%s", template_name, getattr(settings, "WHATSAPP_TEMPLATE_LANGUAGE", "en_US"))
        if not template_name:
            logger.warning("[TEMPLATE] No template configured, skipping")
            return False

        components = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": customer_name},
                    {"type": "text", "text": invoice_id},
                    {"type": "text", "text": amount_text},
                    {"type": "text", "text": items_text},
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
