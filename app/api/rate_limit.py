from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from slowapi import Limiter
from slowapi.util import get_remote_address

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
        storage_uri = _add_query_param(redis_url, "ssl_cert_reqs", settings.REDIS_SSL_CERT_REQS)
    else:
        storage_uri = redis_url or "memory://"

limiter = Limiter(key_func=get_remote_address, storage_uri=storage_uri)
