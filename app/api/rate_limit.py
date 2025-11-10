from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
import logging
import ssl

import certifi
import redis
from slowapi import Limiter
from slowapi.util import get_remote_address
import threading

try:  # pragma: no cover
    from prometheus_client import Counter
    _PROM_RATE_LIMIT = Counter("suoops_rate_limit_exceeded_events", "Rate limit exceeded events (handler invocations)")
except Exception:  # noqa: BLE001
    _PROM_RATE_LIMIT = None
from app.core.config import settings

logger = logging.getLogger(__name__)


def _create_redis_storage_uri() -> str:
    """
    Create a properly configured Redis URI for SlowAPI/limits.
    
    SlowAPI uses the 'limits' library which creates its own Redis connection pool.
    We need to pass SSL configuration via the URI or create a custom storage.
    """
    if settings.ENV.lower() != "prod":
        logger.info("Rate limiter using in-memory storage (dev/test mode)")
        return "memory://"
    
    redis_url = settings.REDIS_URL
    if not redis_url or not redis_url.startswith("rediss://"):
        return redis_url or "memory://"
    
    # For Heroku Redis with SSL, we need to create a custom connection
    # since SlowAPI doesn't properly handle SSL parameters from query string
    logger.info("Rate limiter will use custom Redis client with proper SSL config")
    return "memory://"  # Fallback for now, will use custom storage below


def _create_custom_redis_client() -> redis.Redis | None:
    """
    Create a Redis client with proper SSL configuration for rate limiting.
    This bypasses SlowAPI's URI parsing issues.
    """
    if settings.ENV.lower() != "prod":
        return None
    
    redis_url = settings.REDIS_URL
    if not redis_url or not redis_url.startswith("rediss://"):
        return None
    
    try:
        # Use our centralized Redis pool
        from app.db.redis_client import get_redis_client
        client = get_redis_client()
        logger.info("Rate limiter using shared Redis pool with proper SSL configuration")
        return client
    except Exception as e:
        logger.warning("Failed to create Redis client for rate limiter: %s, falling back to memory", e)
        return None


# Configure rate limiter storage with custom Redis client
storage_uri = _create_redis_storage_uri()

# Try to use custom Redis client if in production
_custom_redis_client = _create_custom_redis_client()

if _custom_redis_client:
    # Create limiter with custom storage using our Redis pool
    from limits.storage import RedisStorage
    try:
        custom_storage = RedisStorage(uri=storage_uri, connection_pool=_custom_redis_client.connection_pool)
        limiter = Limiter(
            key_func=get_remote_address,
            storage_uri=custom_storage,
            storage_options={}
        )
        logger.info("Rate limiter initialized with shared Redis pool")
    except Exception as e:
        logger.error("Failed to create custom Redis storage for rate limiter: %s, using memory", e)
        limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
else:
    # Fall back to default (memory in dev, or if Redis unavailable)
    limiter = Limiter(key_func=get_remote_address, storage_uri=storage_uri)

RATE_LIMITS = {
    # Auth flows
    "signup_request": "5/minute" if settings.ENV.lower() == "prod" else "50/minute",
    "signup_verify": "10/minute",
    "login_request": "10/minute",
    "login_verify": "10/minute",
    "otp_resend": "10/minute",
    "refresh": "20/minute",
    # OAuth
    "oauth_login": "30/minute",
    "oauth_callback": "60/minute",
    # OCR
    "ocr_parse": "10/minute",
    "ocr_create_invoice": "10/minute",
    # Webhooks
    "webhook_whatsapp_verify": "120/minute",
    "webhook_whatsapp_inbound": "300/minute",
    "webhook_paystack": "60/minute",
}

_rate_limit_lock = threading.Lock()
_rate_limit_counters: dict[str, int] = {"exceeded": 0}

def increment_rate_limit_exceeded():
    with _rate_limit_lock:
        _rate_limit_counters["exceeded"] += 1
    if _PROM_RATE_LIMIT:
        _PROM_RATE_LIMIT.inc()

def rate_limit_stats() -> dict[str, int]:
    with _rate_limit_lock:
        return dict(_rate_limit_counters)
