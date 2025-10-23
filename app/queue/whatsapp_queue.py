"""Simple WhatsApp message queue abstraction.

For MVP this attempts to push messages into Redis list; if Redis is unavailable,
falls back to an in-memory buffer. A background worker can later poll this.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import redis
import certifi

from app.core.config import settings
from app.workers.tasks import process_whatsapp_inbound

logger = logging.getLogger(__name__)

_fallback_buffer: list[dict[str, Any]] = []

def _add_query_param(url: str, key: str, value: str | None) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if value is None:
        query.pop(key, None)
    else:
        query[key] = [value]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _prepare_redis_url(url: str) -> str:
    if url and url.startswith("rediss://"):
        url = _add_query_param(url, "ssl_cert_reqs", settings.REDIS_SSL_CERT_REQS)
        ca_path = settings.REDIS_SSL_CA_CERTS or certifi.where()
        url = _add_query_param(url, "ssl_ca_certs", ca_path)
    return url


try:  # pragma: no cover - connection attempt
    redis_url = _prepare_redis_url(settings.REDIS_URL)
    _redis = redis.Redis.from_url(redis_url, socket_timeout=0.5)
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
        logger.warning("Persisting WhatsApp payload for later processing")

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
