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

        parse = self.nlp.parse_text(text, is_speech=False)
        
        # Try expense processor first (checks if expense-related)
        await self.expense_processor.handle(sender, parse, message)
        
        # Then try invoice processor
        await self.invoice_processor.handle(sender, parse, message)
    
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

