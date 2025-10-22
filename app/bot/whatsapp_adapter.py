from __future__ import annotations

import logging
from typing import Any

import httpx
import requests

from app.bot.nlp_service import NLPService
from app.core.config import settings
from app.services.invoice_service import InvoiceService

logger = logging.getLogger(__name__)


class WhatsAppClient:
    """
    WhatsApp Cloud API client for sending messages and downloading media.
    
    Single Responsibility: All WhatsApp API interactions.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.phone_number_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", None)
        self.base_url = f"https://graph.facebook.com/v21.0/{self.phone_number_id}/messages"
        self.media_url = "https://graph.facebook.com/v21.0"

    def send_text(self, to: str, body: str) -> None:
        """Send text message to WhatsApp number."""
        if not self.phone_number_id or not self.api_key:
            logger.warning("[WHATSAPP] Not configured, would send to %s: %s", to, body)
            return

        try:
            payload = {
                "messaging_product": "whatsapp",
                "to": to.replace("+", ""),  # Remove + sign
                "type": "text",
                "text": {"body": body}
            }
            response = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            logger.info("[WHATSAPP] ✓ Sent to %s: %s", to, body[:50])
        except Exception as e:
            logger.error("[WHATSAPP] Failed to send to %s: %s", to, e)

    def send_document(self, to: str, url: str, filename: str, caption: str | None = None) -> None:
        """Send document (PDF) to WhatsApp number."""
        if not self.phone_number_id or not self.api_key:
            logger.warning("[WHATSAPP DOC] Not configured, would send to %s: %s", to, filename)
            return

        try:
            payload = {
                "messaging_product": "whatsapp",
                "to": to.replace("+", ""),  # Remove + sign
                "type": "document",
                "document": {
                    "link": url,
                    "filename": filename
                }
            }
            if caption:
                payload["document"]["caption"] = caption

            response = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            logger.info("[WHATSAPP DOC] ✓ Sent to %s: %s", to, filename)
        except Exception as e:
            logger.error("[WHATSAPP DOC] Failed to send to %s: %s", to, e)

    async def get_media_url(self, media_id: str) -> str:
        """
        Get downloadable URL for WhatsApp media.
        
        Args:
            media_id: Media ID from webhook
            
        Returns:
            Direct download URL for the media file
        """
        if not self.api_key:
            raise ValueError("WhatsApp not configured")
        
        url = f"{self.media_url}/{media_id}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data["url"]

    async def download_media(self, media_url: str) -> bytes:
        """
        Download media file from WhatsApp CDN.
        
        Args:
            media_url: URL from get_media_url()
            
        Returns:
            Raw file bytes
        """
        if not self.api_key:
            raise ValueError("WhatsApp not configured")
        
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(media_url, headers=headers)
            response.raise_for_status()
            logger.info("[WHATSAPP] Downloaded %d bytes", len(response.content))
            return response.content


class WhatsAppHandler:
    """
    Handle incoming WhatsApp messages (text and voice).
    
    Single Responsibility: Orchestrate message processing.
    """
    
    def __init__(self, client: WhatsAppClient, nlp: NLPService, invoice_service: InvoiceService):
        self.client = client
        self.nlp = nlp
        self.invoice_service = invoice_service
        self._speech_service = None  # Lazy load to avoid circular import

    @property
    def speech_service(self):
        """Lazy load speech service to avoid import issues."""
        if self._speech_service is None:
            from app.services.speech_service import SpeechService
            self._speech_service = SpeechService()
        return self._speech_service

    async def handle_incoming(self, payload: dict[str, Any]):
        """
        Route incoming message to appropriate handler.
        
        Supports both text and audio messages.
        """
        sender = payload.get("from")
        msg_type = payload.get("type", "text")
        
        if msg_type == "text":
            text = payload.get("text", "").strip()
            if text:
                await self._handle_text_message(sender, text, payload)
        
        elif msg_type == "audio":
            media_id = payload.get("audio_id")
            if media_id:
                await self._handle_audio_message(sender, media_id, payload)
        
        else:
            self.client.send_text(
                sender,
                "Sorry, I only support text messages and voice notes.",
            )

    async def _handle_text_message(self, sender: str, text: str, payload: dict[str, Any]):
        """Process text message (DRY: shared by text and transcribed audio)."""
        parse = self.nlp.parse_text(text, is_speech=False)
        await self._process_invoice_intent(sender, parse, payload)

    async def _handle_audio_message(self, sender: str, media_id: str, payload: dict[str, Any]):
        """Process voice note message."""
        try:
            # Notify user we're processing
            self.client.send_text(sender, "🎙️ Processing your voice message...")
            
            # Download audio from WhatsApp
            media_url = await self.client.get_media_url(media_id)
            audio_bytes = await self.client.download_media(media_url)
            
            # Transcribe to text
            transcript = await self.speech_service.transcribe_audio(audio_bytes)
            
            if not transcript or len(transcript.split()) < 3:
                self.client.send_text(
                    sender,
                    "⚠️ Your voice message was too short or unclear.\n\n"
                    "Please try again and speak clearly:\n"
                    "\"Invoice [Customer Name] [Amount] for [Description]\"",
                )
                return
            
            # Show what we understood
            self.client.send_text(
                sender,
                f"📝 I heard: \"{transcript}\"\n\nProcessing...",
            )
            
            # Parse as speech (with cleaning)
            parse = self.nlp.parse_text(transcript, is_speech=True)
            await self._process_invoice_intent(sender, parse, payload)
            
        except Exception as e:
            logger.exception("[VOICE] Failed to process audio")
            self.client.send_text(
                sender,
                f"❌ Sorry, I couldn't process that voice message: {e}\n\n"
                "Please try again or send a text message.",
            )

    async def _process_invoice_intent(self, sender: str, parse, payload: dict[str, Any]):
        """
        Process invoice creation intent (DRY: reused by text and voice).
        
        SRP: Single method for invoice creation logic.
        """
        if parse.intent == "create_invoice":
            data = parse.entities
            issuer_id = self._resolve_issuer_id(payload)
            if issuer_id is None:
                logger.warning("Unable to resolve issuer for WhatsApp payload: %s", payload)
                self.client.send_text(
                    sender,
                    "Unable to identify your account. Please log in first.",
                )
                return
            
            # Check invoice quota before creating
            try:
                quota_check = self.invoice_service.check_invoice_quota(issuer_id)
                
                # Send warning if approaching limit
                if quota_check["can_create"] and quota_check["limit"]:
                    remaining = quota_check["limit"] - quota_check["used"]
                    if remaining <= 5 and remaining > 0:
                        self.client.send_text(
                            sender,
                            quota_check["message"]
                        )
                
                # Block if at limit
                if not quota_check["can_create"]:
                    limit_message = f"🚫 Invoice Limit Reached!\n\n"
                    limit_message += f"Plan: {quota_check['plan'].upper()}\n"
                    limit_message += f"Used: {quota_check['used']}/{quota_check['limit']} invoices this month\n\n"
                    limit_message += quota_check["message"]
                    limit_message += f"\n\n📞 Contact us to upgrade your plan."
                    
                    self.client.send_text(sender, limit_message)
                    return
                    
            except Exception as e:
                logger.error("Failed to check quota: %s", e)
                # Continue anyway to avoid blocking legitimate requests
            
            try:
                invoice = self.invoice_service.create_invoice(
                    issuer_id=issuer_id,
                    data=data,
                )
                
                # Send confirmation to business owner
                business_message = f"✅ Invoice {invoice.invoice_id} created!\n\n"
                business_message += f"💰 Amount: ₦{invoice.amount:,.2f}\n"
                business_message += f"� Customer: {invoice.customer.name if invoice.customer else 'N/A'}\n"
                business_message += f"�📊 Status: {invoice.status}\n"
                
                if invoice.payment_url:
                    business_message += f"\n� Payment link sent to customer!"
                
                self.client.send_text(sender, business_message)
                
                # Send invoice and payment link to CUSTOMER
                customer_phone = data.get("customer_phone")
                if customer_phone and invoice.payment_url:
                    # Send payment link to customer
                    customer_message = f"Hello {invoice.customer.name if invoice.customer else 'there'}! 👋\n\n"
                    customer_message += f"You have a new invoice from your business partner.\n\n"
                    customer_message += f"📄 Invoice: {invoice.invoice_id}\n"
                    customer_message += f"💰 Amount: ₦{invoice.amount:,.2f}\n\n"
                    customer_message += f"💳 Pay now: {invoice.payment_url}\n\n"
                    customer_message += f"Click the link above to complete your payment securely via Paystack."
                    
                    self.client.send_text(customer_phone, customer_message)
                    
                    # If PDF URL is accessible, send it too
                    if invoice.pdf_url and invoice.pdf_url.startswith("http"):
                        self.client.send_document(
                            customer_phone,
                            invoice.pdf_url,
                            f"Invoice_{invoice.invoice_id}.pdf",
                            f"Invoice {invoice.invoice_id} - ₦{invoice.amount:,.2f}"
                        )
                    
                    logger.info("Sent invoice %s to customer at %s", invoice.invoice_id, customer_phone)
                else:
                    logger.warning("No customer phone or payment URL for invoice %s", invoice.invoice_id)
                    
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to create invoice")
                error_msg = str(exc)
                if "invoice_limit_reached" in error_msg or "403" in error_msg:
                    self.client.send_text(
                        sender,
                        "🚫 You've reached your monthly invoice limit.\n\n"
                        "Upgrade your plan to create more invoices."
                    )
                else:
                    self.client.send_text(sender, f"Error: {exc}")
        else:
            self.client.send_text(
                sender,
                "Sorry, I didn't understand. Try:\n"
                "• Text: \"Invoice Joy 12000 for wigs due tomorrow\"\n"
                "• Voice: Send a voice note with invoice details",
            )

    @staticmethod
    def _resolve_issuer_id(payload: dict[str, Any]) -> int | None:
        candidate_keys = ("issuer_id", "user_id", "account_id")
        metadata = payload.get("metadata") or {}
        for key in candidate_keys:
            value = payload.get(key)
            if value is not None:
                coerced = WhatsAppHandler._coerce_int(value)
                if coerced is not None:
                    return coerced
            meta_value = metadata.get(key)
            if meta_value is not None:
                coerced_meta = WhatsAppHandler._coerce_int(meta_value)
                if coerced_meta is not None:
                    return coerced_meta
        return None

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
