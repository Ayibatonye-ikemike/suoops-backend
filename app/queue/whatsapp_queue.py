"""Simple WhatsApp message queue abstraction.

For MVP this attempts to push messages into Redis list; if Redis is unavailable,
falls back to an in-memory buffer. A background worker can later poll this.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import redis

from app.core.config import settings
from app.workers.tasks import process_whatsapp_inbound

logger = logging.getLogger(__name__)

_fallback_buffer: list[dict[str, Any]] = []

try:  # pragma: no cover - connection attempt
    _redis = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=0.5)
    _redis.ping()
    _ENABLED = True
except Exception:  # noqa: BLE001
    _redis = None
    _ENABLED = False
    logger.warning("Redis not available, using in-memory WhatsApp queue fallback")

KEY = "whatsapp:inbound"


def enqueue_message(payload: dict[str, Any]) -> None:
    # Prefer asynchronous Celery worker
    try:
        process_whatsapp_inbound.delay(payload)
        return
    except Exception:  # noqa: BLE001
        logger.exception("Celery dispatch failed; falling back to local processing path")
        try:
            process_whatsapp_inbound.apply(args=[payload])
            return
        except Exception:  # noqa: BLE001
            logger.exception("Inline Celery task execution failed; persisting payload")

    data = json.dumps(payload)
    if _ENABLED and _redis is not None:
        try:
            _redis.rpush(KEY, data)
            return
        except Exception:  # noqa: BLE001
            logger.exception("Failed pushing WhatsApp message to Redis; fallback buffer used")
    _fallback_buffer.append(payload)


def drain_fallback() -> list[dict]:  # utility for tests
    items = list(_fallback_buffer)
    _fallback_buffer.clear()
    return items
