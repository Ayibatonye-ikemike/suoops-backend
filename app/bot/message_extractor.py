from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_message(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the first message object from a WhatsApp webhook payload."""
    if not isinstance(payload, dict):
        return None

    # Already normalized payload
    if "entry" not in payload:
        message = dict(payload)
        message.setdefault("raw", payload)
        return message

    try:
        entry = payload.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return None

        message = messages[0]
        sender = message.get("from")
        if not sender:
            return None

        msg_type = message.get("type", "text")
        normalized_sender = sender if sender.startswith("+") else f"+{sender}"

        extracted: dict[str, Any] = {"from": normalized_sender, "type": msg_type}

        if msg_type == "text":
            extracted["text"] = message.get("text", {}).get("body", "")
        elif msg_type == "audio":
            extracted["audio_id"] = message.get("audio", {}).get("id")
        elif msg_type == "interactive":
            # Handle interactive button replies
            interactive = message.get("interactive", {})
            interactive_type = interactive.get("type")
            if interactive_type == "button_reply":
                # Button was clicked - extract button ID and title
                button_reply = interactive.get("button_reply", {})
                extracted["button_id"] = button_reply.get("id")
                extracted["button_title"] = button_reply.get("title")
                logger.info("[EXTRACT] Button clicked: id=%s, title=%s", 
                           extracted.get("button_id"), extracted.get("button_title"))

        contacts = value.get("contacts", [])
        if contacts:
            extracted["contact"] = contacts[0]

        extracted["raw"] = payload
        return extracted
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to parse WhatsApp webhook payload: %s", exc)
        return None
