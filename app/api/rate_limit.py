from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings


def _ensure_ssl_required(redis_url: str) -> str:
    parsed = urlparse(redis_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["ssl_cert_reqs"] = ["required"]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


storage_uri = "memory://"
if settings.ENV.lower() == "prod":
    # Add SSL parameters for Heroku Redis
    redis_url = settings.REDIS_URL
    if redis_url and redis_url.startswith("rediss://"):
        storage_uri = _ensure_ssl_required(redis_url)
    else:
        storage_uri = redis_url or "memory://"

limiter = Limiter(key_func=get_remote_address, storage_uri=storage_uri)
