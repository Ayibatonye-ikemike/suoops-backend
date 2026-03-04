from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.bot.expense_intent_processor import ExpenseIntentProcessor
from app.bot.invoice_intent_processor import (
    InvoiceIntentProcessor,
    clear_pending_price_session,
    get_pending_price_session,
)
from app.bot.message_extractor import extract_message
from app.bot.nlp_service import NLPService
from app.bot.product_invoice_flow import ProductInvoiceFlow, get_cart
from app.bot.support_handler import SupportHandler
from app.bot.voice_message_processor import VoiceMessageProcessor
from app.bot.whatsapp_client import WhatsAppClient
from app.bot.conversation_window import mark_conversation_active
from app.core.config import settings
from app.models import models
from app.services.analytics_service import (
    calculate_customer_metrics,
    calculate_invoice_metrics,
    calculate_revenue_metrics,
    get_conversion_rate,
    get_date_range,
)
from app.services.invoice_service import build_invoice_service
from app.utils.currency_fmt import fmt_money, get_user_currency

logger = logging.getLogger(__name__)

__all__ = ["WhatsAppClient", "WhatsAppHandler"]


class WhatsAppHandler:
    """Route incoming WhatsApp messages to the appropriate processors."""

    def __init__(self, client: WhatsAppClient, nlp: NLPService, db: Session):
        self.client = client
        self.db = db
        self.nlp = nlp
        self._speech_service = None

        self.invoice_processor = InvoiceIntentProcessor(db=db, client=client)
        self.expense_processor = ExpenseIntentProcessor(db=db, client=client)
        self.support_handler = SupportHandler(db=db, client=client)
        self.product_flow = ProductInvoiceFlow(db=db, client=client)
        self.voice_processor = VoiceMessageProcessor(
            client=client,
            nlp=nlp,
            invoice_processor=self.invoice_processor,
            speech_service_factory=self._get_speech_service,
        )

    def _check_inventory_access(self, sender: str) -> bool:
        """Check if the sender has PRO plan access for inventory/product features.

        Returns True if access is granted, False if blocked (sends upsell message).
        """
        issuer_id = self.invoice_processor._resolve_issuer_id(sender)
        if issuer_id is None:
            self.client.send_text(
                sender,
                "❌ Your WhatsApp number isn't linked to a business account.\n"
                "Register at suoops.com to start invoicing!"
            )
            return False

        user = self.db.query(models.User).filter(models.User.id == issuer_id).first()
        if not user or user.effective_plan.value != "pro":
            self.client.send_text(
                sender,
                "🔒 *Product Catalog is a Pro feature.*\n\n"
                "Upgrade to Pro at suoops.com/dashboard/subscription\n"
                "to manage products, build invoices from your catalog & more!"
            )
            return False
        return True

    async def handle_incoming(self, payload: dict[str, Any]) -> None:
        """Handle incoming WhatsApp webhook payload with robust error handling."""
        sender = None  # Initialise early so the except block can safely check it
        try:
            message = extract_message(payload)
            if not message:
                # Status webhooks (sent/delivered/read) are normal — not errors
                logger.debug("Non-message webhook payload (status update): %s", payload)
                return

            sender = message.get("from")
            if not sender:
                logger.warning("Missing sender in message: %s", message)
                return

            # Track 24-hour conversation window for outbound messaging
            mark_conversation_active(sender)

            msg_type = message.get("type", "text")

            if msg_type == "text":
                await self._handle_text_message(sender, message)
                return
            
            if msg_type == "interactive":
                # Handle button clicks
                await self._handle_interactive_message(sender, message)
                return

            if msg_type == "audio":
                media_id = message.get("audio_id")
                if media_id:
                    await self.voice_processor.process(sender, media_id, message)
                return
            
            if msg_type == "image":
                # Handle image messages (receipts)
                await self._handle_image_message(sender, message)
                return

            self.client.send_text(
                sender,
                "Sorry, I only support text messages, voice notes, and images.",
            )
        except Exception as exc:
            logger.exception("Error handling WhatsApp message: %s", exc)
            # Try to notify user of error - but don't fail if this also errors
            try:
                if sender:
                    self.client.send_text(
                        sender,
                        "⚠️ Something went wrong. Please try again in a moment.\n\n"
                        "If this keeps happening, contact support@suoops.com",
                    )
            except Exception:
                logger.exception("Failed to send error message to user")

    async def _handle_text_message(self, sender: str, message: dict[str, Any]) -> None:
        """Handle text messages with comprehensive error handling."""
        text = message.get("text", "").strip()
        if not text:
            logger.info("Received empty text message from %s", sender)
            return

        text_lower = text.lower()
        
        # Check if customer is confirming payment
        paid_keywords = {"paid", "i paid", "i've paid", "ive paid", "payment done", "sent", "transferred", "done"}
        if text_lower in paid_keywords:
            if self.invoice_processor.handle_customer_paid(sender):
                logger.info("Handled payment confirmation from customer %s", sender)
                return

        # Separate help vs greeting for different responses
        help_keywords = {"help", "menu", "guide", "how", "instructions", "commands"}
        greeting_keywords = {
            "hi", "hello", "hey", "good morning", "good afternoon",
            "good evening", "start", "yo", "sup", "what's up",
            "whats up", "howdy", "hiya",
        }
        optin_keywords = {"ok", "yes", "sure", "yea", "yeah", "yep", "👍", "okay"}
        
        is_help = text_lower in help_keywords
        is_greeting = text_lower in greeting_keywords
        is_optin = text_lower in optin_keywords

        # ── Conversational responses ─────────────────────────────
        if self._handle_conversational(sender, text_lower):
            return

        # ── Product browsing flow (PRO only) ────────────────────────
        # Check if user has an active cart session (mid-flow)
        cart_session = get_cart(sender)
        if cart_session:
            if not self._check_inventory_access(sender):
                return
            # User is mid-flow: handle items text or customer details
            if cart_session.step == "awaiting_items":
                self.product_flow.handle_items_reply(sender, text)
                return
            if cart_session.step == "awaiting_customer":
                invoice_data = self.product_flow.handle_customer_reply(sender, text)
                if invoice_data:
                    # Create the invoice using the existing processor
                    issuer_id = self.invoice_processor._resolve_issuer_id(sender)
                    if issuer_id:
                        invoice_service = build_invoice_service(self.db, user_id=issuer_id)
                        if self.invoice_processor._enforce_quota(invoice_service, issuer_id, sender):
                            await self.invoice_processor._create_invoice(
                                invoice_service, issuer_id, sender, invoice_data, {}
                            )
                return

        # ── Pending-price session (qty-only items needing prices) ──
        pending_price = get_pending_price_session(sender)
        if pending_price:
            # Let user cancel or start a new invoice
            if text_lower in {"cancel", "stop", "nevermind", "no"}:
                clear_pending_price_session(sender)
                self.client.send_text(sender, "✅ Invoice cancelled.")
                return
            # If user typed a brand-new invoice command, clear old session
            if text_lower.startswith("invoice"):
                clear_pending_price_session(sender)
                # fall through → NLP will handle the new invoice
            else:
                handled = await self.invoice_processor.handle_price_reply(
                    sender, text,
                )
                if handled:
                    return
        # ── End pending-price ──────────────────────────────────────

        # Check if text triggers product browsing (PRO only)
        if ProductInvoiceFlow.is_trigger(text_lower):
            if not self._check_inventory_access(sender):
                return
            issuer_id = self.invoice_processor._resolve_issuer_id(sender)
            if issuer_id is not None:
                self.product_flow.start_browsing(sender, issuer_id)
                return
            else:
                self.client.send_text(
                    sender,
                    "❌ Your WhatsApp number isn't linked to a business account.\n"
                    "Register at suoops.com to start invoicing!"
                )
                return

        # Check if user is searching products: "search wig" / "find shoe" (PRO only)
        search_match = text_lower.startswith("search ") or text_lower.startswith("find ")
        if search_match:
            if not self._check_inventory_access(sender):
                return
            issuer_id = self.invoice_processor._resolve_issuer_id(sender)
            if issuer_id is not None:
                query = text[len(text_lower.split()[0]) + 1:].strip()
                if query:
                    self.product_flow.handle_search(sender, issuer_id, query)
                    return
        # ── End product browsing flow ──────────────────────────────

        # ── Analytics / Insights command ──────────────────────────
        analytics_keywords = {"report", "analytics", "insights", "summary", "dashboard", "stats", "my stats", "my report"}
        if text_lower in analytics_keywords:
            issuer_id = self.invoice_processor._resolve_issuer_id(sender)
            if issuer_id is not None:
                self._send_analytics(sender, issuer_id)
            else:
                self.client.send_text(
                    sender,
                    "❌ Your WhatsApp number isn't linked to a business account.\n"
                    "Register at suoops.com to start invoicing!"
                )
            return
        # ── End analytics ─────────────────────────────────────────

        # ── Tax report download ───────────────────────────────────
        tax_keywords = {"tax report", "tax", "my tax", "download tax", "tax pdf"}
        if text_lower in tax_keywords:
            issuer_id = self.invoice_processor._resolve_issuer_id(sender)
            if issuer_id is not None:
                self._send_tax_report(sender, issuer_id)
            else:
                self.client.send_text(
                    sender,
                    "❌ Your WhatsApp number isn't linked to a business account.\n"
                    "Register at suoops.com to start invoicing!"
                )
            return
        # ── End tax report ────────────────────────────────────────

        # ── Currency toggle (USD / Naira) ─────────────────────────
        currency_keywords = {"currency", "usd", "dollar", "dollars", "naira", "ngn", "show usd", "show naira", "show dollars"}
        if text_lower in currency_keywords:
            issuer_id = self.invoice_processor._resolve_issuer_id(sender)
            if issuer_id is not None:
                self._toggle_currency(sender, issuer_id, text_lower)
            else:
                self.client.send_text(
                    sender,
                    "❌ Your WhatsApp number isn't linked to a business account.\n"
                    "Register at suoops.com to start invoicing!"
                )
            return
        # ── End currency toggle ───────────────────────────────────

        # Handle explicit help command - give concise guide
        if is_help:
            issuer_id = self.invoice_processor._resolve_issuer_id(sender)
            if issuer_id is not None:
                self._send_help_guide(sender, issuer_id)
            else:
                self.client.send_text(
                    sender,
                    "📖 *SuoOps Help*\n\n"
                    "I help businesses send invoices via WhatsApp.\n\n"
                    "📥 *Received an invoice?*\n"
                    "Reply 'Hi' to get payment details.\n\n"
                    "📤 *Want to send invoices?*\n"
                    "Register free at suoops.com\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    "🚀 Type *get started* for setup guide\n"
                    "❓ *Ask me anything* — pricing, how it works, etc.\n"
                    "🆘 Type *support* to reach our team"
                )
            return
        
        # CUSTOMER OPT-IN CHECK FIRST: A person can be BOTH a business AND a customer
        # who received an invoice. Check for pending invoices first!
        if is_greeting or is_optin:
            # Try to handle as customer opt-in (send pending invoices)
            # This works for both pure customers AND business users who also received invoices
            if self.invoice_processor.handle_customer_optin(sender):
                logger.info("Handled opt-in from customer %s", sender)
                return  # Successfully handled, don't process further
        
        # If they're a registered business with NO pending customer invoices, 
        # show business welcome (short version for greetings)
        if is_greeting or is_optin:
            issuer_id = self.invoice_processor._resolve_issuer_id(sender)
            if issuer_id is not None:
                # This is a registered business - send contextual greeting
                self._send_business_greeting(sender, issuer_id)
                return
            else:
                # Not a business and not a found customer - warm intro
                self.client.send_text(
                    sender,
                    "👋 Hey there! I'm SuoOps — your WhatsApp invoice assistant.\n\n"
                    "I help Nigerian businesses create and send professional invoices "
                    "right from WhatsApp. 🇳🇬\n\n"
                    "📥 *Got an invoice?* I'll send you the payment details.\n\n"
                    "📤 *Run a business?* Register free at suoops.com and "
                    "start invoicing in seconds!\n\n"
                    "Just ask me anything — I'm here to help 😊"
                )
                return

        # Look up the caller's preferred currency so the NLP
        # automatically uses the right amount-size heuristics
        # (e.g. 1-digit amounts for USD, 3-digit for NGN).
        caller_currency = "NGN"
        issuer_id_for_currency = self.invoice_processor._resolve_issuer_id(sender)
        if issuer_id_for_currency is not None:
            user_row = (
                self.db.query(models.User)
                .filter(models.User.id == issuer_id_for_currency)
                .first()
            )
            if user_row:
                caller_currency = getattr(user_row, "preferred_currency", "NGN") or "NGN"

        parse = self.nlp.parse_text(text, is_speech=False, caller_currency=caller_currency)
        
        # Check if user is trying to create an invoice but format is wrong
        # NLP will return "unknown" intent if the keyword is missing or format is too off
        if parse.intent == "unknown" and "invoice" in text_lower:
            issuer_id = self.invoice_processor._resolve_issuer_id(sender)
            if issuer_id is not None:
                # This is a registered business trying to create an invoice
                self.client.send_text(
                    sender,
                    "🤔 I couldn't understand the format.\n\n"
                    "✅ *Try:*\n"
                    "`Invoice Joy 08012345678, 5000 wig`\n\n"
                    "Type *help* for more examples."
                )
                return
        
        # Try expense processor first (checks if expense-related)
        expense_handled = False
        try:
            expense_handled = await self.expense_processor.handle(sender, parse, message)
        except Exception as exc:
            logger.exception("Error in expense processor: %s", exc)
            self.client.send_text(
                sender,
                "⚠️ Something went wrong recording your expense. Please try again.",
            )
            expense_handled = True  # Error message sent, don't double-fire

        if expense_handled:
            return

        # Only try invoice processor if expense processor didn't handle it
        if parse.intent == "create_invoice":
            try:
                await self.invoice_processor.handle(sender, parse, message)
            except Exception as exc:
                logger.exception("Error in invoice processor: %s", exc)
                self.client.send_text(
                    sender,
                    "⚠️ Something went wrong creating your invoice. Please try again.",
                )
            return

        # ── Support FAQ, onboarding & escalation ─────────────────
        try:
            support_handled = self.support_handler.try_handle(sender, text)
            if support_handled:
                return
        except Exception as exc:
            logger.exception("Error in support handler: %s", exc)
        # ── End support ───────────────────────────────────────────

        # If we get here with an unknown intent, send a friendly nudge
        issuer_id = self.invoice_processor._resolve_issuer_id(sender)
        if issuer_id is not None:
            user = self.db.query(models.User).filter(models.User.id == issuer_id).first()
            nudge = (
                "Hmm, I didn't quite catch that 😅\n\n"
                "Here's what I can help with:\n\n"
                "📝 *Invoice:* `Invoice Joy 5000 wig`\n"
                "💸 *Expense:* `Expense: 5000 transport`\n"
                "📊 *Report:* Type *report*\n"
            )
            if user and user.effective_plan.value == "pro":
                nudge += "📦 *Inventory:* Type *products*\n"
            nudge += (
                "\n❓ Or just ask me a question!\n"
                "e.g. \"how do I get paid?\" or \"what are the plans?\""
            )
            self.client.send_text(sender, nudge)
        else:
            self.client.send_text(
                sender,
                "I'm not sure I understood that 😊\n\n"
                "I'm SuoOps — I help businesses send invoices via WhatsApp.\n\n"
                "📤 *Want to send invoices?* Register free at suoops.com\n"
                "📥 *Got an invoice?* Just reply *Hi*\n\n"
                "Ask me anything — e.g. \"how to register\" or \"pricing\""
            )
    
    def _send_business_greeting(self, sender: str, issuer_id: int) -> None:
        """Send a warm, contextual greeting to a returning business user."""
        import datetime as _dt

        user = self.db.query(models.User).filter(models.User.id == issuer_id).first()
        name = getattr(user, "business_name", None) or getattr(user, "full_name", None) or ""

        # Time-of-day greeting
        hour = _dt.datetime.now(_dt.timezone.utc).hour + 1  # WAT = UTC+1
        if hour < 12:
            time_greeting = "Good morning"
        elif hour < 17:
            time_greeting = "Good afternoon"
        else:
            time_greeting = "Good evening"

        if name:
            msg = f"👋 {time_greeting}, {name.split()[0]}! Welcome back.\n\n"
        else:
            msg = f"👋 {time_greeting}! Welcome back.\n\n"

        msg += "What would you like to do?\n\n"
        msg += (
            "📝 *Create invoice* — just type:\n"
            "`Invoice Joy 08012345678, 5000 wig`\n\n"
            "💸 *Log an expense:*\n"
            "`Expense: 5,000 transport`\n\n"
            "📊 Type *report* for your business snapshot\n"
        )
        if user and user.effective_plan.value == "pro":
            msg += "📦 Type *products* to invoice from inventory\n"
        msg += (
            "\nOr just ask me anything — I'm here to help! 😊"
        )
        self.client.send_text(sender, msg)

    def _handle_conversational(self, sender: str, text_lower: str) -> bool:
        """Handle conversational/social messages naturally.

        Returns True if a response was sent, False to continue processing.
        """
        # ── Thank-you ──
        thank_phrases = {
            "thanks", "thank you", "thank u", "thanx", "thx",
            "thanks a lot", "thanks so much", "much appreciated",
            "appreciate it", "cheers", "awesome thanks",
            "okay thanks", "ok thanks", "alright thanks",
            "great thanks", "cool thanks", "wonderful",
        }
        if text_lower in thank_phrases or text_lower.startswith("thank"):
            self.client.send_text(
                sender,
                "You're welcome! 😊\n\n"
                "Let me know if you need anything else — I'm always here."
            )
            return True

        # ── Goodbye ──
        bye_phrases = {
            "bye", "goodbye", "good bye", "good night", "goodnight",
            "later", "see you", "see ya", "talk later", "gotta go",
            "bye bye", "take care", "night", "nighty night",
        }
        if text_lower in bye_phrases:
            self.client.send_text(
                sender,
                "Goodbye! 👋 Have a great one.\n\n"
                "I'm here whenever you need me — just send a message!"
            )
            return True

        # ── How are you / smalltalk ──
        smalltalk_phrases = {
            "how are you", "how are u", "how you dey",
            "how far", "how body", "how e dey go",
            "what's good", "how's it going", "how is it going",
            "how do you do", "how's your day",
        }
        if text_lower in smalltalk_phrases:
            self.client.send_text(
                sender,
                "I'm doing great, thanks for asking! 😄\n\n"
                "Ready to help with invoices, expenses, or anything else.\n"
                "What can I do for you today?"
            )
            return True

        # ── Positive feedback ──
        positive_phrases = {
            "nice", "cool", "great", "awesome", "perfect",
            "amazing", "love it", "fantastic", "brilliant",
            "sweet", "dope", "lit", "fire", "legit",
            "well done", "good job", "excellent",
        }
        if text_lower in positive_phrases:
            self.client.send_text(
                sender,
                "Glad to hear that! 🎉\n\n"
                "Need anything else? Just ask!"
            )
            return True

        # ── Laughter ──
        laugh_phrases = {"lol", "haha", "hahaha", "😂", "🤣", "😁", "😄", "lmao"}
        if text_lower in laugh_phrases:
            self.client.send_text(
                sender,
                "😄 Glad I could bring a smile!\n\n"
                "Anything I can help with?"
            )
            return True

        # ── Emoji-only messages ──
        if all(
            not c.isalnum() and not c.isspace()
            for c in text_lower
        ) and len(text_lower.strip()) > 0:
            # Pure emoji/symbol message
            self.client.send_text(
                sender,
                "😊 Nice!\n\nAnything I can help you with?"
            )
            return True

        # ── "Who are you" / identity ──
        identity_phrases = {
            "who are you", "what are you", "are you a bot",
            "are you real", "are you human", "is this a bot",
            "what is this", "what's this number",
        }
        if text_lower in identity_phrases:
            self.client.send_text(
                sender,
                "I'm *SuoOps* 🇳🇬 — your AI-powered invoice assistant!\n\n"
                "I help you create invoices, track expenses, and manage "
                "your business — all from WhatsApp.\n\n"
                "Type *help* to see everything I can do."
            )
            return True

        return False
    
    def _send_analytics(self, sender: str, issuer_id: int) -> None:
        """Send business analytics snapshot via WhatsApp."""
        from decimal import Decimal

        try:
            period = "30d"
            start_date, end_date = get_date_range(period)
            conversion_rate = get_conversion_rate("NGN")

            revenue = calculate_revenue_metrics(
                self.db, issuer_id, start_date, end_date, conversion_rate
            )
            invoices = calculate_invoice_metrics(
                self.db, issuer_id, start_date, end_date
            )
            customers = calculate_customer_metrics(
                self.db, issuer_id, start_date, end_date
            )

            # Resolve user's preferred display currency
            currency = get_user_currency(self.db, issuer_id)

            def fmt(amount: float) -> str:
                return fmt_money(amount, currency, compact=True)

            # Build growth indicator
            growth = revenue.growth_rate
            if growth > 0:
                growth_icon = "📈"
                growth_text = f"+{growth:.0f}%"
            elif growth < 0:
                growth_icon = "📉"
                growth_text = f"{growth:.0f}%"
            else:
                growth_icon = "➡️"
                growth_text = "0%"

            # Collection rate
            collection = (
                (invoices.paid_invoices / invoices.total_invoices * 100)
                if invoices.total_invoices > 0 else 0
            )

            msg = (
                "📊 *Your Business Report (30 days)*\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{growth_icon} *Revenue {growth_text} vs prev*\n"
                f"💰 Total: {fmt(revenue.total_revenue)}\n"
                f"✅ Collected: {fmt(revenue.paid_revenue)}\n"
                f"⏳ Pending: {fmt(revenue.pending_revenue)}\n"
                f"🔴 Overdue: {fmt(revenue.overdue_revenue)}\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "📄 *Invoices*\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📋 Total: {invoices.total_invoices}\n"
                f"✅ Paid: {invoices.paid_invoices}\n"
                f"⏳ Pending: {invoices.pending_invoices}\n"
            )

            if invoices.awaiting_confirmation:
                msg += f"🔔 Awaiting: {invoices.awaiting_confirmation}\n"
            if invoices.overdue_invoices if hasattr(invoices, 'overdue_invoices') else 0:
                msg += f"🔴 Overdue: {invoices.overdue_invoices}\n"

            msg += (
                f"📊 Collection: {collection:.0f}%\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "👥 *Customers*\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👥 Total: {customers.total_customers}\n"
                f"🆕 Active this month: {customers.active_customers}\n"
                f"🔄 Repeat rate: {customers.repeat_customer_rate:.0f}%\n\n"
            )

            if revenue.average_invoice_value:
                msg += f"💵 Avg invoice: {fmt(revenue.average_invoice_value)}\n\n"

            msg += (
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "💡 Full analytics at suoops.com/dashboard/analytics"
            )

            self.client.send_text(sender, msg)

        except Exception as exc:
            logger.exception("Error generating analytics for user %s: %s", issuer_id, exc)
            self.client.send_text(
                sender,
                "⚠️ Couldn't generate your report right now. "
                "Try again or view full analytics at suoops.com/dashboard/analytics"
            )

    def _send_tax_report(self, sender: str, issuer_id: int) -> None:
        """Generate and send the latest monthly tax report PDF via WhatsApp."""
        import datetime as dt

        try:
            # Check plan — tax reports require STARTER+
            user = self.db.query(models.User).filter(models.User.id == issuer_id).first()
            if not user or user.effective_plan.value == "free":
                self.client.send_text(
                    sender,
                    "🔒 *Tax Reports require a Starter or Pro plan.*\n\n"
                    "Upgrade at suoops.com/dashboard/subscription\n"
                    "to unlock tax reports, analytics & more!"
                )
                return

            now = dt.datetime.now(dt.timezone.utc)
            year = now.year
            month = now.month

            # Try current month first, fall back to previous month
            from app.models.tax_models import MonthlyTaxReport

            report = (
                self.db.query(MonthlyTaxReport)
                .filter(
                    MonthlyTaxReport.user_id == issuer_id,
                    MonthlyTaxReport.period_type == "month",
                )
                .order_by(MonthlyTaxReport.generated_at.desc())
                .first()
            )

            # If no report exists, generate one for the current month
            if not report:
                from app.services.tax_reporting_service import TaxReportingService

                try:
                    service = TaxReportingService(self.db)
                    report = service.generate_report(
                        user_id=issuer_id,
                        period_type="month",
                        year=year,
                        month=month,
                        basis="paid",
                    )
                    self.db.commit()
                except Exception as gen_err:
                    logger.warning("Failed to generate tax report for user %s: %s", issuer_id, gen_err)

            if not report:
                self.client.send_text(
                    sender,
                    "📊 No tax report data found yet.\n\n"
                    "Create some invoices first, then type *tax report* "
                    "to get your tax summary!"
                )
                return

            # Generate PDF if not already present
            if not report.pdf_url:
                try:
                    from app.services.pdf_service import PDFService
                    from app.storage.s3_client import S3Client
                    from app.services.tax_reporting.computations import (
                        compute_revenue_by_date_range,
                        compute_expenses_by_date_range,
                    )

                    total_revenue = float(
                        compute_revenue_by_date_range(
                            self.db, issuer_id, report.start_date, report.end_date, "paid"
                        )
                    )
                    total_expenses = float(
                        compute_expenses_by_date_range(
                            self.db, issuer_id, report.start_date, report.end_date
                        )
                    )

                    pdf_service = PDFService(S3Client())
                    pdf_url = pdf_service.generate_monthly_tax_report_pdf(
                        report, basis="paid",
                        total_revenue=total_revenue, total_expenses=total_expenses,
                    )

                    from app.services.tax_reporting_service import TaxReportingService
                    TaxReportingService(self.db).attach_report_pdf(report, pdf_url)
                    report.pdf_url = pdf_url
                    self.db.commit()
                except Exception as pdf_err:
                    logger.warning("Failed to generate tax PDF for user %s: %s", issuer_id, pdf_err)

            # Build period label
            if report.start_date:
                period_label = report.start_date.strftime("%B %Y")
            else:
                period_label = f"{report.year}-{report.month:02d}" if report.month else str(report.year)

            # Format amounts in user's preferred currency
            currency = get_user_currency(self.db, issuer_id)

            def fmt(val) -> str:
                return fmt_money(float(val or 0), currency, compact=True)

            profit = float(report.assessable_profit or 0)
            levy = float(report.levy_amount or 0)
            pit = float(report.pit_amount or 0)
            vat = float(report.vat_collected or 0)

            msg = (
                f"📊 *Tax Report — {period_label}*\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"💰 Assessable Profit: {fmt(profit)}\n"
                f"📋 Dev Levy: {fmt(levy)}\n"
                f"🏛️ Personal Income Tax: {fmt(pit)}\n"
            )

            if float(report.cit_amount or 0) > 0:
                msg += f"🏢 Company Income Tax: {fmt(report.cit_amount)}\n"

            if vat > 0:
                msg += f"💵 VAT Collected: {fmt(vat)}\n"

            total_tax = levy + pit + float(report.cit_amount or 0)
            msg += (
                f"\n📌 *Total Tax Liability: {fmt(total_tax)}*\n\n"
            )

            # Send text summary first
            self.client.send_text(sender, msg)

            # Send PDF if available — upload directly to WhatsApp (S3 presigned
            # URLs are blocked by WhatsApp servers → 403 Forbidden)
            if report.pdf_url:
                from app.storage.s3_client import S3Client as _S3
                _s3 = _S3()
                s3_key = _s3.extract_key_from_url(report.pdf_url)
                pdf_bytes = _s3.download_bytes(s3_key) if s3_key else None

                if pdf_bytes:
                    filename = f"TaxReport_{period_label.replace(' ', '_')}.pdf"
                    media_id = self.client.upload_media(pdf_bytes, "application/pdf", filename)
                    if media_id:
                        self.client.send_document(
                            sender, media_id, filename,
                            f"📄 Tax Report — {period_label}",
                        )
                    else:
                        self.client.send_text(
                            sender,
                            "💡 Couldn't attach PDF right now. "
                            "Download it at suoops.com/dashboard/tax"
                        )
                else:
                    self.client.send_text(
                        sender,
                        "💡 PDF not available right now. "
                        "Download it at suoops.com/dashboard/tax"
                    )
            else:
                self.client.send_text(
                    sender,
                    "💡 PDF not available right now. "
                    "Download it at suoops.com/dashboard/tax"
                )

        except Exception as exc:
            logger.exception("Error sending tax report for user %s: %s", issuer_id, exc)
            self.client.send_text(
                sender,
                "⚠️ Couldn't generate your tax report right now. "
                "Try again or download at suoops.com/dashboard/tax"
            )

    def _toggle_currency(self, sender: str, issuer_id: int, text_lower: str) -> None:
        """Toggle or display the user's preferred currency (NGN / USD)."""
        from app.services.exchange_rate import get_ngn_usd_rate

        user = self.db.query(models.User).filter(models.User.id == issuer_id).first()
        if not user:
            return

        current = getattr(user, "preferred_currency", "NGN") or "NGN"

        # Explicit switch requests
        usd_words = {"usd", "dollar", "dollars", "show usd", "show dollars"}
        ngn_words = {"naira", "ngn", "show naira"}

        if text_lower in usd_words:
            new = "USD"
        elif text_lower in ngn_words:
            new = "NGN"
        else:
            # "currency" → toggle to the opposite
            new = "USD" if current == "NGN" else "NGN"

        user.preferred_currency = new  # type: ignore[assignment]
        self.db.commit()

        # Build confirmation
        rate = get_ngn_usd_rate()
        if new == "USD":
            self.client.send_text(
                sender,
                "💱 *Currency set to USD* 🇺🇸\n\n"
                f"Live rate: ₦{rate:,.0f} = $1\n"
                "All amounts will now show in dollars.\n\n"
                "Type *naira* to switch back."
            )
        else:
            self.client.send_text(
                sender,
                "💱 *Currency set to Naira* 🇳🇬\n\n"
                "All amounts will show in ₦.\n\n"
                "Type *usd* to switch to dollars."
            )

    def _send_help_guide(self, sender: str, issuer_id: int) -> None:
        """Send comprehensive help guide to a business user."""
        help_message = (
            "📖 *SuoOps Invoice Guide*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📝 *CREATE AN INVOICE*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "`Invoice [Name] [Phone] [Amount] [Item], [Amount] [Item]`\n\n"
            "*Single Item:*\n"
            "• `Invoice Joy 08012345678 12000 wig`\n"
            "• `Invoice Mike 25000 consulting`\n\n"
            "*Multiple Items:*\n"
            "• `Invoice Ada 08012345678 11000 Design, 10000 Printing, 1000 Delivery`\n"
            "• `Invoice Blessing 5000 braids, 2000 gel, 500 pins`\n\n"
        )

        # Only show inventory section if user has PRO plan
        user = self.db.query(models.User).filter(models.User.id == issuer_id).first()
        if user and user.effective_plan.value == "pro":
            help_message += (
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "📦 *INVOICE FROM INVENTORY*\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "• Type *products* — browse & pick from your stock\n"
                "• Type *search wig* — find a specific product\n"
                "• Select items, set quantities, send invoice!\n\n"
            )

        help_message += (
            "⚠️ *IMPORTANT:*\n"
            "• Put amount BEFORE item name (11000 Design ✅, NOT Design 11000 ❌)\n"
            "• Commas in numbers are fine (11,000 ✅ or 11000 ✅)\n"
            "• Separate items with commas\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📅 *SET A DUE DATE (Optional)*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Add due date to any invoice:\n"
            "• `Invoice Joy 5000 wig tomorrow`\n"
            "• `Invoice Joy 5000 wig due in 7 days`\n"
            "• `Invoice Joy 5000 wig due friday`\n"
            "• `Invoice Joy 5000 wig due march 5`\n\n"
            "💡 If you don't set one, it defaults to 3 days.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📱 *WHAT HAPPENS NEXT*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "1️⃣ Customer gets WhatsApp notification\n"
            "2️⃣ They reply 'Hi' → get payment details + PDF\n"
            "3️⃣ They pay & tap 'I've Paid' → you're notified!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "💸 *TRACK EXPENSES*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "• `Expense: ₦5,000 for transport`\n"
            "• `Spent 3000 naira on data`\n"
            "• Send a photo of your receipt 📸\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📊 *BUSINESS REPORT*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Type *report* — get revenue, invoices & customer stats\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "🏛️ *TAX REPORT (Pro)*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Type *tax report* — get your tax summary + PDF\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "💱 *CURRENCY DISPLAY*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Type *usd* — show amounts in US Dollars\n"
            "Type *naira* — switch back to Naira (₦)\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 *TIPS*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "• Set up bank details in your dashboard first\n"
            "• Share the payment link if customer doesn't reply\n"
            "• Track all invoices at suoops.com/dashboard\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "🆘 *SUPPORT & QUESTIONS*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "❓ *Ask me anything:*\n"
            "  \"how to get paid\", \"pricing\", \"verify my number\"\n\n"
            "🚀 Type *setup* — check your account status\n"
            "🆘 Type *support* — reach our team\n"
            "🌐 Visit support.suoops.com for more help"
        )
        self.client.send_text(sender, help_message)
    
    async def _handle_interactive_message(self, sender: str, message: dict[str, Any]) -> None:
        """Handle interactive button clicks and list selections from WhatsApp."""
        button_id = message.get("button_id", "")
        button_title = message.get("button_title", "")
        # List replies come through as list_reply_id / list_reply_title
        list_reply_id = message.get("list_reply_id", "")
        list_reply_title = message.get("list_reply_title", "")
        
        interactive_id = button_id or list_reply_id
        
        logger.info(
            "[INTERACTIVE] From %s: button_id=%s, list_reply_id=%s",
            sender, button_id, list_reply_id,
        )
        
        # ── Product flow: cart action buttons ──────────────────────
        if button_id == "cart_add_more":
            self.product_flow.handle_add_more(sender)
            return

        if button_id == "cart_clear":
            self.product_flow.handle_clear_cart(sender)
            return
        # ── End product flow ───────────────────────────────────────

        # Handle "I've Paid" button click
        if button_id == "confirm_paid" or button_id.startswith("paid_"):
            if self.invoice_processor.handle_customer_paid(sender):
                logger.info("Handled payment confirmation button from customer %s", sender)
                return
        
        # Handle other buttons as opt-in (Hi, Get Details, etc.)
        if button_id in ("opt_in", "get_details", "hi"):
            if self.invoice_processor.handle_customer_optin(sender):
                logger.info("Handled opt-in button from customer %s", sender)
                return
        
        logger.warning("[INTERACTIVE] Unhandled: id=%s", interactive_id)
    
    async def _handle_image_message(self, sender: str, message: dict[str, Any]) -> None:
        """Handle image messages (receipt photos)"""
        parse = {}  # Empty parse for images
        await self.expense_processor.handle(sender, parse, message)

    @property
    def speech_service(self):
        return self._get_speech_service()

    def _get_speech_service(self):
        if self._speech_service is None:
            from app.services.speech_service import SpeechService

            self._speech_service = SpeechService()
        return self._speech_service

    def handle_webhook(self, payload: dict[str, Any]) -> None:
        """Synchronous convenience wrapper for legacy callers."""
        import asyncio

        asyncio.run(self.handle_incoming(payload))

