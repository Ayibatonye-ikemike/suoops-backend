"""Periodic maintenance tasks — subscription expiry, data cleanup, inactive account purge."""
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


# ═══════════════════════════════════════════════════════════════════════
# INACTIVE ACCOUNT CLEANUP
# ═══════════════════════════════════════════════════════════════════════

# Users inactive for 90+ days with zero invoices get a warning email.
# 7 days later, if still inactive and zero invoices, account is deleted.

INACTIVE_DAYS = 90  # 3 months
WARNING_DAYS_BEFORE_DELETE = 7
WARNING_EMAIL_TYPE = "inactive_deletion_warning"


@celery_app.task(
    name="maintenance.warn_inactive_accounts",
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_kwargs={"max_retries": 2},
    soft_time_limit=300,
    time_limit=360,
)
def warn_inactive_accounts() -> dict[str, Any]:
    """Send deletion warning to inactive empty accounts.

    Targets users who:
    - Last login was 90+ days ago (or never logged in and created 90+ days ago)
    - Have zero invoices (both revenue and expense)
    - Are on the FREE plan
    - Haven't already been warned

    Runs weekly. Warning email gives 7 days notice before deletion.
    """
    from sqlalchemy import func

    from app.models.models import Invoice, SubscriptionPlan, User, UserEmailLog
    from app.utils.smtp import send_smtp_email as _send_smtp_email

    stats = {"warned": 0, "skipped": 0, "failed": 0}

    try:
        with session_scope() as db:
            now = dt.datetime.now(dt.timezone.utc)
            cutoff = now - dt.timedelta(days=INACTIVE_DAYS)

            # Find inactive free users with zero invoices
            inactive_users = (
                db.query(User)
                .outerjoin(Invoice, Invoice.issuer_id == User.id)
                .filter(
                    User.plan == SubscriptionPlan.FREE,
                    # Inactive: last_login before cutoff, or never logged in and created before cutoff
                    db.query(func.literal(True)).filter(
                        ((User.last_login != None) & (User.last_login < cutoff))  # noqa: E711
                        | ((User.last_login == None) & (User.created_at < cutoff))  # noqa: E711
                    ).exists(),
                )
                .group_by(User.id)
                .having(func.count(Invoice.id) == 0)
                .all()
            )

            if not inactive_users:
                logger.info("No inactive empty accounts found")
                return {"success": True, **stats}

            logger.info("Found %d inactive empty accounts", len(inactive_users))

            for user in inactive_users:
                # Skip if already warned
                already_warned = (
                    db.query(UserEmailLog.id)
                    .filter(
                        UserEmailLog.user_id == user.id,
                        UserEmailLog.email_type == WARNING_EMAIL_TYPE,
                    )
                    .first()
                )
                if already_warned:
                    stats["skipped"] += 1
                    continue

                # Skip if no email to warn them
                if not user.email:
                    stats["skipped"] += 1
                    continue

                name = (user.name or "").split()[0] or "there"
                last_active = user.last_login or user.created_at
                days_inactive = (now - last_active.replace(tzinfo=dt.timezone.utc)
                                 if last_active.tzinfo is None
                                 else now - last_active).days

                subject = "Your SuoOps account will be deleted in 7 days"
                plain = (
                    f"Hi {name},\n\n"
                    f"Your SuoOps account has been inactive for {days_inactive} days "
                    f"and has no invoices.\n\n"
                    f"Your account will be permanently deleted in 7 days unless you "
                    f"log in and create an invoice.\n\n"
                    f"Log in now: https://suoops.com/login\n\n"
                    f"If you want to keep your account, simply log in before the deadline.\n\n"
                    f"— The SuoOps Team"
                )

                if _send_smtp_email(user.email, subject, None, plain):
                    db.add(UserEmailLog(user_id=user.id, email_type=WARNING_EMAIL_TYPE))
                    db.commit()
                    stats["warned"] += 1
                    logger.info("Sent deletion warning to user %s (%s)", user.id, user.email)
                else:
                    stats["failed"] += 1

        logger.info("Inactive account warnings: %s", stats)
        return {"success": True, **stats}

    except Exception as exc:
        logger.error("Inactive account warning task failed: %s", exc)
        raise


@celery_app.task(
    name="maintenance.delete_inactive_accounts",
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_kwargs={"max_retries": 2},
    soft_time_limit=300,
    time_limit=360,
)
def delete_inactive_accounts() -> dict[str, Any]:
    """Delete inactive empty accounts that were warned 7+ days ago.

    Only deletes users who:
    - Were warned (have WARNING_EMAIL_TYPE in UserEmailLog)
    - Warning was sent 7+ days ago
    - Still have zero invoices
    - Still on FREE plan
    - Still inactive (haven't logged in since the warning)

    Runs weekly, 1 day after the warning task.
    """
    from sqlalchemy import func

    from app.models.models import Invoice, SubscriptionPlan, User, UserEmailLog
    from app.services.account_deletion_service import AccountDeletionService

    stats = {"deleted": 0, "skipped": 0, "failed": 0}

    try:
        with session_scope() as db:
            now = dt.datetime.now(dt.timezone.utc)
            warning_cutoff = now - dt.timedelta(days=WARNING_DAYS_BEFORE_DELETE)

            # Find users who were warned 7+ days ago
            warned_users = (
                db.query(User)
                .join(
                    UserEmailLog,
                    (UserEmailLog.user_id == User.id)
                    & (UserEmailLog.email_type == WARNING_EMAIL_TYPE)
                    & (UserEmailLog.sent_at < warning_cutoff),
                )
                .outerjoin(Invoice, Invoice.issuer_id == User.id)
                .filter(
                    User.plan == SubscriptionPlan.FREE,
                )
                .group_by(User.id)
                .having(func.count(Invoice.id) == 0)
                .all()
            )

            if not warned_users:
                logger.info("No accounts ready for deletion")
                return {"success": True, **stats}

            logger.info("Found %d accounts ready for deletion", len(warned_users))

            service = AccountDeletionService(db)

            for user in warned_users:
                # Double-check: skip if they logged in after the warning
                warning_log = (
                    db.query(UserEmailLog.sent_at)
                    .filter(
                        UserEmailLog.user_id == user.id,
                        UserEmailLog.email_type == WARNING_EMAIL_TYPE,
                    )
                    .order_by(UserEmailLog.sent_at.desc())
                    .first()
                )
                if warning_log and user.last_login:
                    warning_sent = warning_log[0]
                    if warning_sent.tzinfo is None:
                        warning_sent = warning_sent.replace(tzinfo=dt.timezone.utc)
                    last_login = user.last_login
                    if last_login.tzinfo is None:
                        last_login = last_login.replace(tzinfo=dt.timezone.utc)
                    if last_login > warning_sent:
                        # User logged in after warning — they're active, skip
                        stats["skipped"] += 1
                        # Clean up the warning so they don't get deleted later
                        db.query(UserEmailLog).filter(
                            UserEmailLog.user_id == user.id,
                            UserEmailLog.email_type == WARNING_EMAIL_TYPE,
                        ).delete()
                        db.commit()
                        logger.info("User %s logged in after warning, skipping deletion", user.id)
                        continue

                try:
                    service.delete_account(user_id=user.id, deleted_by_user_id=None)
                    stats["deleted"] += 1
                    logger.info("Deleted inactive account: user %s (%s)", user.id, user.email)
                except Exception as e:
                    stats["failed"] += 1
                    logger.warning("Failed to delete user %s: %s", user.id, e)

        logger.info("Inactive account deletion: %s", stats)
        return {"success": True, **stats}

    except Exception as exc:
        logger.error("Inactive account deletion task failed: %s", exc)
        raise
