from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from celery import Celery

from app.core.config import settings


def _ensure_ssl_required(redis_url: str) -> str:
    """Add ssl_cert_reqs=required to Redis URLs while preserving other params."""
    parsed = urlparse(redis_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["ssl_cert_reqs"] = ["required"]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _get_redis_url_with_ssl() -> str:
    """Get Redis URL with SSL parameters for hosted Redis (e.g. Heroku)."""
    redis_url = settings.REDIS_URL
    if redis_url and redis_url.startswith("rediss://"):
        return _ensure_ssl_required(redis_url)
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
