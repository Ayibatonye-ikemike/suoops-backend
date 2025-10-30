from __future__ import annotations

import logging
from typing import Any, Callable

from app.bot.invoice_intent_processor import InvoiceIntentProcessor
from app.bot.whatsapp_client import WhatsAppClient
from app.bot.nlp_service import NLPService
from app.models import models

logger = logging.getLogger(__name__)


class VoiceMessageProcessor:
    """Process WhatsApp voice notes by downloading, transcribing, and handling intents."""

    def __init__(
        self,
        client: WhatsAppClient,
        nlp: NLPService,
        invoice_processor: InvoiceIntentProcessor,
        speech_service_factory: Callable[[], Any],
    ) -> None:
        self.client = client
        self.nlp = nlp
        self.invoice_processor = invoice_processor
        self._speech_service_factory = speech_service_factory

    def _check_user_has_paid_plan(self, sender: str) -> bool:
        """Check if user has paid plan for voice message feature."""
        # Get user from WhatsApp phone number
        user = (
            self.invoice_processor.db.query(models.User)
            .filter(models.User.whatsapp_phone == sender)
            .first()
        )
        
        if not user:
            return False
        
        return user.plan != models.SubscriptionPlan.FREE

    async def process(self, sender: str, media_id: str, payload: dict[str, Any]) -> None:
        try:
            # Check if user has paid plan (voice messages are premium feature)
            if not self._check_user_has_paid_plan(sender):
                self.client.send_text(
                    sender,
                    "🔒 Voice Invoice Feature\n\n"
                    "Voice message invoices are only available on paid plans.\n\n"
                    "✅ Upgrade your plan to unlock:\n"
                    "• Voice note invoices\n"
                    "• Photo invoices (OCR)\n"
                    "• More monthly invoices\n"
                    "• Priority support\n\n"
                    "Visit suoops.com/dashboard/subscription to upgrade!"
                )
                return
            
            self.client.send_text(sender, "🎙️ Processing your voice message...")
            media_url = await self.client.get_media_url(media_id)
            audio_bytes = await self.client.download_media(media_url)

            transcript = await self._speech_service_factory().transcribe_audio(audio_bytes)
            if not transcript or len(transcript.split()) < 3:
                self.client.send_text(
                    sender,
                    "⚠️ Your voice message was too short or unclear.\n\n"
                    "Please try again and speak clearly:\n"
                    '"Invoice [Customer Name] [Amount] for [Description]"',
                )
                return

            self.client.send_text(sender, f"📝 I heard: \"{transcript}\"\n\nProcessing...")
            parse = self.nlp.parse_text(transcript, is_speech=True)
            await self.invoice_processor.handle(sender, parse, payload)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[VOICE] Failed to process audio")
            self.client.send_text(
                sender,
                f"❌ Sorry, I couldn't process that voice message: {exc}\n\n"
                "Please try again or send a text message.",
            )
