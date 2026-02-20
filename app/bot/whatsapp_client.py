from __future__ import annotations

import logging
import os
from typing import Any

import httpx
import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


class WhatsAppClient:
    """WhatsApp Cloud API client for sending messages and downloading media."""

    @staticmethod
    def _is_test_mode() -> bool:
        # Keep tests hermetic: never hit real WhatsApp APIs under pytest.
        if settings.ENV.lower() in {"test", "testing"}:
            return True
        return bool(os.getenv("PYTEST_CURRENT_TEST"))

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.phone_number_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", None)
        self.base_url = f"https://graph.facebook.com/v21.0/{self.phone_number_id}/messages"
        self.media_url = "https://graph.facebook.com/v21.0"

    def send_text(self, to: str, body: str) -> bool:
        """Send a plain text message. Returns True on success, False on failure."""
        if self._is_test_mode():
            logger.info("[WHATSAPP][TEST] Would send text to %s: %s", to, body[:200])
            return True
        if not self.phone_number_id or not self.api_key:
            logger.warning("[WHATSAPP] Not configured, would send to %s: %s", to, body)
            return False

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
            return True
        except requests.HTTPError as exc:  # pragma: no cover - external service
            detail = exc.response.text if exc.response is not None else "(no body)"
            logger.error(
                "[WHATSAPP] Failed to send to %s: %s | Response: %s",
                to,
                exc,
                detail,
            )
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error("[WHATSAPP] Failed to send to %s: %s", to, exc)
            return False

    def send_document(self, to: str, url: str, filename: str, caption: str | None = None) -> None:
        """Send a document (usually PDF). Accepts a URL or media_id."""
        if self._is_test_mode():
            logger.info("[WHATSAPP DOC][TEST] Would send to %s: %s (%s)", to, filename, url)
            return
        if not self.phone_number_id or not self.api_key:
            logger.warning("[WHATSAPP DOC] Not configured, would send to %s: %s", to, filename)
            return

        try:
            document: dict[str, Any] = {"filename": filename}
            if caption:
                document["caption"] = caption

            # If it looks like a media_id (no :// scheme), use "id"; otherwise "link"
            if "://" in url:
                document["link"] = url
            else:
                document["id"] = url

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

    def upload_media(self, data: bytes, mime_type: str = "application/pdf", filename: str = "document.pdf") -> str | None:
        """Upload media bytes directly to WhatsApp's Media API.

        Returns the media_id on success, or None on failure.
        """
        if self._is_test_mode():
            logger.info("[WHATSAPP MEDIA][TEST] Would upload %d bytes as %s", len(data), filename)
            return "test-media-id"
        if not self.phone_number_id or not self.api_key:
            logger.warning("[WHATSAPP MEDIA] Not configured")
            return None

        upload_url = f"{self.media_url}/{self.phone_number_id}/media"
        try:
            response = requests.post(
                upload_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                files={"file": (filename, data, mime_type)},
                data={"messaging_product": "whatsapp", "type": mime_type},
                timeout=30,
            )
            response.raise_for_status()
            media_id = response.json().get("id")
            logger.info("[WHATSAPP MEDIA] ✓ Uploaded %s → media_id=%s", filename, media_id)
            return media_id
        except Exception as exc:  # noqa: BLE001
            logger.error("[WHATSAPP MEDIA] Upload failed for %s: %s", filename, exc)
            return None

    def send_template(
        self,
        to: str,
        template_name: str,
        language: str,
        components: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Send a pre-approved template message."""
        if self._is_test_mode():
            logger.info(
                "[WHATSAPP TEMPLATE][TEST] Would send to %s: %s (%s)",
                to,
                template_name,
                language,
            )
            return True
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
            logger.info("[WHATSAPP TEMPLATE] Sending to %s, template=%s, payload=%s", to, template_name, payload)
            response = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10,
            )
            logger.info(
                "[WHATSAPP TEMPLATE] Response status=%s, body=%s",
                response.status_code,
                response.text[:500] if response.text else "empty",
            )
            response.raise_for_status()
            logger.info("[WHATSAPP TEMPLATE] ✓ Sent to %s with %s", to, template_name)
            return True
        except requests.HTTPError as exc:
            detail = exc.response.text if exc.response is not None else "(no body)"
            logger.error("[WHATSAPP TEMPLATE] HTTP Error to %s: %s | Response: %s", to, exc, detail)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error("[WHATSAPP TEMPLATE] Failed to send to %s: %s", to, exc)
            return False

    def send_otp_template(
        self,
        to: str,
        otp_code: str,
        template_name: str = "otp_verifications",
        language: str = "en",
    ) -> bool:
        """Send OTP verification code using approved authentication template.
        
        Uses Meta's authentication template format which allows sending to users
        who haven't messaged the business first (bypasses 24-hour window).
        
        Args:
            to: Recipient phone number
            otp_code: The OTP code to send
            template_name: Name of the approved auth template (default: otp_verifications)
            language: Template language code (default: en)
        
        Returns:
            True if sent successfully, False otherwise
        """
        # Authentication templates with "Copy code" button structure:
        # - Body: {{1}} is the OTP code
        # - Button: URL button with otp{{1}} parameter
        components = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": otp_code}
                ]
            },
            {
                "type": "button",
                "sub_type": "url",
                "index": "0",
                "parameters": [
                    {"type": "text", "text": otp_code}
                ]
            }
        ]
        
        logger.info("[WHATSAPP OTP] Sending OTP template '%s' to %s", template_name, to)
        return self.send_template(to, template_name, language, components)

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

    def send_interactive_list(
        self,
        to: str,
        body: str,
        button_text: str,
        sections: list[dict[str, Any]],
        header: str | None = None,
        footer: str | None = None,
    ) -> bool:
        """
        Send an interactive list message (product catalog, menu, etc.).

        WhatsApp limits:
            - Max 10 rows total across all sections
            - Row title max 24 chars, description max 72 chars
            - Button text max 20 chars

        Args:
            to: Recipient phone number
            body: Message body text
            button_text: Text on the button that opens the list
            sections: List of sections, each with 'title' and 'rows'.
                      Each row: {'id': str, 'title': str, 'description': str (optional)}
            header: Optional header text
            footer: Optional footer text

        Returns:
            True if sent successfully
        """
        if self._is_test_mode():
            logger.info("[WHATSAPP LIST][TEST] Would send list to %s: %s", to, body[:100])
            return True
        if not self.phone_number_id or not self.api_key:
            logger.warning("[WHATSAPP LIST] Not configured, would send to %s", to)
            return False

        # Enforce WhatsApp limits
        total_rows = sum(len(s.get("rows", [])) for s in sections)
        if total_rows > 10:
            logger.warning("[WHATSAPP LIST] Truncating to 10 rows (had %d)", total_rows)
            # Truncate rows to fit within 10
            remaining = 10
            for section in sections:
                rows = section.get("rows", [])
                section["rows"] = rows[:remaining]
                remaining -= len(section["rows"])
                if remaining <= 0:
                    break

        interactive: dict[str, Any] = {
            "type": "list",
            "body": {"text": body},
            "action": {
                "button": button_text[:20],
                "sections": sections,
            },
        }

        if header:
            interactive["header"] = {"type": "text", "text": header}
        if footer:
            interactive["footer"] = {"text": footer}

        payload = {
            "messaging_product": "whatsapp",
            "to": to.replace("+", ""),
            "type": "interactive",
            "interactive": interactive,
        }

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
            logger.info("[WHATSAPP LIST] ✓ Sent list to %s with %d items", to, total_rows)
            return True
        except requests.HTTPError as exc:
            detail = exc.response.text if exc.response is not None else "(no body)"
            logger.error("[WHATSAPP LIST] HTTP Error to %s: %s | Response: %s", to, exc, detail)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error("[WHATSAPP LIST] Failed to send to %s: %s", to, exc)
            return False

    def send_interactive_buttons(
        self,
        to: str,
        body: str,
        buttons: list[dict[str, str]],
        header: str | None = None,
        footer: str | None = None,
    ) -> bool:
        """
        Send an interactive message with reply buttons.
        
        Args:
            to: Recipient phone number
            body: Message body text
            buttons: List of buttons, each with 'id' and 'title' (max 3 buttons, title max 20 chars)
            header: Optional header text
            footer: Optional footer text
        
        Returns:
            True if sent successfully
        """
        if not self.phone_number_id or not self.api_key:
            logger.warning("[WHATSAPP BUTTONS] Not configured, would send to %s", to)
            return False

        # Build button rows (max 3 buttons allowed by WhatsApp)
        button_rows = [
            {"type": "reply", "reply": {"id": btn["id"], "title": btn["title"][:20]}}
            for btn in buttons[:3]
        ]

        interactive: dict[str, Any] = {
            "type": "button",
            "body": {"text": body},
            "action": {"buttons": button_rows},
        }

        if header:
            interactive["header"] = {"type": "text", "text": header}
        if footer:
            interactive["footer"] = {"text": footer}

        payload = {
            "messaging_product": "whatsapp",
            "to": to.replace("+", ""),
            "type": "interactive",
            "interactive": interactive,
        }

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
            logger.info("[WHATSAPP BUTTONS] ✓ Sent to %s with %d buttons", to, len(buttons))
            return True
        except requests.HTTPError as exc:
            detail = exc.response.text if exc.response is not None else "(no body)"
            logger.error("[WHATSAPP BUTTONS] HTTP Error to %s: %s | Response: %s", to, exc, detail)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error("[WHATSAPP BUTTONS] Failed to send to %s: %s", to, exc)
            return False
