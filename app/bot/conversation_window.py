"""Helpers for tracking the WhatsApp 24-hour conversation window.

WhatsApp Business API only allows sending free-form (non-template) messages
within 24 hours of the customer/user's last inbound message.  We use a Redis
key with a 24-hour TTL to track this window.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_WA_WINDOW_PREFIX = "wa:window:"
_WA_WINDOW_TTL = 86400  # 24 hours in seconds


def mark_conversation_active(phone: str) -> None:
    """Record that a user sent an inbound message (opens a 24-hour window)."""
    try:
        from app.db.redis_client import get_redis_client

        r = get_redis_client()
        r.setex(f"{_WA_WINDOW_PREFIX}{phone}", _WA_WINDOW_TTL, "1")
    except Exception:
        # Redis failure should never break message processing
        logger.debug("Failed to mark conversation window for %s", phone)


def is_window_open(phone: str) -> bool:
    """Check if a user's 24-hour conversation window is still open."""
    try:
        from app.db.redis_client import get_redis_client

        r = get_redis_client()
        return r.exists(f"{_WA_WINDOW_PREFIX}{phone}") > 0
    except Exception:
        logger.debug("Failed to check conversation window for %s", phone)
        return False
