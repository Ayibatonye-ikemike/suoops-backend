from __future__ import annotations

from celery import Celery

from app.core.config import settings


def _create_celery() -> Celery:
    celery = Celery(
        "whatsinvoice",
        broker=settings.REDIS_URL,
        backend=settings.REDIS_URL,
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
