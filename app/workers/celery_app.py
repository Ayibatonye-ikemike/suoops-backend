from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings
from app.core.redis_utils import get_ssl_options, prepare_redis_url


def _create_celery() -> Celery:
    redis_url = prepare_redis_url(settings.REDIS_URL)
    ssl_options = get_ssl_options()
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
    if ssl_options:
        celery.conf.update(
            broker_use_ssl=ssl_options,
            redis_backend_use_ssl=ssl_options,
        )
    # Beat schedule (only active outside test env)
    if settings.ENV.lower() not in {"test"}:
        celery.conf.beat_schedule = {
            "monthly-tax-reports": {
                "task": "tax.generate_previous_month_reports",
                "schedule": crontab(minute=0, hour=2, day_of_month=1),  # 02:00 UTC first day
                "args": ["paid"],
            }
        }
    return celery


celery_app = _create_celery()
