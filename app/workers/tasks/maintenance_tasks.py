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


# ═══════════════════════════════════════════════════════════════════════
# CHURNED BUSINESS RE-ENGAGEMENT
# ═══════════════════════════════════════════════════════════════════════

# Real businesses who created invoices but went inactive 30+ days ago.
# Different from zero-invoice cleanup — these users had real activity.

CHURN_INACTIVE_DAYS = 30
CHURN_MIN_INVOICES = 3  # Must have created at least 3 invoices (real usage)
CHURN_EMAIL_TYPES = {
    30: "churn_winback_30d",
    60: "churn_winback_60d",
    90: "churn_winback_90d",
}


@celery_app.task(
    name="maintenance.winback_churned_businesses",
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_kwargs={"max_retries": 2},
    soft_time_limit=300,
    time_limit=360,
)
def winback_churned_businesses() -> dict[str, Any]:
    """Re-engage real businesses that stopped using SuoOps.

    Targets users who:
    - Created 3+ invoices (real usage, not just testing)
    - Last login was 30+ days ago
    - NOT already deleted or warned for zero-invoice cleanup

    Sends tiered messages:
    - 30 days: "We miss you" + their stats
    - 60 days: "Your customers might have unpaid invoices"
    - 90 days: Final "come back or your data stays safe"

    Runs weekly on Wednesdays.
    """
    from sqlalchemy import func

    from app.models.models import Invoice, User, UserEmailLog
    from app.utils.smtp import send_smtp_email as _send_smtp_email

    stats = {"sent_30d": 0, "sent_60d": 0, "sent_90d": 0, "skipped": 0, "failed": 0}

    try:
        with session_scope() as db:
            now = dt.datetime.now(dt.timezone.utc)

            # Find users with 3+ invoices who are inactive
            invoice_counts = (
                db.query(
                    Invoice.issuer_id,
                    func.count(Invoice.id).label("cnt"),
                    func.sum(Invoice.amount).label("total_revenue"),
                    func.count(Invoice.id).filter(Invoice.status == "paid").label("paid_cnt"),
                    func.count(Invoice.id).filter(Invoice.status == "pending").label("pending_cnt"),
                )
                .filter(Invoice.invoice_type == "revenue")
                .group_by(Invoice.issuer_id)
                .having(func.count(Invoice.id) >= CHURN_MIN_INVOICES)
                .subquery()
            )

            churned_users = (
                db.query(User, invoice_counts)
                .join(invoice_counts, User.id == invoice_counts.c.issuer_id)
                .filter(
                    # Inactive for 30+ days
                    (
                        (User.last_login.isnot(None)) & (User.last_login < now - dt.timedelta(days=CHURN_INACTIVE_DAYS))
                    ) | (
                        (User.last_login.is_(None)) & (User.created_at < now - dt.timedelta(days=CHURN_INACTIVE_DAYS))
                    ),
                )
                .all()
            )

            if not churned_users:
                logger.info("No churned businesses found for winback")
                return {"success": True, **stats}

            logger.info("Found %d churned businesses for winback", len(churned_users))

            for row in churned_users:
                user = row[0]
                total_invoices = row.cnt
                total_revenue = float(row.total_revenue or 0)
                paid_count = row.paid_cnt
                pending_count = row.pending_cnt

                last_active = user.last_login or user.created_at
                if last_active.tzinfo is None:
                    last_active = last_active.replace(tzinfo=dt.timezone.utc)
                days_inactive = (now - last_active).days

                # Determine which tier to send
                if days_inactive >= 90:
                    tier = 90
                elif days_inactive >= 60:
                    tier = 60
                else:
                    tier = 30

                email_type = CHURN_EMAIL_TYPES[tier]

                # Skip if already sent this tier
                already_sent = (
                    db.query(UserEmailLog.id)
                    .filter(
                        UserEmailLog.user_id == user.id,
                        UserEmailLog.email_type == email_type,
                    )
                    .first()
                )
                if already_sent:
                    stats["skipped"] += 1
                    continue

                name = (user.name or "").split()[0] or "there"
                biz = user.business_name or "your business"
                revenue_str = f"₦{total_revenue:,.0f}" if total_revenue else "₦0"

                # ── Build message per tier ──
                if tier == 30:
                    subject = f"We miss {biz} on SuoOps"
                    plain = (
                        f"Hi {name},\n\n"
                        f"It's been {days_inactive} days since you last used SuoOps. "
                        f"Here's what you've built so far:\n\n"
                        f"• {total_invoices} invoices created\n"
                        f"• {revenue_str} total revenue tracked\n"
                        f"• {paid_count} paid, {pending_count} still pending\n\n"
                        f"Your customers might be waiting to pay those pending invoices. "
                        f"Log in and send a reminder:\n"
                        f"https://suoops.com/login\n\n"
                        f"— The SuoOps Team"
                    )
                elif tier == 60:
                    subject = f"{name}, you have {pending_count} unpaid invoices on SuoOps"
                    plain = (
                        f"Hi {name},\n\n"
                        f"It's been {days_inactive} days since you logged into SuoOps.\n\n"
                        f"You have {pending_count} pending invoices worth tracking. "
                        f"Your customers might have forgotten — a quick reminder from "
                        f"SuoOps could help you collect.\n\n"
                        f"Log in to review: https://suoops.com/login\n\n"
                        f"If you've moved on, no worries — your data is safe with us.\n\n"
                        f"— The SuoOps Team"
                    )
                else:  # 90 days
                    subject = f"Your SuoOps data is still safe, {name}"
                    plain = (
                        f"Hi {name},\n\n"
                        f"It's been {days_inactive} days since your last visit. "
                        f"Your invoices, customers, and {revenue_str} in revenue records "
                        f"are still safely stored.\n\n"
                        f"If you'd like to pick up where you left off: "
                        f"https://suoops.com/login\n\n"
                        f"We're not going anywhere — your account stays active.\n\n"
                        f"— The SuoOps Team"
                    )

                # Try email first
                sent = False
                if user.email:
                    sent = _send_smtp_email(user.email, subject, None, plain)

                # Also send WhatsApp if they have a verified phone
                if user.phone and user.phone_verified:
                    try:
                        from app.core.whatsapp import get_whatsapp_client
                        client = get_whatsapp_client()
                        wa_msg = (
                            f"Hi {name} 👋\n\n"
                            f"It's been {days_inactive} days since you used SuoOps.\n\n"
                        )
                        if tier == 30:
                            wa_msg += (
                                f"You have {pending_count} pending invoices ({revenue_str} tracked). "
                                f"Your customers might be ready to pay — send a quick reminder?\n\n"
                                f"Tap to log in: https://suoops.com/login"
                            )
                        elif tier == 60:
                            wa_msg += (
                                f"You still have {pending_count} unpaid invoices. "
                                f"A quick reminder could help you collect.\n\n"
                                f"Log in: https://suoops.com/login"
                            )
                        else:
                            wa_msg += (
                                f"Your {total_invoices} invoices and {revenue_str} in records "
                                f"are still safe. Pick up where you left off anytime.\n\n"
                                f"https://suoops.com/login"
                            )
                        client.send_text(user.phone, wa_msg)
                        sent = True
                    except Exception as e:
                        logger.warning("WhatsApp winback failed for user %s: %s", user.id, e)

                if sent:
                    db.add(UserEmailLog(user_id=user.id, email_type=email_type))
                    db.commit()
                    stats[f"sent_{tier}d"] += 1
                    logger.info(
                        "Sent %s winback to user %s (%s) — %d invoices, %s revenue",
                        email_type, user.id, biz, total_invoices, revenue_str,
                    )
                else:
                    stats["failed"] += 1

        logger.info("Churned business winback: %s", stats)
        return {"success": True, **stats}

    except Exception as exc:
        logger.error("Churned business winback task failed: %s", exc)
        raise


# ═══════════════════════════════════════════════════════════════════════
# ZERO-INVOICE ACTIVATION NUDGE
# ═══════════════════════════════════════════════════════════════════════

# Users who signed up but never created an invoice.  Tiered nudges at
# 1 day (quick reminder), 3 days (value pitch), and 7 days (urgency).
# Only targets WhatsApp-verified users so we can reach them directly.

ACTIVATION_NUDGE_TIERS = {
    1: "activation_nudge_1d",
    3: "activation_nudge_3d",
    7: "activation_nudge_7d",
}


@celery_app.task(
    name="maintenance.nudge_zero_invoice_users",
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_kwargs={"max_retries": 2},
    soft_time_limit=300,
    time_limit=360,
)
def nudge_zero_invoice_users() -> dict[str, Any]:
    """Send activation nudges to users who signed up but never created an invoice.

    Targets WhatsApp-verified users at 3 tiers:
    - 1 day:  Quick "need help?" reminder
    - 3 days: Value pitch — what they're missing
    - 7 days: Urgency — free invoices waiting

    Skips users who already received a nudge for the given tier.
    Runs daily at 10:00 WAT (09:00 UTC).
    """
    from sqlalchemy import func

    from app.models.models import Invoice, User, UserEmailLog

    stats = {"sent_1d": 0, "sent_3d": 0, "sent_7d": 0, "skipped": 0, "failed": 0}

    try:
        with session_scope() as db:
            now = dt.datetime.now(dt.timezone.utc)

            # All user IDs who have created at least one invoice
            users_with_invoices = db.query(func.distinct(Invoice.issuer_id)).subquery()

            # Zero-invoice, WhatsApp-verified users signed up 1-14 days ago
            candidates = (
                db.query(User)
                .filter(
                    User.phone.isnot(None),
                    User.phone_verified.is_(True),
                    ~User.id.in_(db.query(users_with_invoices)),
                    User.created_at >= now - dt.timedelta(days=14),
                    User.created_at < now - dt.timedelta(hours=20),  # At least ~1 day old
                )
                .all()
            )

            if not candidates:
                logger.info("No zero-invoice users to nudge")
                return {"success": True, **stats}

            logger.info("Found %d zero-invoice users for activation nudge", len(candidates))

            for user in candidates:
                created = user.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=dt.timezone.utc)
                days_since = (now - created).days

                # Pick the right tier
                if days_since >= 7:
                    tier = 7
                elif days_since >= 3:
                    tier = 3
                else:
                    tier = 1

                email_type = ACTIVATION_NUDGE_TIERS[tier]

                # Skip if already sent this tier
                already_sent = (
                    db.query(UserEmailLog.id)
                    .filter(
                        UserEmailLog.user_id == user.id,
                        UserEmailLog.email_type == email_type,
                    )
                    .first()
                )
                if already_sent:
                    stats["skipped"] += 1
                    continue

                name = (user.name or "").split()[0] or "there"

                # Build WhatsApp message per tier
                if tier == 1:
                    msg = (
                        f"Hi {name} 👋\n\n"
                        f"Welcome to SuoOps! You signed up yesterday but haven't "
                        f"created your first invoice yet.\n\n"
                        f"It takes less than 30 seconds — just type what you sold "
                        f"and we'll generate a professional PDF invoice.\n\n"
                        f"💡 *Try it now:* Send a message like:\n"
                        f"_\"Invoice Chidi 08012345678, 5000 hair, 3000 nails\"_\n\n"
                        f"That's it! We'll create and send the invoice for you.\n\n"
                        f"Need help? Just reply *help* 🙂"
                    )
                elif tier == 3:
                    msg = (
                        f"Hi {name} 👋\n\n"
                        f"You signed up for SuoOps {days_since} days ago — "
                        f"here's what you're missing:\n\n"
                        f"✅ Professional PDF invoices your customers will trust\n"
                        f"✅ Automatic payment tracking — know who paid and who didn't\n"
                        f"✅ Business reports — see your revenue at a glance\n"
                        f"✅ Inventory management — track your stock\n\n"
                        f"🎁 You have *2 free invoices* waiting. "
                        f"Create your first one now — just send us what you sold!\n\n"
                        f"Example: _\"Invoice Amaka 08098765432, 10000 shoes\"_"
                    )
                else:  # 7 days
                    msg = (
                        f"Hi {name},\n\n"
                        f"It's been a week since you joined SuoOps and your "
                        f"*2 free invoices* are still unused! 🎁\n\n"
                        f"Other business owners are already:\n"
                        f"📊 Tracking ₦41M+ in revenue\n"
                        f"📱 Creating invoices straight from WhatsApp\n"
                        f"💰 Getting paid faster with payment reminders\n\n"
                        f"Don't miss out — create your first invoice in seconds.\n\n"
                        f"Just send: _\"Invoice [customer name] [phone], [amount] [item]\"_\n\n"
                        f"Or visit: https://suoops.com/login"
                    )

                try:
                    from app.core.whatsapp import get_whatsapp_client
                    client = get_whatsapp_client()
                    client.send_text(user.phone, msg)

                    db.add(UserEmailLog(user_id=user.id, email_type=email_type))
                    db.commit()
                    stats[f"sent_{tier}d"] += 1
                    logger.info(
                        "Sent %s nudge to user %s (%s)",
                        email_type, user.id, user.name,
                    )
                except Exception as e:
                    logger.warning("Activation nudge failed for user %s: %s", user.id, e)
                    stats["failed"] += 1

        logger.info("Zero-invoice activation nudge: %s", stats)
        return {"success": True, **stats}

    except Exception as exc:
        logger.error("Zero-invoice activation nudge task failed: %s", exc)
        raise
