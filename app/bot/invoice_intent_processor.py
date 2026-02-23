from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.bot.whatsapp_client import WhatsAppClient
from app.core.config import settings
from app.core.exceptions import InvoiceBalanceExhaustedError, MissingBankDetailsError
from app.services.invoice_service import build_invoice_service
from app.utils.currency_fmt import fmt_money, fmt_money_full, get_user_currency

logger = logging.getLogger(__name__)

# ── Pending-price session store ─────────────────────────────────
# When a user sends quantity-only items ("5 wig, 10 shoe") and has
# no product catalog, the bot asks for prices and stores state here.
# Same ephemeral pattern as product_invoice_flow._carts.

_PRICE_TTL = 900  # 15 minutes


@dataclass
class PendingPriceSession:
    """Ephemeral state for invoice items awaiting user price input."""

    user_id: int
    lines: list[dict[str, Any]]  # [{description, quantity}, ...]
    data: dict[str, Any]         # original parsed data (name, phone, etc.)
    created_at: float = field(default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > _PRICE_TTL


_pending_prices: dict[str, PendingPriceSession] = {}


def get_pending_price_session(phone: str) -> PendingPriceSession | None:
    """Get active pending-price session, or None if expired/missing."""
    session = _pending_prices.get(phone)
    if session and session.is_expired:
        del _pending_prices[phone]
        return None
    return session


def clear_pending_price_session(phone: str) -> None:
    """Remove pending-price session for phone."""
    _pending_prices.pop(phone, None)


class InvoiceIntentProcessor:
    """Handle the invoice creation intent extracted from NLP results."""

    def __init__(self, db: Session, client: WhatsAppClient):
        self.db = db
        self.client = client

    async def handle(self, sender: str, parse: Any, payload: dict[str, Any]) -> None:
        if getattr(parse, "intent", None) != "create_invoice":
            # Don't respond to non-invoice messages - let other processors handle them
            return

        data = getattr(parse, "entities", {})

        issuer_id = self._resolve_issuer_id(sender)
        if issuer_id is None:
            # Check if user exists but phone is unverified
            from app.models import models as _m
            clean_digits = "".join(ch for ch in sender if ch.isdigit())
            phone_candidates: set[str] = {sender}
            if sender.startswith("+"):
                phone_candidates.add(sender[1:])
            if clean_digits:
                phone_candidates.add(clean_digits)
                if clean_digits.startswith("234"):
                    phone_candidates.add(f"+{clean_digits}")
                    phone_candidates.add("0" + clean_digits[3:])
            unverified_user = (
                self.db.query(_m.User)
                .filter(
                    _m.User.phone.in_(list(phone_candidates)),
                    _m.User.phone_verified.is_(False),
                )
                .first()
            )
            if unverified_user:
                logger.info("Unverified phone for user %s (sender: %s)", unverified_user.id, sender)
                self.client.send_text(
                    sender,
                    "📱 *Almost there! Verify your phone first.*\n\n"
                    "Your account exists but your WhatsApp number isn't verified yet.\n\n"
                    "1. Go to suoops.com/dashboard/settings\n"
                    "2. Click *Verify Phone*\n"
                    "3. Enter the OTP code you receive\n\n"
                    "Once verified, come back and send your invoice! 🚀",
                )
            else:
                logger.warning("Unable to resolve issuer for WhatsApp sender: %s", sender)
                self.client.send_text(
                    sender,
                    "👋 Hi! I don't recognise this number yet.\n\n"
                    "📲 *Already have an account?*\n"
                    "Make sure this WhatsApp number is added & verified "
                    "in your profile at suoops.com/dashboard/settings\n\n"
                    "🆕 *New to SuoOps?*\n"
                    "Register free at suoops.com — start sending invoices "
                    "via WhatsApp in under 2 minutes!",
                )
            return

        invoice_service = build_invoice_service(self.db, user_id=issuer_id)

        if not self._enforce_quota(invoice_service, issuer_id, sender):
            return

        await self._create_invoice(invoice_service, issuer_id, sender, data, payload)

    def _enforce_quota(self, invoice_service, issuer_id: int, sender: str) -> bool:
        """Check invoice balance before creating invoice. Returns (can_create, balance)."""
        try:
            quota_check = invoice_service.check_invoice_quota(issuer_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to check quota: %s", exc)
            return True

        balance = quota_check.get("invoice_balance", 0)

        # Don't show warning here - we'll show remaining count AFTER successful creation
        # This prevents confusing UX when invoice creation succeeds

        if quota_check.get("can_create"):
            return True

        # No balance remaining
        limit_message = (
            "🚫 No Invoices Remaining!\n\n"
            f"Plan: {quota_check.get('plan', '').upper()}\n"
            f"Balance: {balance} invoices\n\n"
            f"💳 Purchase a pack: ₦{quota_check.get('pack_price', 2500):,} "
            f"for {quota_check.get('pack_size', 100)} invoices\n\n"
            "Visit suoops.com/dashboard/billing/purchase to buy more."
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
        # ── Resolve prices from inventory for quantity-only items ──
        amount = data.get("amount", 0)
        lines = data.get("lines", [])
        needs_price = any(l.get("unit_price") is None for l in lines)

        if needs_price and lines:
            resolved = self._resolve_prices_from_inventory(
                issuer_id, lines, sender, data=data,
            )
            if resolved is None:
                return  # error already sent to user
            data["lines"] = resolved
            from decimal import Decimal

            amount = sum(
                Decimal(str(l["unit_price"])) * l.get("quantity", 1)
                for l in resolved
            )
            data["amount"] = amount

        # ── Guard: reject zero / trivially-small amounts early ──
        amount = data.get("amount", 0)
        if not amount or amount <= 0:
            self.client.send_text(
                sender,
                "❌ I couldn't find an amount in your message.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "✅ *CORRECT FORMAT:*\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "`Invoice [Name] [Phone], [Amount] [Item]`\n\n"
                "📋 *EXAMPLES:*\n"
                "• `Invoice Joy 08012345678, 12000 wig`\n"
                "• `Invoice Ada 5000 braids, 2000 gel`\n\n"
                "💡 *TIP:* Amount should be a number (e.g. 5000, not five thousand)",
            )
            return

        if amount < 100:
            currency = get_user_currency(self.db, issuer_id)
            self.client.send_text(
                sender,
                f"⚠️ Amount {fmt_money(amount, currency)} seems too low.\n\n"
                "Minimum invoice amount is ₦100.\n"
                "Did you mean a larger number?\n\n"
                "💡 *TIP:* Amount should be a number (e.g. 5000 or 5,000)",
            )
            return

        # ── Guard: missing customer name ──
        customer_name = data.get("customer_name", "")
        if not customer_name or customer_name == "Customer":
            self.client.send_text(
                sender,
                "❌ I couldn't find a customer name.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "✅ *CORRECT FORMAT:*\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "`Invoice [Name] [Phone], [Amount] [Item]`\n\n"
                "📋 *EXAMPLES:*\n"
                "• `Invoice Joy 08012345678, 12000 wig`\n"
                "• `Invoice Ada 5000 braids`\n\n"
                "💡 *TIP:* Customer name comes right after the word 'Invoice'",
            )
            return

        # Check for potentially malformed amounts BEFORE creating invoice
        lines = data.get("lines", [])
        
        # Detect suspicious patterns that suggest parsing errors
        is_suspicious = False
        suspicious_reason = ""
        
        # 1. Very small amount with multiple line items could mean comma-formatting issues
        if amount < 500 and len(lines) >= 2:
            is_suspicious = True
            suspicious_reason = "very small total with multiple items"
        
        # 2. Amount that looks like a partial number (e.g., 244 instead of 11,244)
        if 100 <= amount < 1000 and len(lines) == 1:
            # Could be intentional (small item) or parsing error - just log
            logger.info("Small invoice amount ₦%s - may be intentional or parsing issue", amount)
        
        # 3. Suspiciously large amounts (possible concatenation error like 9,422,244)
        if amount > 5_000_000:
            is_suspicious = True
            suspicious_reason = "unusually large amount"
        
        if is_suspicious:
            logger.warning(
                "Suspicious invoice amount ₦%s (%s) - raw data: %s",
                amount, suspicious_reason, data
            )
            currency = get_user_currency(self.db, issuer_id)
            # Send format reminder but continue with creation (user may know what they're doing)
            self.client.send_text(
                sender,
                f"⚠️ Heads up: The total is {fmt_money_full(amount, currency)}\n\n"
                "If this looks wrong, cancel and try again with this format:\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "✅ *CORRECT FORMAT:*\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "`Invoice [Name] [Phone] [Amount] [Item], [Amount] [Item]`\n\n"
                "📋 *EXAMPLES:*\n"
                "• `Invoice Joy 08012345678 11000 Design, 10000 Printing, 1000 Delivery`\n"
                "• `Invoice Ada 08098765432 5000 braids, 2000 gel`\n\n"
                "💡 *TIP:* Put amount BEFORE item name, separate items with commas\n\n"
                "Creating invoice anyway..."
            )
        
        try:
            invoice = invoice_service.create_invoice(issuer_id=issuer_id, data=data)
        except InvoiceBalanceExhaustedError as exc:
            # Invoice balance exhausted - caught by exception type
            logger.warning("Invoice balance exhausted for user %s: %s", issuer_id, exc)
            self.client.send_text(
                sender,
                "🚫 No invoices remaining!\n\n"
                "Purchase a pack: ₦2,500 for 100 invoices\n"
                "Visit: suoops.com/dashboard/billing/purchase",
            )
            return
        except MissingBankDetailsError:
            logger.warning("Missing bank details for user %s", issuer_id)
            self.client.send_text(
                sender,
                "🏦 *Please add your bank details first!*\n\n"
                "Your invoice message is correct ✅ but I need your bank "
                "account info to include on the invoice.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "📱 *How to add:*\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "1. Go to suoops.com/dashboard/settings\n"
                "2. Add your *Bank Name*\n"
                "3. Add your *Account Number*\n"
                "4. Add your *Account Name*\n\n"
                "Once done, come back and send your invoice again! 🚀",
            )
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to create invoice")
            error_msg = str(exc).lower()
            
            # Invoice balance exhausted (fallback string check)
            if "invoice_balance_exhausted" in error_msg or "inv005" in error_msg:
                self.client.send_text(
                    sender,
                    "🚫 No invoices remaining!\n\n"
                    "Purchase a pack: ₦2,500 for 100 invoices\n"
                    "Visit: suoops.com/dashboard/billing/purchase",
                )
            # Missing amount
            elif "amount" in error_msg or data.get("amount", 0) == 0:
                self.client.send_text(
                    sender,
                    "❌ I couldn't find a valid amount in your message.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    "✅ *CORRECT FORMAT:*\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "`Invoice [Name] [Phone], [Amount] [Item]`\n\n"
                    "📱 *WITH PHONE:*\n"
                    "• `Invoice Joy 08012345678, 12000 wig`\n"
                    "• `Invoice Ada 08098765432, 5000 braids, 2000 gel`\n\n"
                    "📝 *WITHOUT PHONE:*\n"
                    "• `Invoice Joy 12000 wig`\n"
                    "• `Invoice Mike 8000 shirt`\n\n"
                    "💡 *TIP:* The amount must be at least ₦100"
                )
            # Missing customer name
            elif (
                "customer" in error_msg
                or "name" in error_msg
                or not data.get("customer_name")
                or data.get("customer_name") == "Customer"
            ):
                self.client.send_text(
                    sender,
                    "❌ Please include a customer name.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    "✅ *CORRECT FORMAT:*\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "`Invoice [Name] [Phone], [Amount] [Item]`\n\n"
                    "📋 *EXAMPLES:*\n"
                    "• `Invoice Joy 08012345678, 12000 wig`\n"
                    "• `Invoice Ada 5000 braids` (no phone)\n"
                    "• `Invoice Mike 08091234567, 25000 consulting`\n\n"
                    "💡 *TIP:* Customer name should come right after 'Invoice'"
                )
            # Database errors
            elif "not-null" in error_msg or "constraint" in error_msg:
                self.client.send_text(
                    sender,
                    "❌ Something was missing from your invoice.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    "✅ *CORRECT FORMAT:*\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "`Invoice [Name] [Phone], [Amount] [Item]`\n\n"
                    "📋 *COMPLETE EXAMPLES:*\n"
                    "• `Invoice Joy 08012345678, 12000 wig`\n"
                    "• `Invoice Ada 08098765432, 5000 braids, 2000 gel`\n"
                    "• `Invoice Mike 25000 consulting`\n\n"
                    "💡 *TIP:* Type *help* to see the full guide"
                )
            # Connection errors
            elif "connection" in error_msg or "timeout" in error_msg:
                self.client.send_text(
                    sender,
                    "❌ Network issue. Please try again in a moment."
                )
            # Missing bank details (fallback string check)
            elif "bank" in error_msg or "inv004" in error_msg:
                self.client.send_text(
                    sender,
                    "🏦 *Please add your bank details first!*\n\n"
                    "Your invoice message is correct ✅ but I need your bank "
                    "account info to include on the invoice.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    "📱 *How to add:*\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "1. Go to suoops.com/dashboard/settings\n"
                    "2. Add your *Bank Name*\n"
                    "3. Add your *Account Number*\n"
                    "4. Add your *Account Name*\n\n"
                    "Once done, come back and send your invoice again! 🚀",
                )
            # Generic fallback - provide comprehensive guide
            else:
                self.client.send_text(
                    sender,
                    "❌ Sorry, I couldn't create that invoice.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    "✅ *CORRECT FORMAT:*\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "`Invoice [Name] [Phone], [Amount] [Item]`\n\n"
                    "📱 *WITH PHONE NUMBER:*\n"
                    "• `Invoice Joy 08012345678, 12000 wig`\n"
                    "• `Invoice Ada 08098765432, 5000 braids, 2000 gel`\n\n"
                    "📝 *WITHOUT PHONE:*\n"
                    "• `Invoice Joy 12000 wig`\n"
                    "• `Invoice Mike 25000 consulting`\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    "💡 *TIPS:*\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "• Use the word 'Invoice' to start\n"
                    "• Include customer name, amount, and item description\n"
                    "• Phone number is optional but needed for WhatsApp notifications\n"
                    "• Type *help* anytime for the full guide"
                )
            return

        # Send notifications via all channels (Email only - WhatsApp handled separately by _notify_customer)
        customer_email = data.get("customer_email")
        customer_phone = data.get("customer_phone")
        
        # Track if there's no contact info at all
        no_contact_info = not customer_email and not customer_phone
        
        # Only send email notification here - WhatsApp is handled by _notify_customer to avoid duplicates
        results = {"email": False, "whatsapp": False}
        if customer_email:
            try:
                from app.services.notification.service import NotificationService
                service = NotificationService()
                results["email"] = await service.send_invoice_email(invoice, customer_email, invoice.pdf_url)
            except Exception as exc:
                logger.error("Failed to send invoice email: %s", exc)

        whatsapp_pending = self._notify_customer(invoice, data, issuer_id) if customer_phone else False
        self._notify_business(sender, invoice, invoice_service, issuer_id, customer_email, results, whatsapp_pending, no_contact_info)

    def _notify_business(
        self,
        sender: str,
        invoice,
        invoice_service,
        issuer_id: int,
        customer_email: str | None = None,
        notification_results: dict[str, bool] | None = None,
        whatsapp_pending: bool = False,
        no_contact_info: bool = False
    ) -> None:
        customer_name = getattr(invoice.customer, "name", "N/A") if invoice.customer else "N/A"
        
        # Show appropriate status label
        status_display = (
            "Awaiting Payment Confirmation"
            if invoice.status == "awaiting_confirmation"
            else invoice.status.replace("_", " ").title()
        )
        
        # Get remaining invoice balance
        remaining_balance = None
        quota_check = None
        try:
            quota_check = invoice_service.check_invoice_quota(issuer_id)
            remaining_balance = quota_check.get("invoice_balance", 0)
        except Exception:
            pass
        
        # Format due date for display
        due_display = ""
        if invoice.due_date:
            due_display = f"📅 Due: {invoice.due_date.strftime('%d %b %Y')}\n"

        # Display amount in the invoice's own currency
        inv_currency = getattr(invoice, "currency", "NGN") or "NGN"

        business_message = (
            f"✅ Invoice {invoice.invoice_id} created!\n\n"
            f"💰 Amount: {fmt_money_full(invoice.amount, inv_currency, convert=False)}\n"
            f"👤 Customer: {customer_name}\n"
            f"{due_display}"
            f"📊 Status: {status_display}\n"
        )
        
        # Show remaining invoice count
        if remaining_balance is not None:
            if remaining_balance <= 5:
                business_message += f"📉 Invoices remaining: {remaining_balance}\n"
            else:
                business_message += f"📊 Invoices remaining: {remaining_balance}\n"
        
        # Show notification status
        if no_contact_info:
            business_message += (
                "\n📝 No phone/email provided.\n"
                "⏳ Awaiting payment confirmation.\n"
                f"💡 Click 'Mark Paid' when customer pays: suoops.com/dashboard/invoices/{invoice.invoice_id}"
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
                f"📄 Invoice {invoice.invoice_id} - {fmt_money_full(invoice.amount, inv_currency, convert=False)}",
            )
        
        # Show low balance warning AFTER successful creation (better UX)
        if remaining_balance is not None and 0 < remaining_balance <= 5:
            pack_price = quota_check.get("pack_price", 2500) if quota_check else 2500
            pack_size = quota_check.get("pack_size", 100) if quota_check else 100
            self.client.send_text(
                sender,
                f"⚠️ Running low on invoices!\n\n"
                f"You have {remaining_balance} invoice{'s' if remaining_balance != 1 else ''} left.\n\n"
                f"💳 Buy more: ₦{pack_price:,} for {pack_size} invoices\n"
                "Visit: suoops.com/dashboard/billing/purchase"
            )

    def _notify_customer(self, invoice, data: dict[str, Any], issuer_id: int) -> bool:
        """
        Notify customer about their invoice via WhatsApp.

        ALWAYS uses template messages when configured because we cannot know
        server-side whether Meta's 24-hour messaging window is open.  Regular
        (non-template) messages silently fail with error 131047 when the
        window is closed.

        Returns True when a template was sent, False otherwise.
        """
        customer_phone = data.get("customer_phone")
        logger.info("[NOTIFY] customer_phone from data: %s, invoice: %s", customer_phone, invoice.invoice_id)
        if not customer_phone:
            logger.warning("No customer phone for invoice %s", invoice.invoice_id)
            return False

        # Log opt-in status for debugging (but don't branch on it)
        customer = getattr(invoice, "customer", None)
        if customer:
            logger.info(
                "[NOTIFY] Customer check: id=%s, phone=%s, whatsapp_opted_in=%s",
                getattr(customer, "id", "?"),
                getattr(customer, "phone", "?"),
                getattr(customer, "whatsapp_opted_in", False),
            )
        else:
            logger.warning("[NOTIFY] No customer object on invoice %s", invoice.invoice_id)

        # Always prefer template messages -- they work outside the 24-hour
        # messaging window.  The template opens a new window so the PDF
        # document sent right after will also be delivered.
        has_template = bool(
            getattr(settings, "WHATSAPP_TEMPLATE_INVOICE_PAYMENT", None)
            or getattr(settings, "WHATSAPP_TEMPLATE_INVOICE", None)
        )

        if has_template:
            logger.info(
                "[NOTIFY] Sending template to customer %s for invoice %s",
                customer_phone,
                invoice.invoice_id,
            )
            self._send_template_only(invoice, customer_phone, issuer_id)
            invoice.whatsapp_delivery_pending = True
            self.db.commit()
            return True

        # No templates configured -- fall back to regular messages (best effort).
        logger.warning(
            "[NOTIFY] No WhatsApp templates configured. "
            "Falling back to regular message for customer %s (invoice %s). "
            "Set WHATSAPP_TEMPLATE_INVOICE_PAYMENT or WHATSAPP_TEMPLATE_INVOICE env vars.",
            customer_phone,
            invoice.invoice_id,
        )
        self._send_full_invoice(invoice, customer_phone, issuer_id)
        return False

    def _send_template_only(self, invoice, customer_phone: str, issuer_id: int) -> None:
        """Send invoice template with full payment details.
        
        Uses 'invoice_with_payment' template if configured (includes bank details),
        falls back to basic 'invoice_notification' template.
        """
        customer_name = getattr(invoice.customer, "name", "valued customer") if invoice.customer else "valued customer"
        amount_text = fmt_money_full(invoice.amount, getattr(invoice, "currency", "NGN") or "NGN", convert=False)
        items_text = self._build_items_text(invoice)
        
        # Try the full invoice template with payment details first
        template_name = getattr(settings, "WHATSAPP_TEMPLATE_INVOICE_PAYMENT", None)
        fallback_template = getattr(settings, "WHATSAPP_TEMPLATE_INVOICE", None)
        
        logger.info(
            "[BOT TEMPLATE] Config - INVOICE_PAYMENT='%s', INVOICE='%s'",
            template_name, fallback_template
        )
        
        if template_name:
            # Use the full template with bank details
            logger.info("[BOT TEMPLATE] Using invoice_with_payment template: %s", template_name)
            issuer = self._load_issuer(issuer_id)
            bank_name = getattr(issuer, "bank_name", "N/A") if issuer else "N/A"
            account_number = getattr(issuer, "account_number", "N/A") if issuer else "N/A"
            account_name = getattr(issuer, "account_name", "N/A") if issuer else "N/A"
            
            frontend_url = getattr(settings, "FRONTEND_URL", "https://suoops.com")
            payment_link = f"{frontend_url.rstrip('/')}/pay/{invoice.invoice_id}"
            
            logger.info(
                "[TEMPLATE] Sending full invoice template to %s for invoice %s",
                customer_phone,
                invoice.invoice_id,
            )
            template_sent = self._send_full_invoice_template(
                customer_phone,
                customer_name,
                invoice.invoice_id,
                amount_text,
                items_text,
                bank_name,
                account_number,
                account_name,
                payment_link,
                template_name,
            )
        else:
            # Fall back to basic template with CTA to reply
            items_with_cta = f"{items_text}. Reply 'Hi' to get payment details"
            logger.info(
                "[TEMPLATE] Sending basic template to %s for invoice %s",
                customer_phone,
                invoice.invoice_id,
            )
            template_sent = self._send_template(
                customer_phone,
                invoice.invoice_id,
                customer_name,
                amount_text,
                items_with_cta,
            )
        
        if template_sent:
            logger.info("[TEMPLATE] Template sent successfully to %s", customer_phone)
            # Send the PDF document right after the template.
            # The template opens a 24-hour messaging window, so the document
            # send is allowed immediately after the template is delivered.
            if invoice.pdf_url and invoice.pdf_url.startswith("http"):
                amount_text_pdf = fmt_money_full(invoice.amount, getattr(invoice, "currency", "NGN") or "NGN", convert=False)
                self.client.send_document(
                    customer_phone,
                    invoice.pdf_url,
                    f"Invoice_{invoice.invoice_id}.pdf",
                    f"Invoice {invoice.invoice_id} - {amount_text_pdf}",
                )
                logger.info("[TEMPLATE] PDF sent to customer %s for invoice %s", customer_phone, invoice.invoice_id)
            else:
                logger.warning("[TEMPLATE] No PDF URL available for invoice %s, skipping PDF send", invoice.invoice_id)
        else:
            logger.error(
                "[TEMPLATE] Failed to send template to %s for invoice %s. "
                "Check WHATSAPP_TEMPLATE_INVOICE / WHATSAPP_TEMPLATE_INVOICE_PAYMENT env vars.",
                customer_phone,
                invoice.invoice_id,
            )

    def _send_full_invoice(self, invoice, customer_phone: str, issuer_id: int) -> None:
        """Send full invoice with payment details to opted-in customers.
        
        Sends only 2 messages:
        1. Payment link with bank details
        2. Invoice PDF document
        """
        issuer = self._load_issuer(issuer_id)
        amount_text = fmt_money_full(invoice.amount, getattr(invoice, "currency", "NGN") or "NGN", convert=False)

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
        import datetime as dt

        from app.models import models
        
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
        logger.info(
            "[OPTIN] Found %d customer record(s) for phone %s: %s",
            len(customers),
            customer_phone,
            customer_ids,
        )
        
        # Mark all matching customers as opted in
        for customer in customers:
            if not customer.whatsapp_opted_in:
                customer.whatsapp_opted_in = True
        self.db.commit()
        logger.info("[OPTIN] Customer(s) %s opted in to WhatsApp", customer_phone)
        
        # Check if this phone also belongs to a registered business (issuer)
        # We'll exclude invoices where they're BOTH the issuer and customer (self-invoices/tests)
        issuer_id = self._resolve_issuer_id(customer_phone)
        
        # Find invoices with whatsapp_delivery_pending=True - these are the ones just sent
        # via template that the customer is replying "OK" to
        recent_invoices_query = (
            self.db.query(models.Invoice)
            .filter(
                models.Invoice.customer_id.in_(customer_ids),
                models.Invoice.status.in_(["pending", "awaiting_confirmation"]),
                models.Invoice.whatsapp_delivery_pending == True,  # noqa: E712
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
            .limit(1)  # Only the most recent invoice awaiting PDF delivery
            .all()
        )
        
        if not recent_invoices:
            logger.info("[OPTIN] No recent unpaid invoices for customer %s", customer_phone)
            
            # issuer_id already resolved above
            if issuer_id is not None:
                # They're a registered business - let the greeting handler deal with them
                # Return False so the adapter can send the appropriate business greeting
                logger.info("[OPTIN] User is a business with no pending invoices, deferring to greeting")
                return False
            else:
                # Just a customer with no pending invoices
                self.client.send_text(
                    customer_phone,
                    "👋 Thanks for your message!\n\n"
                    "No pending invoices right now. You'll get a notification here when a "
                    "business sends you one."
                )
            return True
        
        # Send the invoice PDF - customer already has payment details from template
        invoice = recent_invoices[0]  # We only query 1 now
        amount_text = fmt_money_full(invoice.amount, getattr(invoice, "currency", "NGN") or "NGN", convert=False)
        
        logger.info("[OPTIN] Sending PDF for invoice %s", invoice.invoice_id)
        
        # Send a simple confirmation with the PDF
        if invoice.pdf_url and invoice.pdf_url.startswith("http"):
            self.client.send_text(
                customer_phone,
                f"📄 Here's your invoice:"
            )
            self.client.send_document(
                customer_phone,
                invoice.pdf_url,
                f"Invoice_{invoice.invoice_id}.pdf",
                f"Invoice {invoice.invoice_id} - {amount_text}",
            )
        else:
            # No PDF available - just acknowledge
            self.client.send_text(
                customer_phone,
                f"✅ Thanks! Invoice {invoice.invoice_id} for {amount_text} is ready.\n\n"
                "Use the payment link above to pay."
            )
        
        # Mark as delivered
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
                f"({fmt_money_full(pending_invoice.amount, getattr(pending_invoice, 'currency', 'NGN') or 'NGN', convert=False)}) has been sent to the business.\n\n"
                "📧 You'll receive your receipt once they verify the payment."
            )
            logger.info(
                "[PAID] Customer %s confirmed payment for invoice %s",
                customer_phone,
                pending_invoice.invoice_id,
            )
            return True
            
        except Exception as exc:
            logger.error("[PAID] Failed to confirm transfer: %s", exc)
            self.client.send_text(
                customer_phone,
                (
                    "❌ Sorry, there was an error processing your payment confirmation. "
                    "Please try again or contact the business."
                ),
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
        amount_text = fmt_money_full(invoice.amount, getattr(invoice, "currency", "NGN") or "NGN", convert=False)
        biz_name = getattr(issuer, "business_name", None) or getattr(issuer, "name", "your vendor")

        # Build a line-items summary (max 3 lines)
        items_summary = ""
        inv_lines = getattr(invoice, "lines", None) or []
        if inv_lines:
            summaries = [f"  • {l.description}" for l in inv_lines[:3]]
            if len(inv_lines) > 3:
                summaries.append(f"  … and {len(inv_lines) - 3} more")
            items_summary = "\n".join(summaries)

        message = f"📄 *Invoice from {biz_name}*\nAmount: *{amount_text}*"
        if items_summary:
            message += f"\n\n📋 Items:\n{items_summary}"
        message += f"\n\n🔗 View & Pay Securely:\n{payment_link}"

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
        message += f"\n\n🔒 _Powered by Suoops — suoops.com_"

        return message

    def _send_template(
        self,
        customer_phone: str,
        invoice_id: str,
        customer_name: str,
        amount_text: str,
        items_text: str,
    ) -> bool:
        template_name = getattr(settings, "WHATSAPP_TEMPLATE_INVOICE", None)
        logger.info(
            "[TEMPLATE] template_name=%s, language=%s",
            template_name,
            getattr(settings, "WHATSAPP_TEMPLATE_LANGUAGE", "en_US"),
        )
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
            language=getattr(settings, "WHATSAPP_TEMPLATE_LANGUAGE", "en"),
            components=components,
        )

    def _send_full_invoice_template(
        self,
        customer_phone: str,
        customer_name: str,
        invoice_id: str,
        amount_text: str,
        items_text: str,
        bank_name: str,
        account_number: str,
        account_name: str,
        payment_link: str,
        template_name: str,
    ) -> bool:
        """Send the full invoice template with bank details and payment link."""
        # 8 parameters: customer_name, invoice_id, amount, items, bank, account, account_name, payment_link
        components = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": customer_name},
                    {"type": "text", "text": invoice_id},
                    {"type": "text", "text": amount_text},
                    {"type": "text", "text": items_text},
                    {"type": "text", "text": bank_name},
                    {"type": "text", "text": account_number},
                    {"type": "text", "text": account_name},
                    {"type": "text", "text": payment_link},
                ],
            }
        ]

        return self.client.send_template(
            customer_phone,
            template_name=template_name,
            language=getattr(settings, "WHATSAPP_TEMPLATE_LANGUAGE", "en"),
            components=components,
        )

    # ── Inventory price resolution ──────────────────────────────────

    def _resolve_prices_from_inventory(
        self,
        issuer_id: int,
        lines: list[dict[str, Any]],
        sender: str,
        *,
        data: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]] | None:
        """Resolve unit prices for quantity-only line items from inventory.

        Returns the resolved lines list on success, or *None* if resolution
        failed (an error/prompt is sent to the user in that case).

        When *data* is provided and there is no product catalog (or no
        matches at all), the bot starts a conversational price-gathering
        session instead of simply blocking.
        """
        from decimal import Decimal

        from app.bot.product_invoice_flow import _fuzzy_match_product
        from app.services.inventory.product_service import ProductService

        try:
            product_svc = ProductService(self.db, issuer_id)
            products, _ = product_svc.list_products(page=1, page_size=50)
        except Exception:
            logger.warning("Could not load products for user %s", issuer_id)
            products = []

        if not products:
            # No inventory — ask user for prices conversationally
            if data is not None:
                self._start_pending_price_session(sender, issuer_id, lines, data)
            else:
                item_names = ", ".join(
                    l.get("description", "item") for l in lines
                )
                self.client.send_text(
                    sender,
                    f"❌ I see quantities for *{item_names}* but no prices.\n\n"
                    "Include prices like:\n"
                    "   `Invoice Tonye 08012345678, 5000 wig, 3000 shoe`",
                )
            return None

        product_cache: list[tuple[str, Any]] = [
            (p.name.lower(), p) for p in products
        ]

        resolved: list[dict[str, Any]] = []
        unmatched: list[str] = []

        for line in lines:
            desc = (line.get("description") or "").lower().strip()
            qty = line.get("quantity", 1)

            match = _fuzzy_match_product(desc, product_cache)
            if match and match.selling_price:
                resolved.append({
                    "description": match.name,
                    "quantity": qty,
                    "unit_price": Decimal(str(match.selling_price)),
                    "product_id": match.id,
                })
            else:
                unmatched.append(line.get("description", "item"))

        if unmatched:
            missing = ", ".join(unmatched)
            currency = get_user_currency(self.db, issuer_id)

            # If SOME matched, show what we found
            if resolved:
                found = ", ".join(
                    f"{r['quantity']}x {r['description']} ({fmt_money(r['unit_price'], currency, convert=False)})"
                    for r in resolved
                )
                self.client.send_text(
                    sender,
                    f"⚠️ I found some items but not all:\n"
                    f"✅ {found}\n"
                    f"❌ Not found: *{missing}*\n\n"
                    "💡 *Fix:* Add prices for the missing items:\n"
                    f"  `Invoice ..., 5000 {unmatched[0].lower()}`\n\n"
                    "Or type *products* to add them to your catalog.",
                )
            else:
                # Nothing matched — ask for prices conversationally
                if data is not None:
                    self._start_pending_price_session(sender, issuer_id, lines, data)
                else:
                    self.client.send_text(
                        sender,
                        f"❌ I couldn't find *{missing}* in your product catalog.\n\n"
                        "Include prices like:\n"
                        "   `Invoice Tonye 08012345678, 5000 wig, 3000 shoe`",
                    )
            return None

        return resolved

    # ── Conversational price gathering ──────────────────────────────

    def _start_pending_price_session(
        self,
        sender: str,
        issuer_id: int,
        lines: list[dict[str, Any]],
        data: dict[str, Any],
    ) -> None:
        """Store a pending-price session and prompt user for prices."""
        session = PendingPriceSession(
            user_id=issuer_id,
            lines=[
                {
                    "description": l.get("description", "item"),
                    "quantity": l.get("quantity", 1),
                }
                for l in lines
            ],
            data={k: v for k, v in data.items() if k not in ("lines", "amount")},
        )
        _pending_prices[sender] = session

        items_list = "\n".join(
            f"  {i + 1}. {l['description'].title()} (×{l['quantity']})"
            for i, l in enumerate(session.lines)
        )
        customer = data.get("customer_name", "your customer")
        n = len(session.lines)
        example = ", ".join(["5000"] * n)

        self.client.send_text(
            sender,
            f"📝 *Invoice for {customer}*\n\n"
            f"I see {n} item{'s' if n > 1 else ''} but need prices:\n"
            f"{items_list}\n\n"
            f"💰 *Reply with the price per item:*\n"
            f"  e.g. `{example}`\n\n"
            f"Type *cancel* to start over.",
        )

    async def handle_price_reply(self, sender: str, text: str) -> bool:
        """Handle a price reply for pending quantity-only items.

        Returns *True* if the message was handled, *False* if there is
        no active pending-price session.
        """
        session = get_pending_price_session(sender)
        if not session:
            return False

        prices = self._parse_price_reply(text, session.lines)
        if prices is None:
            n = len(session.lines)
            items_list = "\n".join(
                f"  {i + 1}. {l['description'].title()} (×{l['quantity']})"
                for i, l in enumerate(session.lines)
            )
            self.client.send_text(
                sender,
                f"🤔 I couldn't read the prices.\n\n"
                f"Items:\n{items_list}\n\n"
                f"Reply with {n} price{'s' if n > 1 else ''} separated by commas:\n"
                f"  e.g. `{', '.join(['5000'] * n)}`\n\n"
                f"Type *cancel* to start over.",
            )
            return True

        from decimal import Decimal

        resolved_lines: list[dict[str, Any]] = []
        total = Decimal("0")
        for line, price in zip(session.lines, prices):
            unit_price = Decimal(str(price))
            qty = line.get("quantity", 1)
            resolved_lines.append(
                {
                    "description": line["description"],
                    "quantity": qty,
                    "unit_price": unit_price,
                }
            )
            total += unit_price * qty

        # Rebuild the full data dict
        data: dict[str, Any] = dict(session.data)
        data["lines"] = resolved_lines
        data["amount"] = total

        clear_pending_price_session(sender)

        issuer_id = session.user_id
        invoice_service = build_invoice_service(self.db, user_id=issuer_id)
        if self._enforce_quota(invoice_service, issuer_id, sender):
            await self._create_invoice(invoice_service, issuer_id, sender, data, {})

        return True

    @staticmethod
    def _parse_price_reply(
        text: str, lines: list[dict[str, Any]]
    ) -> list[float] | None:
        """Extract prices from a user's reply.

        Handles:
          • ``5000, 3000, 2000``       (comma-separated)
          • ``5,000  3,000  2,000``    (thousand-formatted, space-sep)
          • ``5000 wig, 3000 shoe``    (price + item name)
          • ``5000``                   (single item)

        Returns a list matching the order of *lines*, or *None*.
        """
        text = text.strip()
        n = len(lines)

        # Normalise thousand-separator commas: "5,000" → "5000"
        cleaned = re.sub(r"(\d),(\d{3})(?!\d)", r"\1\2", text)
        cleaned = re.sub(r"(\d),(\d{3})(?!\d)", r"\1\2", cleaned)  # e.g. 1,000,000

        raw_numbers = re.findall(r"\d+(?:\.\d+)?", cleaned)
        numbers = [float(x) for x in raw_numbers]

        # Exact count → positional mapping
        if len(numbers) == n:
            return numbers

        # More numbers than items → try matching by item name
        if len(numbers) > n:
            parts = re.split(r"[,\n]", cleaned)
            matched: list[float] = []
            for line in lines:
                desc = (line.get("description") or "").lower().strip()
                for part in parts:
                    part_lower = part.lower().strip()
                    part_nums = re.findall(r"\d+(?:\.\d+)?", part)
                    if part_nums and desc in part_lower:
                        matched.append(float(part_nums[0]))
                        break
            if len(matched) == n:
                return matched

        # Single item, at least one number
        if n == 1 and numbers:
            return [numbers[0]]

        return None

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
                models.User.phone_verified.is_(True),  # Must be verified!
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
