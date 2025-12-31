import logging
import threading

import redis
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

try:  # pragma: no cover
    from prometheus_client import Counter
    _PROM_RATE_LIMIT = Counter("suoops_rate_limit_exceeded_events", "Rate limit exceeded events (handler invocations)")
except Exception:  # noqa: BLE001
    _PROM_RATE_LIMIT = None
from app.api.rate_limit_strategies import get_plan_from_token
from app.core.config import settings

logger = logging.getLogger(__name__)


def get_user_identifier(request: Request) -> str:
    """Get unique identifier for rate limiting that includes user plan.
    
    Uses JWT token to extract plan for dynamic rate limiting (Strategy pattern).
    Falls back to IP address for unauthenticated requests.
    
    Returns:
        Identifier in format: 'ip:plan' or just 'ip' for unauthenticated
        
    Example:
        >>> get_user_identifier(request)
        '192.168.1.1:pro'  # Authenticated PRO user
        '10.0.0.1:free'    # Unauthenticated (treated as free)
    """
    ip_address = get_remote_address(request)
    
    # Extract Bearer token from Authorization header
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Remove 'Bearer ' prefix
    
    # Get user's plan from token (defaults to 'free' if invalid/missing)
    plan = get_plan_from_token(token)
    
    # Include plan in identifier for per-plan rate limiting
    return f"{ip_address}:{plan}"


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
    # Use custom key function that includes user plan for dynamic rate limiting
    from limits.storage import RedisStorage
    try:
        custom_storage = RedisStorage(uri=storage_uri, connection_pool=_custom_redis_client.connection_pool)
        limiter = Limiter(
            key_func=get_user_identifier,  # Dynamic rate limiting by plan
            storage_uri=custom_storage,
            storage_options={}
        )
        logger.info("Rate limiter initialized with shared Redis pool and plan-based limits")
    except Exception as e:
        logger.error("Failed to create custom Redis storage for rate limiter: %s, using memory", e)
        limiter = Limiter(key_func=get_user_identifier, storage_uri="memory://")
else:
    # Fall back to default (memory in dev, or if Redis unavailable)
    limiter = Limiter(key_func=get_user_identifier, storage_uri=storage_uri)

RATE_LIMITS = {
    # Auth flows (same for all users - before authentication)
    "signup_request": "5/minute" if settings.ENV.lower() == "prod" else "50/minute",
    "signup_verify": "10/minute",
    "login_request": "10/minute",
    "login_verify": "10/minute",
    "otp_resend": "10/minute",
    "refresh": "20/minute",
    # OAuth
    "oauth_login": "30/minute",
    "oauth_callback": "60/minute",
    # OCR (uses dynamic limits based on plan)
    "ocr_parse": "10/minute",  # FREE fallback
    "ocr_create_invoice": "10/minute",  # FREE fallback
    # Webhooks
    "webhook_whatsapp_verify": "120/minute",
    "webhook_whatsapp_inbound": "300/minute",
    "webhook_paystack": "60/minute",
}


def get_dynamic_limit(request: Request) -> str:
    """Get dynamic rate limit based on user's subscription plan.
    
    Follows Strategy pattern - delegates to plan-specific strategies.
    Used for authenticated endpoints where plan affects limits.
    
    Args:
        request: Starlette request object
        
    Returns:
        Rate limit string (e.g., '60/minute' for PRO users)
        
    Example usage in route:
        @limiter.limit(get_dynamic_limit)
        async def create_invoice(...):
            ...
    """
    from app.api.rate_limit_strategies import get_plan_from_token, get_rate_limit_strategy
    
    # Extract Bearer token
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    
    # Get plan and corresponding strategy
    plan = get_plan_from_token(token)
    strategy = get_rate_limit_strategy(plan)
    
    return strategy.get_limit()

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
