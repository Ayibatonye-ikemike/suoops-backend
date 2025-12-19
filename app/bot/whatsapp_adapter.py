from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.bot.expense_intent_processor import ExpenseIntentProcessor
from app.bot.invoice_intent_processor import InvoiceIntentProcessor
from app.bot.message_extractor import extract_message
from app.bot.voice_message_processor import VoiceMessageProcessor
from app.bot.whatsapp_client import WhatsAppClient
from app.bot.nlp_service import NLPService

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
        self.voice_processor = VoiceMessageProcessor(
            client=client,
            nlp=nlp,
            invoice_processor=self.invoice_processor,
            speech_service_factory=self._get_speech_service,
        )

    async def handle_incoming(self, payload: dict[str, Any]) -> None:
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

    async def _handle_text_message(self, sender: str, message: dict[str, Any]) -> None:
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

        # Check if this is an opt-in response from a customer
        # Common affirmative replies that indicate opt-in
        optin_keywords = {"ok", "yes", "hi", "hello", "hey", "sure", "yea", "yeah", "yep", "👍", "okay"}
        if text_lower in optin_keywords:
            # Try to handle as customer opt-in (send pending invoices)
            if self.invoice_processor.handle_customer_optin(sender):
                logger.info("Handled opt-in from customer %s", sender)
                return  # Successfully sent pending invoices, don't process further
        
        # Check if this is a help/greeting from a business user
        help_keywords = {"help", "start", "menu", "guide", "how", "instructions"}
        greeting_keywords = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"}
        
        if text_lower in help_keywords or text_lower in greeting_keywords or text_lower in optin_keywords:
            # Check if sender is a registered business
            issuer_id = self.invoice_processor._resolve_issuer_id(sender)
            if issuer_id is not None:
                # This is a registered business - send welcome/help message
                self._send_business_welcome(sender)
                return

        parse = self.nlp.parse_text(text, is_speech=False)
        
        # Try expense processor first (checks if expense-related)
        await self.expense_processor.handle(sender, parse, message)
        
        # Then try invoice processor
        await self.invoice_processor.handle(sender, parse, message)
    
    def _send_business_welcome(self, sender: str) -> None:
        """Send welcome/help message to a registered business user."""
        welcome_message = (
            "👋 *Welcome to SuoOps!*\n\n"
            "I'm your WhatsApp invoice assistant. Here's how to use me:\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📝 *HOW TO CREATE AN INVOICE*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Send a message in this format:\n"
            "```Invoice [Customer Name] [Phone], [Amount] [Item]```\n\n"
            "*Examples:*\n"
            "• `Invoice Joy 08012345678, 12000 wig`\n"
            "• `Invoice Ada 08098765432, 5000 braids, 2000 gel`\n"
            "• Or send a *voice note* with the details!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📱 *WHAT HAPPENS NEXT*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "1️⃣ Your customer receives a WhatsApp message\n"
            "2️⃣ When they reply, they get:\n"
            "   • Payment details (your bank info)\n"
            "   • Invoice PDF\n"
            "   • Payment link\n\n"
            "3️⃣ When they pay & confirm, you get notified!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 *TIPS*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "• Make sure your bank details are set up in your dashboard\n"
            "• First-time customers need to reply before seeing payment info\n"
            "• Type *help* anytime to see this guide\n\n"
            "Ready? Send your first invoice! 🚀"
        )
        self.client.send_text(sender, welcome_message)
    
    async def _handle_interactive_message(self, sender: str, message: dict[str, Any]) -> None:
        """Handle interactive button clicks from WhatsApp."""
        button_id = message.get("button_id", "")
        button_title = message.get("button_title", "")
        
        logger.info("[BUTTON] Received button click from %s: id=%s, title=%s", sender, button_id, button_title)
        
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
        
        logger.warning("[BUTTON] Unhandled button: id=%s", button_id)
    
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

