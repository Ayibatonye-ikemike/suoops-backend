from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.bot.expense_intent_processor import ExpenseIntentProcessor
from app.bot.invoice_intent_processor import InvoiceIntentProcessor
from app.bot.message_extractor import extract_message
from app.bot.nlp_service import NLPService
from app.bot.product_invoice_flow import ProductInvoiceFlow, get_cart, clear_cart
from app.bot.voice_message_processor import VoiceMessageProcessor
from app.bot.whatsapp_client import WhatsAppClient
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
        try:
            message = extract_message(payload)
            if not message:
                logger.warning("Unsupported WhatsApp payload: %s", payload)
                return

            sender = message.get("from")
            if not sender:
                logger.warning("Missing sender in message: %s", message)
                return

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
        greeting_keywords = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening", "start"}
        optin_keywords = {"ok", "yes", "sure", "yea", "yeah", "yep", "👍", "okay"}
        
        is_help = text_lower in help_keywords
        is_greeting = text_lower in greeting_keywords
        is_optin = text_lower in optin_keywords

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
                    "Register free at suoops.com"
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
                # This is a registered business - send short greeting
                self._send_business_greeting(sender, issuer_id)
                return
            else:
                # Not a business and not a found customer - send short response
                self.client.send_text(
                    sender,
                    "👋 Hi! I'm the SuoOps invoice assistant.\n\n"
                    "📥 Received an invoice? I'll send payment details when it arrives.\n\n"
                    "📤 Want to send invoices? Register free at suoops.com"
                )
                return

        parse = self.nlp.parse_text(text, is_speech=False)
        
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
        try:
            await self.expense_processor.handle(sender, parse, message)
        except Exception as exc:
            logger.exception("Error in expense processor: %s", exc)
            self.client.send_text(
                sender,
                "⚠️ Something went wrong recording your expense. Please try again.",
            )
        
        # Then try invoice processor
        try:
            await self.invoice_processor.handle(sender, parse, message)
        except Exception as exc:
            logger.exception("Error in invoice processor: %s", exc)
            self.client.send_text(
                sender,
                "⚠️ Something went wrong creating your invoice. Please try again.",
            )

        # If we get here with an unknown intent, send a gentle nudge
        if parse.intent == "unknown":
            issuer_id = self.invoice_processor._resolve_issuer_id(sender)
            if issuer_id is not None:
                # Registered business — nudge toward creating an invoice
                nudge = (
                    "🤔 I'm not sure what you mean.\n\n"
                    "Here's what I can do:\n"
                    "📝 *Create invoice:* `Invoice Joy 5000 wig`\n"
                    "📊 *Business report:* Type *report*\n"
                )
                # Only show inventory option if user has PRO plan
                user = self.db.query(models.User).filter(models.User.id == issuer_id).first()
                if user and user.effective_plan.value == "pro":
                    nudge += "📦 *From inventory:* Type *products*\n"
                nudge += "❓ *Full guide:* Type *help*"
                self.client.send_text(sender, nudge)
    
    def _send_business_greeting(self, sender: str, issuer_id: int) -> None:
        """Send short greeting to a returning business user."""
        msg = (
            "👋 Welcome back!\n\n"
            "📝 *Create invoice:*\n"
            "`Invoice Joy 08012345678, 5000 wig`\n\n"
        )
        # Only show inventory option if user has PRO plan
        user = self.db.query(models.User).filter(models.User.id == issuer_id).first()
        if user and user.effective_plan.value == "pro":
            msg += (
                "📦 *From inventory:*\n"
                "Type *products* to browse your stock\n\n"
            )
        msg += (
            "📊 *Business report:*\n"
            "Type *report* for your analytics\n"
            "Type *tax report* for tax summary + PDF\n\n"
            "Type *help* for full guide."
        )
        self.client.send_text(sender, msg)
    
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

            # Format currency helper
            def fmt(amount: float) -> str:
                if amount >= 1_000_000:
                    return f"₦{amount / 1_000_000:,.1f}M"
                if amount >= 1_000:
                    return f"₦{amount:,.0f}"
                return f"₦{amount:,.2f}"

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

            now = dt.datetime.utcnow()
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

            # Format amounts
            def fmt(val) -> str:
                amount = float(val or 0)
                if amount >= 1_000_000:
                    return f"₦{amount / 1_000_000:,.1f}M"
                return f"₦{amount:,.0f}"

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
            "📊 *BUSINESS REPORT*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Type *report* — get revenue, invoices & customer stats\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "🏛️ *TAX REPORT (Starter+)*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Type *tax report* — get your tax summary + PDF\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 *TIPS*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "• Set up bank details in your dashboard first\n"
            "• Share the payment link if customer doesn't reply\n"
            "• Track all invoices at suoops.com/dashboard"
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

