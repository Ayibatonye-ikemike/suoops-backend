from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from celery import Celery

from app.core.config import settings


def _add_query_param(url: str, key: str, value: str | None) -> str:
    """Return URL with query parameter updated while preserving existing params."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if value is None:
        query.pop(key, None)
    else:
        query[key] = [value]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _get_redis_url_with_ssl() -> str:
    """Get Redis URL with configurable SSL parameters for hosted Redis."""
    redis_url = settings.REDIS_URL
    if redis_url and redis_url.startswith("rediss://"):
        return _add_query_param(redis_url, "ssl_cert_reqs", settings.REDIS_SSL_CERT_REQS)
    return redis_url


def _create_celery() -> Celery:
    redis_url = _get_redis_url_with_ssl()
    celery = Celery(
        "whatsinvoice",
        broker=redis_url,
        backend=redis_url,
        include=["app.workers.tasks"],
    )
    celery.conf.update(
        task_default_queue="default",
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_always_eager=settings.ENV.lower() in {"test"},
    )
    return celery


celery_app = _create_celery()
