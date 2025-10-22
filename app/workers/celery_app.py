from __future__ import annotations

from celery import Celery

from app.core.config import settings


def _get_redis_url_with_ssl() -> str:
    """Get Redis URL with SSL parameters for Heroku Redis"""
    redis_url = settings.REDIS_URL
    if redis_url and redis_url.startswith("rediss://"):
        # Add SSL cert requirements parameter for Heroku Redis
        return f"{redis_url}?ssl_cert_reqs=none"
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
