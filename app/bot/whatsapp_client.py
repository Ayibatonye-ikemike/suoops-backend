from __future__ import annotations

import logging
from typing import Any

import httpx
import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


class WhatsAppClient:
    """WhatsApp Cloud API client for sending messages and downloading media."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.phone_number_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", None)
        self.base_url = f"https://graph.facebook.com/v21.0/{self.phone_number_id}/messages"
        self.media_url = "https://graph.facebook.com/v21.0"

    def send_text(self, to: str, body: str) -> None:
        """Send a plain text message."""
        if not self.phone_number_id or not self.api_key:
            logger.warning("[WHATSAPP] Not configured, would send to %s: %s", to, body)
            return

        try:
            payload = {
                "messaging_product": "whatsapp",
                "to": to.replace("+", ""),
                "type": "text",
                "text": {"body": body},
            }
            response = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            logger.info("[WHATSAPP] ✓ Sent to %s: %s", to, body[:50])
        except Exception as exc:  # noqa: BLE001
            logger.error("[WHATSAPP] Failed to send to %s: %s", to, exc)

    def send_document(self, to: str, url: str, filename: str, caption: str | None = None) -> None:
        """Send a document (usually PDF)."""
        if not self.phone_number_id or not self.api_key:
            logger.warning("[WHATSAPP DOC] Not configured, would send to %s: %s", to, filename)
            return

        try:
            document: dict[str, Any] = {"link": url, "filename": filename}
            if caption:
                document["caption"] = caption

            payload = {
                "messaging_product": "whatsapp",
                "to": to.replace("+", ""),
                "type": "document",
                "document": document,
            }

            response = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            logger.info("[WHATSAPP DOC] ✓ Sent to %s: %s", to, filename)
        except Exception as exc:  # noqa: BLE001
            logger.error("[WHATSAPP DOC] Failed to send to %s: %s", to, exc)

    def send_template(
        self,
        to: str,
        template_name: str,
        language: str,
        components: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Send a pre-approved template message."""
        if not self.phone_number_id or not self.api_key:
            logger.warning(
                "[WHATSAPP TEMPLATE] Not configured, would send to %s: %s",
                to,
                template_name,
            )
            return False

        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to.replace("+", ""),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
            },
        }

        if components:
            payload["template"]["components"] = components

        try:
            response = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            logger.info("[WHATSAPP TEMPLATE] ✓ Sent to %s with %s", to, template_name)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("[WHATSAPP TEMPLATE] Failed to send to %s: %s", to, exc)
            return False

    async def get_media_url(self, media_id: str) -> str:
        """Resolve a media ID into a downloadable URL."""
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
        """Download media bytes from the WhatsApp CDN."""
        if not self.api_key:
            raise ValueError("WhatsApp not configured")

        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(media_url, headers=headers)
            response.raise_for_status()
            logger.info("[WHATSAPP] Downloaded %d bytes", len(response.content))
            return response.content
