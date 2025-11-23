"""Utility helpers for consistent Redis TLS configuration."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
import ssl

import certifi

from app.core.config import settings

_BASE_DIR = Path(__file__).resolve().parents[1]
_DEFAULT_HEROKU_CA = _BASE_DIR / "certs" / "heroku-redis-ca.pem"
_ALLOWED_CERT_REQS = {"none", "optional", "required"}


def _add_query_param(url: str, key: str, value: str | None) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if value is None:
        query.pop(key, None)
    else:
        query[key] = [value]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def get_ca_cert_path() -> str:
    """Return CA bundle path, defaulting to bundled Heroku cert."""
    if settings.REDIS_SSL_CA_CERTS:
        return settings.REDIS_SSL_CA_CERTS
    if _DEFAULT_HEROKU_CA.exists():
        return str(_DEFAULT_HEROKU_CA)
    return certifi.where()


def normalize_cert_reqs(value: str | None = None) -> str:
    """Normalize ssl_cert_reqs string with production safety overrides."""
    candidate = (value or settings.REDIS_SSL_CERT_REQS or "required").lower()
    if candidate not in _ALLOWED_CERT_REQS:
        candidate = "required"
    if settings.ENV.lower() == "prod" and candidate == "none":
        # Force verification in production to avoid MITM and TLS downgrades
        return "required"
    return candidate


def map_cert_reqs(value: str | None = None) -> int:
    """Map ssl_cert_reqs string to ssl module constant."""
    normalized = normalize_cert_reqs(value)
    mapping = {
        "none": ssl.CERT_NONE,
        "optional": ssl.CERT_OPTIONAL,
        "required": ssl.CERT_REQUIRED,
    }
    return mapping[normalized]


def prepare_redis_url(url: str | None) -> str | None:
    """Append TLS query params to Redis URL when using rediss."""
    if not url:
        return url
    if url.startswith("rediss://"):
        url = _add_query_param(url, "ssl_cert_reqs", normalize_cert_reqs())
        url = _add_query_param(url, "ssl_ca_certs", get_ca_cert_path())
    return url


def get_ssl_options() -> dict[str, Any] | None:
    """Return ssl options dict for redis/ Celery when using TLS."""
    url = settings.REDIS_URL
    if not url or not url.startswith("rediss://"):
        return None
    return {
        "ssl_cert_reqs": map_cert_reqs(),
        "ssl_ca_certs": get_ca_cert_path(),
    }
