from __future__ import annotations

import logging
from typing import Any, Callable

from app.bot.invoice_intent_processor import InvoiceIntentProcessor
from app.bot.whatsapp_client import WhatsAppClient
from app.bot.nlp_service import NLPService
from app.core.config import settings
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

    def _check_user_has_business_plan(self, sender: str) -> tuple[bool, models.User | None]:
        """
        Check if user has Business plan for voice/OCR features.
        
        Voice and OCR are exclusive to Business plan.
        Business plan: 15 voice+OCR invoices per month quota.
        
        Returns:
            (has_access: bool, user: User | None)
        """
        # Fast path: feature flag disabled – open access.
        if not settings.FEATURE_VOICE_REQUIRES_PAID:
            return True, None
        # Dev/Test environments bypass gating for easier local workflows.
        if settings.ENV.lower() not in {"prod", "production"}:
            return True, None
        
        normalized = sender.strip()
        if not normalized.startswith("+"):
            if normalized.startswith("234"):
                normalized = f"+{normalized}"
            elif normalized.startswith("0"):
                normalized = f"+234{normalized[1:]}"
            else:
                normalized = f"+{normalized}"
        
        user = (
            self.invoice_processor.db.query(models.User)
            .filter(models.User.phone == normalized)
            .first()
        )
        if not user:
            return False, None
        
        # Check if Business plan
        has_access = user.plan == models.SubscriptionPlan.BUSINESS
        return has_access, user

    async def process(self, sender: str, media_id: str, payload: dict[str, Any]) -> None:
        try:
            # Check if voice feature is globally enabled
            if not settings.FEATURE_VOICE_ENABLED:
                self.client.send_text(
                    sender,
                    "🎙️ Voice invoices are currently unavailable.\n\n"
                    "Please send a text message instead:\n"
                    '"Invoice [Customer] [Amount] for [Description]"\n\n'
                    "Example: \"Invoice Jane 50000 for logo design\""
                )
                return

            # Check if user has Business plan (voice is premium feature)
            has_access, user = self._check_user_has_business_plan(sender)
            if not has_access:
                self.client.send_text(
                    sender,
                    "🔒 Voice Invoice Feature\n\n"
                    "Voice message invoices are only available on the Business plan.\n\n"
                    "📊 Current Plans:\n"
                    "• Starter (₦4,500/mo): 100 invoices + Tax reports\n"
                    "• Pro (₦8,000/mo): 200 invoices + Custom branding\n"
                    "• Business (₦16,000/mo): 300 invoices + Photo OCR (15 premium/mo)\n\n"
                    "Visit suoops.com/dashboard/subscription to upgrade!"
                )
                return
            
            # TODO: Check Business plan quota (15 voice+OCR per month)
            # For now, allow all Business users
            
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
