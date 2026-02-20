from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.bot.expense_intent_processor import ExpenseIntentProcessor
from app.bot.invoice_intent_processor import InvoiceIntentProcessor
from app.bot.message_extractor import extract_message
from app.bot.nlp_service import NLPService
from app.bot.product_invoice_flow import ProductInvoiceFlow, get_cart
from app.bot.voice_message_processor import VoiceMessageProcessor
from app.bot.whatsapp_client import WhatsAppClient
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
                        "⚠️ Something went wrong. Please try again in a moment.",
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

        # ── Product browsing flow ──────────────────────────────────
        # Check if user has an active cart session (mid-flow)
        cart_session = get_cart(sender)
        if cart_session:
            # User is mid-flow: handle quantity or customer details
            if cart_session.step == "awaiting_qty":
                self.product_flow.handle_quantity_reply(sender, text)
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

        # Check if text triggers product browsing
        if ProductInvoiceFlow.is_trigger(text_lower):
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

        # Check if user is searching products: "search wig" / "find shoe"
        search_match = text_lower.startswith("search ") or text_lower.startswith("find ")
        if search_match:
            issuer_id = self.invoice_processor._resolve_issuer_id(sender)
            if issuer_id is not None:
                query = text[len(text_lower.split()[0]) + 1:].strip()
                if query:
                    self.product_flow.handle_search(sender, issuer_id, query)
                    return
        # ── End product browsing flow ──────────────────────────────
        
        # Handle explicit help command - give concise guide
        if is_help:
            issuer_id = self.invoice_processor._resolve_issuer_id(sender)
            if issuer_id is not None:
                self._send_help_guide(sender)
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
                self._send_business_greeting(sender)
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
        
        # Then try invoice processor
        try:
            await self.invoice_processor.handle(sender, parse, message)
        except Exception as exc:
            logger.exception("Error in invoice processor: %s", exc)
            self.client.send_text(
                sender,
                "⚠️ Something went wrong creating your invoice. Please try again.",
            )
    
    def _send_business_greeting(self, sender: str) -> None:
        """Send short greeting to a returning business user."""
        self.client.send_text(
            sender,
            "👋 Welcome back!\n\n"
            "📝 *Create invoice:*\n"
            "`Invoice Joy 08012345678, 5000 wig`\n\n"
            "📦 *From inventory:*\n"
            "Type *products* to browse your stock\n\n"
            "Type *help* for full guide."
        )
    
    def _send_help_guide(self, sender: str) -> None:
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
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📦 *INVOICE FROM INVENTORY*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "• Type *products* — browse & pick from your stock\n"
            "• Type *search wig* — find a specific product\n"
            "• Select items, set quantities, send invoice!\n\n"
            "⚠️ *IMPORTANT:*\n"
            "• Put amount BEFORE item name (11000 Design ✅, NOT Design 11000 ❌)\n"
            "• Don't use commas in numbers (11000 ✅, NOT 11,000 ❌)\n"
            "• Separate items with commas\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📱 *WHAT HAPPENS NEXT*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "1️⃣ Customer gets WhatsApp notification\n"
            "2️⃣ They reply 'Hi' → get payment details + PDF\n"
            "3️⃣ They pay & tap 'I've Paid' → you're notified!\n\n"
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
        
        # ── Product flow: list selection ───────────────────────────
        if list_reply_id.startswith("product_"):
            try:
                product_id = int(list_reply_id.replace("product_", ""))
                self.product_flow.handle_product_selected(sender, product_id)
                return
            except (ValueError, TypeError):
                logger.warning("[INTERACTIVE] Invalid product id: %s", list_reply_id)
        
        # ── Product flow: cart action buttons ──────────────────────
        if button_id == "cart_add_more":
            self.product_flow.handle_add_more(sender)
            return
        
        if button_id == "cart_send_invoice":
            self.product_flow.handle_send_invoice(sender)
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

