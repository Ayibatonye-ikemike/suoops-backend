from __future__ import annotations

import logging
from typing import Any

from app.bot.nlp_service import NLPService
from app.services.invoice_service import InvoiceService

logger = logging.getLogger(__name__)


class WhatsAppClient:
    """Placeholder WhatsApp Cloud API client."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def send_text(self, to: str, body: str) -> None:
        logger.info("[WHATSAPP] -> %s | %s", to, body)

    def send_document(self, to: str, url: str, filename: str) -> None:
        logger.info("[WHATSAPP DOC] -> %s | %s (%s)", to, filename, url)


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
                self.client.send_text(
                    sender,
                    f"Invoice {invoice.invoice_id} created. Status: {invoice.status}",
                )
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
