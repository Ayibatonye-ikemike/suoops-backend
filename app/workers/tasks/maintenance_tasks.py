"""Periodic maintenance tasks — subscription expiry, data cleanup."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from app.workers.celery_app import celery_app
from app.workers.tasks.messaging_tasks import session_scope

logger = logging.getLogger(__name__)


@celery_app.task(
    name="maintenance.downgrade_expired_subscriptions",
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_kwargs={"max_retries": 2},
    soft_time_limit=120,
    time_limit=180,
)
def downgrade_expired_subscriptions() -> dict[str, Any]:
    """Downgrade users whose PRO subscription has expired to FREE.

    Runs daily. Preserves invoice balance (they paid for those).
    """
    from app.models.models import SubscriptionPlan, User

    now = dt.datetime.now(dt.timezone.utc)
    downgraded = 0

    try:
        with session_scope() as db:
            expired_users = db.query(User).filter(
                User.plan == SubscriptionPlan.PRO,
                User.subscription_expires_at.isnot(None),
                User.subscription_expires_at < now,
            ).all()

            for user in expired_users:
                old_plan = user.plan.value
                user.plan = SubscriptionPlan.FREE
                downgraded += 1
                logger.info(
                    "Downgraded user %s from %s to FREE (expired %s)",
                    user.id, old_plan, user.subscription_expires_at,
                )

            db.commit()

        logger.info("Subscription expiry check: %d users downgraded", downgraded)
        return {"success": True, "downgraded": downgraded}

    except Exception as exc:
        logger.warning("Subscription expiry task failure: %s", exc)
        raise


@celery_app.task(
    name="maintenance.cleanup_stale_webhooks",
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_kwargs={"max_retries": 1},
    soft_time_limit=120,
    time_limit=180,
)
def cleanup_stale_webhooks() -> dict[str, Any]:
    """Delete webhook events older than 90 days to prevent table bloat."""
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=90)
    deleted = 0

    try:
        with session_scope() as db:
            from app.models.models import WebhookEvent

            deleted = db.query(WebhookEvent).filter(
                WebhookEvent.created_at < cutoff,
            ).delete(synchronize_session=False)
            db.commit()

        logger.info("Webhook cleanup: deleted %d events older than 90 days", deleted)
        return {"success": True, "deleted": deleted}

    except Exception as exc:
        logger.warning("Webhook cleanup task failure: %s", exc)
        raise
