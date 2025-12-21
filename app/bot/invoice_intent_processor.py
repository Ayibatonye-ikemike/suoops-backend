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
                "🤔 I didn't quite catch that.\n\n"
                "*To create an invoice, try:*\n"
                "• `Invoice Joy 08012345678, 12000 wig`\n"
                "• `Invoice Joy 12000 wig` (no phone - won't notify customer)\n"
                "• `Invoice Ada 08098765432, 5000 braids, 2000 gel`\n\n"
                "💡 Type *help* for a full guide!",
            )
            return

        data = getattr(parse, "entities", {})

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
        """Check invoice balance before creating invoice."""
        try:
            quota_check = invoice_service.check_invoice_quota(issuer_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to check quota: %s", exc)
            return True

        balance = quota_check.get("invoice_balance", 0)

        # Warn if balance is getting low
        if quota_check.get("can_create") and 0 < balance <= 10:
            self.client.send_text(
                sender, 
                f"⚠️ Only {balance} invoices left!\n\n"
                f"Purchase a pack: ₦{quota_check.get('pack_price', 2500):,} for {quota_check.get('pack_size', 100)} invoices\n"
                "Visit: suoops.com/dashboard/billing"
            )

        if quota_check.get("can_create"):
            return True

        # No balance remaining
        limit_message = (
            "🚫 No Invoices Remaining!\n\n"
            f"Plan: {quota_check.get('plan', '').upper()}\n"
            f"Balance: {balance} invoices\n\n"
            f"💳 Purchase a pack: ₦{quota_check.get('pack_price', 2500):,} for {quota_check.get('pack_size', 100)} invoices\n\n"
            "Visit suoops.com/dashboard/billing to buy more."
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
            if "invoice_balance_exhausted" in error_msg or "INV005" in error_msg:
                self.client.send_text(
                    sender,
                    "🚫 No invoices remaining!\n\n"
                    "Purchase a pack: ₦2,500 for 100 invoices\n"
                    "Visit: suoops.com/dashboard/billing",
                )
            else:
                self.client.send_text(sender, f"Error: {exc}")
            return

        # Send notifications via all channels (Email only - WhatsApp handled separately by _notify_customer)
        customer_email = data.get("customer_email")
        customer_phone = data.get("customer_phone")
        
        # Track if there's no contact info at all
        no_contact_info = not customer_email and not customer_phone
        
        # Only send email notification here - WhatsApp is handled by _notify_customer to avoid duplicates
        results = {"email": False, "whatsapp": False, "sms": False}
        if customer_email:
            try:
                from app.services.notification.service import NotificationService
                service = NotificationService()
                results["email"] = await service.send_invoice_email(invoice, customer_email, invoice.pdf_url)
            except Exception as exc:
                logger.error("Failed to send invoice email: %s", exc)

        whatsapp_pending = self._notify_customer(invoice, data, issuer_id) if customer_phone else False
        self._notify_business(sender, invoice, customer_email, results, whatsapp_pending, no_contact_info)

    def _notify_business(
        self,
        sender: str,
        invoice,
        customer_email: str | None = None,
        notification_results: dict[str, bool] | None = None,
        whatsapp_pending: bool = False,
        no_contact_info: bool = False
    ) -> None:
        customer_name = getattr(invoice.customer, "name", "N/A") if invoice.customer else "N/A"
        customer_phone = getattr(invoice.customer, "phone", None) if invoice.customer else None
        
        # Show appropriate status label
        status_display = "Awaiting Payment Confirmation" if invoice.status == "awaiting_confirmation" else invoice.status.replace("_", " ").title()
        
        business_message = (
            f"✅ Invoice {invoice.invoice_id} created!\n\n"
            f"💰 Amount: ₦{invoice.amount:,.2f}\n"
            f"👤 Customer: {customer_name}\n"
            f"📊 Status: {status_display}\n"
        )
        
        # Show notification status
        if no_contact_info:
            business_message += (
                "\n📝 No phone/email provided.\n"
                "⏳ Awaiting payment confirmation.\n"
                "💡 Click 'Mark Paid' when customer pays: suoops.com/dashboard/invoices"
            )
        elif whatsapp_pending:
            business_message += (
                "\n📱 WhatsApp notification sent!\n"
                "⏳ Customer needs to reply 'OK' to receive payment details & PDF.\n"
                "💡 First-time customers must reply once to enable full messaging."
            )
        elif notification_results:
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
            business_message += "\n✅ Full invoice sent to customer via WhatsApp!"
        
        self.client.send_text(sender, business_message)
        
        # Send invoice PDF as document (better UX than URL link)
        if invoice.pdf_url and invoice.pdf_url.startswith("http"):
            self.client.send_document(
                sender,
                invoice.pdf_url,
                f"Invoice_{invoice.invoice_id}.pdf",
                f"📄 Invoice {invoice.invoice_id} - ₦{invoice.amount:,.2f}",
            )

    def _notify_customer(self, invoice, data: dict[str, Any], issuer_id: int) -> bool:
        """
        Notify customer about their invoice.
        Returns True if delivery is pending (customer needs to reply first).
        """
        customer_phone = data.get("customer_phone")
        logger.info("[NOTIFY] customer_phone from data: %s, invoice: %s", customer_phone, invoice.invoice_id)
        if not customer_phone:
            logger.warning("No customer phone for invoice %s", invoice.invoice_id)
            return False

        # Check if customer has messaged us before (can receive regular messages)
        customer = invoice.customer
        has_opted_in = getattr(customer, "whatsapp_opted_in", False) if customer else False
        
        # Also check if the customer's phone belongs to a registered business user
        # Registered users should receive full invoices without needing to opt-in
        is_registered_user = self._is_registered_user(customer_phone)
        
        if has_opted_in or is_registered_user:
            # Customer has messaged us before OR is a registered business - send full invoice
            self._send_full_invoice(invoice, customer_phone, issuer_id)
            return False  # Full delivery completed
        else:
            # New customer - send template only with prompt to reply
            # Regular messages will fail, so we just send template and wait for reply
            self._send_template_only(invoice, customer_phone, issuer_id)
            return True  # Pending - waiting for customer to reply
    
    def _is_registered_user(self, phone: str) -> bool:
        """Check if a phone number belongs to a registered business user."""
        from app.models import models
        
        # Normalize phone for lookup
        normalized = phone.replace(" ", "").replace("-", "")
        if not normalized.startswith("+"):
            if normalized.startswith("0"):
                normalized = "+234" + normalized[1:]
            elif normalized.startswith("234"):
                normalized = "+" + normalized
            else:
                normalized = "+" + normalized
        
        # Check if phone exists in users table
        user = self.db.query(models.User).filter(models.User.phone == normalized).first()
        if user:
            logger.info("[NOTIFY] Customer phone %s is a registered user (ID: %s)", phone, user.id)
            return True
        return False

    def _send_template_only(self, invoice, customer_phone: str, issuer_id: int) -> None:
        """Send only the template to new customers who haven't messaged us yet."""
        customer_name = getattr(invoice.customer, "name", "valued customer") if invoice.customer else "valued customer"
        amount_text = f"₦{invoice.amount:,.2f}"
        items_text = self._build_items_text(invoice)
        
        # Add call-to-action for new customers to reply
        items_with_cta = f"{items_text}. Reply 'Hi' to get payment details"

        logger.info("[TEMPLATE] Sending template ONLY to new customer %s for invoice %s", customer_phone, invoice.invoice_id)
        template_sent = self._send_template(customer_phone, invoice.invoice_id, customer_name, amount_text, items_with_cta)
        
        if template_sent:
            # Mark invoice as pending follow-up delivery
            invoice.whatsapp_delivery_pending = True
            self.db.commit()
            logger.info("[TEMPLATE] Template sent, invoice marked pending for follow-up")
        else:
            logger.warning("[TEMPLATE] Failed to send template to %s", customer_phone)

    def _send_full_invoice(self, invoice, customer_phone: str, issuer_id: int) -> None:
        """Send full invoice with payment details to opted-in customers.
        
        Sends only 2 messages:
        1. Payment link with bank details
        2. Invoice PDF document
        """
        issuer = self._load_issuer(issuer_id)
        amount_text = f"₦{invoice.amount:,.2f}"

        logger.info("[NOTIFY] Sending full invoice to %s for invoice %s", customer_phone, invoice.invoice_id)
        
        # Message 1: Payment link with bank details
        payment_link = self._build_payment_link_message(invoice, issuer)
        self.client.send_text(customer_phone, payment_link)
        
        # Message 2: Invoice PDF document
        if invoice.pdf_url and invoice.pdf_url.startswith("http"):
            self.client.send_document(
                customer_phone,
                invoice.pdf_url,
                f"Invoice_{invoice.invoice_id}.pdf",
                f"Invoice {invoice.invoice_id} - {amount_text}",
            )
        
        # Clear pending flag if it was set
        if invoice.whatsapp_delivery_pending:
            invoice.whatsapp_delivery_pending = False
            self.db.commit()

    def handle_customer_optin(self, customer_phone: str) -> bool:
        """
        Handle when a customer replies to opt-in for WhatsApp messages.
        Marks customer as opted-in and sends payment details for recent invoices.
        
        Returns True if the sender is a customer with recent invoices.
        """
        from app.models import models
        import datetime as dt
        
        # Normalize phone number for lookup - handle all Nigerian formats
        clean_digits = "".join(ch for ch in customer_phone if ch.isdigit())
        candidates = {customer_phone}
        if customer_phone.startswith("+"):
            candidates.add(customer_phone[1:])
        if clean_digits:
            candidates.add(clean_digits)
            if clean_digits.startswith("234"):
                candidates.add(f"+{clean_digits}")
                # Also add local format (0xxx) - remove 234 prefix and add 0
                local_number = "0" + clean_digits[3:]
                candidates.add(local_number)
            elif clean_digits.startswith("0"):
                # Local format - also try international
                intl_number = "234" + clean_digits[1:]
                candidates.add(intl_number)
                candidates.add(f"+{intl_number}")
        
        logger.info("[OPTIN] Looking up customer with phone candidates: %s", candidates)
        
        # Find ALL customers matching any phone format (might have duplicates from before normalization)
        customers = (
            self.db.query(models.Customer)
            .filter(models.Customer.phone.in_(list(candidates)))
            .all()
        )
        
        if not customers:
            logger.info("[OPTIN] No customer found for phone %s", customer_phone)
            return False
        
        # Get all customer IDs
        customer_ids = [c.id for c in customers]
        logger.info("[OPTIN] Found %d customer record(s) for phone %s: %s", len(customers), customer_phone, customer_ids)
        
        # Mark all matching customers as opted in
        for customer in customers:
            if not customer.whatsapp_opted_in:
                customer.whatsapp_opted_in = True
        self.db.commit()
        logger.info("[OPTIN] Customer(s) %s opted in to WhatsApp", customer_phone)
        
        # Check if this phone also belongs to a registered business (issuer)
        # We'll exclude invoices where they're BOTH the issuer and customer (self-invoices/tests)
        issuer_id = self._resolve_issuer_id(customer_phone)
        
        # Find recent unpaid invoices for ANY of these customer records
        seven_days_ago = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)
        recent_invoices_query = (
            self.db.query(models.Invoice)
            .filter(
                models.Invoice.customer_id.in_(customer_ids),
                models.Invoice.status.in_(["pending", "awaiting_confirmation"]),
                models.Invoice.created_at >= seven_days_ago,
            )
        )
        
        # Exclude self-invoices: where the issuer is the same person messaging
        if issuer_id is not None:
            recent_invoices_query = recent_invoices_query.filter(
                models.Invoice.issuer_id != issuer_id
            )
            logger.info("[OPTIN] Excluding self-invoices for issuer_id=%s", issuer_id)
        
        recent_invoices = (
            recent_invoices_query
            .order_by(models.Invoice.created_at.desc())
            .limit(3)  # Max 3 recent invoices to avoid spam
            .all()
        )
        
        if not recent_invoices:
            logger.info("[OPTIN] No recent unpaid invoices for customer %s", customer_phone)
            
            # issuer_id already resolved above
            if issuer_id is not None:
                # They're both a customer AND a business - let them know about both roles
                self.client.send_text(
                    customer_phone,
                    "👋 Hi there!\n\n"
                    "📥 *As a customer:* No pending invoices at the moment.\n\n"
                    "📤 *As a business:* You can create invoices!\n"
                    "Example: `Invoice Joy 08012345678, 5000 wig`\n\n"
                    "Type *help* for full guide."
                )
            else:
                # Just a customer
                self.client.send_text(
                    customer_phone,
                    "👋 Thanks for your message! You don't have any pending invoices at the moment.\n\n"
                    "You'll receive invoice notifications here when a business sends you one."
                )
            return True
        
        # Send payment details for recent invoices
        self.client.send_text(
            customer_phone,
            f"👋 Thanks for your reply!\n\n"
            f"📄 Here are your pending invoice(s):"
        )
        
        # Send each invoice's payment details (just payment link, no PDF spam)
        for invoice in recent_invoices:
            issuer = self._load_issuer(invoice.issuer_id)
            amount_text = f"₦{invoice.amount:,.2f}"
            
            # Send payment link and bank details
            payment_msg = self._build_payment_link_message(invoice, issuer)
            self.client.send_text(customer_phone, f"📄 {invoice.invoice_id} - {amount_text}\n\n{payment_msg}")
            
            # Clear pending flag
            if invoice.whatsapp_delivery_pending:
                invoice.whatsapp_delivery_pending = False
        
        self.db.commit()
        
        # If they're also a business, remind them they can create invoices too
        # issuer_id already resolved above
        if issuer_id is not None:
            self.client.send_text(
                customer_phone,
                "💡 *Tip:* You're also a registered business!\n"
                "Type *help* to see how to create your own invoices."
            )
        
        return True

    def handle_customer_paid(self, customer_phone: str) -> bool:
        """
        Handle when a customer replies 'PAID' to confirm payment.
        Changes invoice status to awaiting_confirmation and notifies business.
        
        Returns True if handled (even if no invoice found - to prevent other processors).
        """
        from app.models import models
        from app.services.invoice_components.status import InvoiceStatusComponent
        import datetime as dt
        
        # Normalize phone number for lookup - build all possible formats
        clean_digits = "".join(ch for ch in customer_phone if ch.isdigit())
        candidates: set[str] = {customer_phone}
        if customer_phone.startswith("+"):
            candidates.add(customer_phone[1:])
        if clean_digits:
            candidates.add(clean_digits)
            if clean_digits.startswith("234"):
                candidates.add(f"+{clean_digits}")
                # Also add 0-prefixed local format
                candidates.add("0" + clean_digits[3:])
        
        logger.info("[PAID] Looking for customer with phone variants: %s", candidates)
        
        # Find ALL customers matching any phone format (might have duplicates)
        customers = (
            self.db.query(models.Customer)
            .filter(models.Customer.phone.in_(list(candidates)))
            .all()
        )
        
        if not customers:
            logger.info("[PAID] No customer found for phone %s", customer_phone)
            # Send helpful message and return True to prevent other processors
            self.client.send_text(
                customer_phone,
                "ℹ️ I couldn't find any invoices associated with your number.\n\n"
                "If you received an invoice, please use the payment link provided, "
                "or contact the business directly."
            )
            return True  # Return True to stop other processors
        
        # Get all customer IDs
        customer_ids = [c.id for c in customers]
        
        # Find the most recent pending invoice for ANY of these customers
        pending_invoice = (
            self.db.query(models.Invoice)
            .filter(
                models.Invoice.customer_id.in_(customer_ids),
                models.Invoice.status == "pending",
            )
            .order_by(models.Invoice.created_at.desc())
            .first()
        )
        
        if not pending_invoice:
            # Check if they have an awaiting_confirmation invoice already
            awaiting = (
                self.db.query(models.Invoice)
                .filter(
                    models.Invoice.customer_id.in_(customer_ids),
                    models.Invoice.status == "awaiting_confirmation",
                )
                .order_by(models.Invoice.created_at.desc())
                .first()
            )
            
            if awaiting:
                self.client.send_text(
                    customer_phone,
                    f"✅ Your payment for invoice {awaiting.invoice_id} is already being verified.\n\n"
                    "The business will confirm and send your receipt shortly."
                )
                return True
            
            self.client.send_text(
                customer_phone,
                "ℹ️ You don't have any pending invoices at the moment.\n\n"
                "If you just made a payment, please wait for the business to send an invoice."
            )
            return True
        
        # Use the status component to confirm transfer (same as clicking the button)
        status_component = InvoiceStatusComponent(self.db)
        try:
            status_component.confirm_transfer(pending_invoice.invoice_id)
            
            self.client.send_text(
                customer_phone,
                f"✅ Thank you! Your payment confirmation for invoice {pending_invoice.invoice_id} "
                f"(₦{pending_invoice.amount:,.2f}) has been sent to the business.\n\n"
                "📧 You'll receive your receipt once they verify the payment."
            )
            logger.info("[PAID] Customer %s confirmed payment for invoice %s", customer_phone, pending_invoice.invoice_id)
            return True
            
        except Exception as exc:
            logger.error("[PAID] Failed to confirm transfer: %s", exc)
            self.client.send_text(
                customer_phone,
                "❌ Sorry, there was an error processing your payment confirmation. Please try again or contact the business."
            )
            return True

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

    def _build_payment_link_message(self, invoice, issuer) -> str:
        """Build a message with payment link and bank details for customer."""
        frontend_url = getattr(settings, "FRONTEND_URL", "https://suoops.com")
        payment_link = f"{frontend_url.rstrip('/')}/pay/{invoice.invoice_id}"
        amount_text = f"₦{invoice.amount:,.2f}"
        
        message = f"📄 Your invoice for {amount_text} is ready!\n\n🔗 View & Pay Online:\n{payment_link}"
        
        # Add bank transfer details if available
        if issuer and issuer.bank_name and issuer.account_number:
            message += (
                f"\n\n💳 Or pay via Bank Transfer:\n"
                f"Bank: {issuer.bank_name}\n"
                f"Account: {issuer.account_number}"
            )
            if getattr(issuer, "account_name", None):
                message += f"\nName: {issuer.account_name}"
            message += "\n\n📝 After transfer, tap the link above and click 'I've sent the transfer'."
        
        return message

    def _send_paid_button(self, customer_phone: str, invoice_id: str, amount_text: str) -> bool:
        """Send an interactive button message for payment confirmation."""
        body = (
            f"💳 After making payment for {amount_text}, tap the button below to notify the business.\n\n"
            "This will send your payment confirmation instantly!"
        )
        
        buttons = [
            {"id": "confirm_paid", "title": "✅ I've Paid"},
        ]
        
        return self.client.send_interactive_buttons(
            to=customer_phone,
            body=body,
            buttons=buttons,
            footer=f"Invoice: {invoice_id}",
        )

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
                # Also add local format (0xxx) - remove 234 prefix and add 0
                local_number = "0" + clean_digits[3:]
                candidates.add(local_number)
            elif clean_digits.startswith("0"):
                # Local format - also try international
                intl_number = "234" + clean_digits[1:]
                candidates.add(intl_number)
                candidates.add(f"+{intl_number}")

        candidates = {c for c in candidates if c}
        if not candidates:
            return None
        
        logger.info("[RESOLVE_ISSUER] Looking for user with phone candidates: %s", candidates)

        # Only match users with VERIFIED phone numbers
        # This prevents someone from hijacking a number after another business removes it
        user = (
            self.db.query(models.User)
            .filter(
                models.User.phone.in_(list(candidates)),
                models.User.phone_verified == True,  # Must be verified!
            )
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
