from __future__ import annotations

import ssl
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import certifi
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
        url_with_reqs = _add_query_param(redis_url, "ssl_cert_reqs", settings.REDIS_SSL_CERT_REQS)
        ca_path = settings.REDIS_SSL_CA_CERTS or certifi.where()
        return _add_query_param(url_with_reqs, "ssl_ca_certs", ca_path)
    return redis_url


def _map_cert_reqs(value: str | None) -> int:
    mapping = {
        "none": ssl.CERT_NONE,
        "optional": ssl.CERT_OPTIONAL,
        "required": ssl.CERT_REQUIRED,
    }
    if value is None:
        return ssl.CERT_NONE
    return mapping.get(value.lower(), ssl.CERT_REQUIRED)


def _get_redis_ssl_options() -> dict[str, Any] | None:
    redis_url = settings.REDIS_URL
    if not redis_url or not redis_url.startswith("rediss://"):
        return None

    ssl_options: dict[str, Any] = {
        "ssl_cert_reqs": _map_cert_reqs(settings.REDIS_SSL_CERT_REQS),
        "ssl_ca_certs": settings.REDIS_SSL_CA_CERTS or certifi.where(),
    }
    return ssl_options


def _create_celery() -> Celery:
    redis_url = _get_redis_url_with_ssl()
    ssl_options = _get_redis_ssl_options()
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
    return celery


celery_app = _create_celery()
