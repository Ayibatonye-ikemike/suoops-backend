from __future__ import annotations

import logging
from typing import Any

import requests

from app.bot.nlp_service import NLPService
from app.core.config import settings
from app.services.invoice_service import InvoiceService

logger = logging.getLogger(__name__)


class WhatsAppClient:
    """WhatsApp Cloud API client for sending messages and documents."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.phone_number_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", None)
        self.base_url = f"https://graph.facebook.com/v21.0/{self.phone_number_id}/messages"

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


class WhatsAppHandler:
    def __init__(self, client: WhatsAppClient, nlp: NLPService, invoice_service: InvoiceService):
        self.client = client
        self.nlp = nlp
        self.invoice_service = invoice_service

    def handle_incoming(self, payload: dict[str, Any]):
        # Expect simplified payload {"from": "+234...", "text": "Invoice Tolu 25000 due tomorrow"}
        sender = payload.get("from")
        text = payload.get("text", "").strip()
        if not text:
            return
        parse = self.nlp.parse_text(text)
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
                self.client.send_text(sender, f"Error: {exc}")
        else:
            self.client.send_text(
                sender,
                "Sorry, I didn't understand. Try: Invoice Joy 12000 for wigs due tomorrow",
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
