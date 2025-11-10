from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import certifi
from slowapi import Limiter
from slowapi.util import get_remote_address
import threading

try:  # pragma: no cover
    from prometheus_client import Counter
    _PROM_RATE_LIMIT = Counter("suoops_rate_limit_exceeded_events", "Rate limit exceeded events (handler invocations)")
except Exception:  # noqa: BLE001
    _PROM_RATE_LIMIT = None
from app.core.config import settings


def _add_query_param(url: str, key: str, value: str | None) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if value is None:
        query.pop(key, None)
    else:
        query[key] = [value]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


storage_uri = "memory://"
if settings.ENV.lower() == "prod":
    redis_url = settings.REDIS_URL
    if redis_url and redis_url.startswith("rediss://"):
        # Use centralized pool for rate limiting too - add pool size params
        storage_uri = _add_query_param(redis_url, "ssl_cert_reqs", settings.REDIS_SSL_CERT_REQS)
        ca_path = settings.REDIS_SSL_CA_CERTS or certifi.where()
        storage_uri = _add_query_param(storage_uri, "ssl_ca_certs", ca_path)
        # Limit connections used by rate limiter
        storage_uri = _add_query_param(storage_uri, "max_connections", "5")
    else:
        storage_uri = redis_url or "memory://"

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

limiter = Limiter(key_func=get_remote_address, storage_uri=storage_uri)

def increment_rate_limit_exceeded():
    with _rate_limit_lock:
        _rate_limit_counters["exceeded"] += 1
    if _PROM_RATE_LIMIT:
        _PROM_RATE_LIMIT.inc()

def rate_limit_stats() -> dict[str, int]:
    with _rate_limit_lock:
        return dict(_rate_limit_counters)
