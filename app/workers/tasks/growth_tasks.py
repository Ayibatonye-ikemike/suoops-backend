"""Growth-focused tasks — aggregate unpaid alerts, weekly free summary, payment upsell.

Three tasks that target the key funnel gaps:
- Aggregate unpaid notification: "You have ₦145,000 unpaid across 6 invoices"
- Weekly free-user summary: Same as daily Pro summary, but weekly for free users
- Payment-triggered upsell: After collecting ≥₦50K, nudge toward Pro
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func as sqlfunc

from app.core.config import settings
from app.db.session import session_scope
from app.utils.smtp import send_smtp_email as _send_smtp_email
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _is_valid_phone(phone: str | None) -> bool:
    if not phone:
        return False
    digits = phone.lstrip("+")
    return digits.isdigit() and len(digits) >= 10


# ═══════════════════════════════════════════════════════════════════════
# TASK 1: AGGREGATE UNPAID AMOUNT NOTIFICATION
# ═══════════════════════════════════════════════════════════════════════

@celery_app.task(
    name="growth.send_aggregate_unpaid_alerts",
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_kwargs={"max_retries": 2},
    soft_time_limit=300,
    time_limit=360,
)
def send_aggregate_unpaid_alerts() -> dict[str, Any]:
    """Notify business owners of their total unpaid amount across all invoices.

    Runs twice a week (Mon + Thu at 09:00 WAT).
    Only notifies users who have ≥₦5,000 unpaid across ≥2 invoices.
    Deduplicates: won't re-send if the same total was sent within 3 days.
    """
    from app.models.models import Invoice, User, UserEmailLog

    stats = {"whatsapp_sent": 0, "email_sent": 0, "skipped": 0, "failed": 0}

    try:
        with session_scope() as db:
            # Find users with pending revenue invoices
            unpaid_data = (
                db.query(
                    Invoice.issuer_id,
                    sqlfunc.sum(Invoice.amount).label("total_unpaid"),
                    sqlfunc.count(Invoice.id).label("invoice_count"),
                )
                .filter(
                    Invoice.invoice_type == "revenue",
                    Invoice.status.in_(["pending", "awaiting_confirmation"]),
                )
                .group_by(Invoice.issuer_id)
                .having(
                    sqlfunc.sum(Invoice.amount) >= 5000,
                    sqlfunc.count(Invoice.id) >= 2,
                )
                .all()
            )

            if not unpaid_data:
                logger.info("No users with significant unpaid invoices")
                return {"success": True, **stats}

            from app.core.whatsapp import get_whatsapp_client
            from app.bot.conversation_window import is_window_open

            client = get_whatsapp_client()

            # Check for recent sends (don't spam)
            three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)

            for row in unpaid_data:
                user = db.query(User).filter(User.id == row.issuer_id).first()
                if not user:
                    continue

                # Dedup: skip if we sent this type recently
                recent = (
                    db.query(UserEmailLog.id)
                    .filter(
                        UserEmailLog.user_id == user.id,
                        UserEmailLog.email_type == "aggregate_unpaid",
                        UserEmailLog.sent_at >= three_days_ago,
                    )
                    .first()
                )
                if recent:
                    stats["skipped"] += 1
                    continue

                total = float(row.total_unpaid)
                count = int(row.invoice_count)
                name = (user.name or "").split()[0] or "there"
                s = "s" if count != 1 else ""

                message = (
                    f"💰 *Payment Alert*\n\n"
                    f"Hi {name}, you have *₦{total:,.0f}* unpaid "
                    f"across *{count} invoice{s}*.\n\n"
                    f"💡 Send reminders to collect faster — "
                    f"or check your dashboard:\n"
                    f"🔗 suoops.com/dashboard\n\n"
                    f"_Tip: Businesses that follow up within 3 days "
                    f"collect 40% faster._"
                )

                sent = False
                has_phone = _is_valid_phone(user.phone)

                # Try WhatsApp
                if has_phone:
                    template_name = getattr(settings, "WHATSAPP_TEMPLATE_UNPAID_ALERT", None)
                    if template_name:
                        lang = settings.WHATSAPP_TEMPLATE_LANGUAGE or "en"
                        ok = client.send_template(
                            user.phone,
                            template_name,
                            lang,
                            components=[{
                                "type": "body",
                                "parameters": [
                                    {"type": "text", "text": name},
                                    {"type": "text", "text": f"₦{total:,.0f}"},
                                    {"type": "text", "text": str(count)},
                                ],
                            }],
                        )
                        if ok:
                            stats["whatsapp_sent"] += 1
                            sent = True

                    if not sent and is_window_open(user.phone):
                        if client.send_text(user.phone, message):
                            stats["whatsapp_sent"] += 1
                            sent = True

                # Email fallback
                if not sent and user.email:
                    subject = f"You have ₦{total:,.0f} unpaid across {count} invoice{s}"
                    plain = (
                        f"Hi {name},\n\n"
                        f"You have ₦{total:,.0f} unpaid across {count} invoice{s}.\n\n"
                        f"Send reminders to collect faster: https://suoops.com/dashboard\n\n"
                        f"— SuoOps"
                    )
                    if _send_smtp_email(user.email, subject, None, plain):
                        stats["email_sent"] += 1
                        sent = True

                if sent:
                    db.add(UserEmailLog(user_id=user.id, email_type="aggregate_unpaid"))
                    db.flush()
                else:
                    stats["failed"] += 1

            db.commit()

        logger.info(
            "Aggregate unpaid alerts: wa=%d email=%d skipped=%d failed=%d",
            stats["whatsapp_sent"], stats["email_sent"],
            stats["skipped"], stats["failed"],
        )
        return {"success": True, **stats}

    except Exception as exc:
        logger.error("Aggregate unpaid alerts failed: %s", exc)
        raise


# ═══════════════════════════════════════════════════════════════════════
# TASK 2: WEEKLY FREE-USER SUMMARY
# ═══════════════════════════════════════════════════════════════════════

@celery_app.task(
    name="growth.send_weekly_free_summary",
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_kwargs={"max_retries": 2},
    soft_time_limit=300,
    time_limit=360,
)
def send_weekly_free_summary() -> dict[str, Any]:
    """Send weekly business summary to FREE users who have invoices.

    Runs every Monday at 09:00 WAT. Mirrors the daily Pro summary but
    covers the past 7 days and targets free users only.
    """
    from app.models.models import Invoice, SubscriptionPlan, User

    stats = {"whatsapp_sent": 0, "email_sent": 0, "skipped": 0, "failed": 0}

    try:
        with session_scope() as db:
            now_utc = datetime.now(timezone.utc)
            week_ago = now_utc - timedelta(days=7)

            # Free users who have created at least 1 revenue invoice ever
            free_users_with_invoices = (
                db.query(User)
                .filter(
                    User.plan == SubscriptionPlan.FREE,
                    (User.phone != None) | (User.email != None),  # noqa: E711
                )
                .join(Invoice, Invoice.issuer_id == User.id)
                .filter(Invoice.invoice_type == "revenue")
                .group_by(User.id)
                .having(sqlfunc.count(Invoice.id) >= 1)
                .all()
            )

            if not free_users_with_invoices:
                logger.info("No free users with invoices for weekly summary")
                return {"success": True, **stats}

            from app.core.whatsapp import get_whatsapp_client
            from app.bot.conversation_window import is_window_open

            client = get_whatsapp_client()

            for user in free_users_with_invoices:
                try:
                    has_phone = _is_valid_phone(user.phone)
                    name = (user.name or "").split()[0] or "there"

                    # Revenue collected this week
                    revenue_week = float(
                        db.query(sqlfunc.coalesce(sqlfunc.sum(Invoice.amount), 0))
                        .filter(
                            Invoice.issuer_id == user.id,
                            Invoice.invoice_type == "revenue",
                            Invoice.status == "paid",
                            Invoice.paid_at >= week_ago,
                        )
                        .scalar()
                    )

                    # Expenses this week
                    expenses_week = float(
                        db.query(sqlfunc.coalesce(sqlfunc.sum(Invoice.amount), 0))
                        .filter(
                            Invoice.issuer_id == user.id,
                            Invoice.invoice_type == "expense",
                            Invoice.created_at >= week_ago,
                        )
                        .scalar()
                    )

                    # Total outstanding
                    outstanding = float(
                        db.query(sqlfunc.coalesce(sqlfunc.sum(Invoice.amount), 0))
                        .filter(
                            Invoice.issuer_id == user.id,
                            Invoice.invoice_type == "revenue",
                            Invoice.status.in_(["pending", "awaiting_confirmation"]),
                        )
                        .scalar()
                    )

                    # Overdue count
                    overdue_count = (
                        db.query(sqlfunc.count(Invoice.id))
                        .filter(
                            Invoice.issuer_id == user.id,
                            Invoice.invoice_type == "revenue",
                            Invoice.status == "pending",
                            Invoice.due_date != None,  # noqa: E711
                            Invoice.due_date < now_utc,
                        )
                        .scalar()
                    ) or 0

                    # Skip if zero activity AND zero outstanding
                    if revenue_week == 0 and expenses_week == 0 and outstanding == 0:
                        stats["skipped"] += 1
                        continue

                    net = revenue_week - expenses_week

                    message = f"📊 *Your Weekly Summary*\n\n"
                    message += f"Hi {name}, here's your week:\n\n"

                    if revenue_week > 0:
                        message += f"💰 Collected: ₦{revenue_week:,.0f}\n"
                    if expenses_week > 0:
                        message += f"💸 Spent: ₦{expenses_week:,.0f}\n"
                    if revenue_week > 0 or expenses_week > 0:
                        emoji = "📈" if net >= 0 else "📉"
                        message += f"{emoji} Net: ₦{net:,.0f}\n"

                    message += "\n"

                    if outstanding > 0:
                        message += f"⏳ Still unpaid: ₦{outstanding:,.0f}\n"
                    if overdue_count > 0:
                        s = "s" if overdue_count != 1 else ""
                        message += f"⚠️ Overdue: {overdue_count} invoice{s}\n"

                    message += (
                        "\n🔗 suoops.com/dashboard\n\n"
                        "_Pro users get this daily + tax reports, "
                        "inventory & more. Upgrade for ₦3,250/mo._"
                    )

                    sent = False

                    # Try WhatsApp
                    if has_phone and is_window_open(user.phone):
                        if client.send_text(user.phone, message):
                            stats["whatsapp_sent"] += 1
                            sent = True

                    # Email fallback
                    if not sent and user.email:
                        subject = "Your Weekly Business Summary"
                        if _send_smtp_email(user.email, subject, None, message.replace("*", "")):
                            stats["email_sent"] += 1
                            sent = True

                    if not sent:
                        stats["failed"] += 1

                except Exception as e:
                    logger.warning("Weekly summary failed for user %s: %s", user.id, e)
                    stats["failed"] += 1

        logger.info(
            "Weekly free summary: wa=%d email=%d skipped=%d failed=%d",
            stats["whatsapp_sent"], stats["email_sent"],
            stats["skipped"], stats["failed"],
        )
        return {"success": True, **stats}

    except Exception as exc:
        logger.error("Weekly free summary failed: %s", exc)
        raise


# ═══════════════════════════════════════════════════════════════════════
# TASK 3: PAYMENT-TRIGGERED UPSELL
# ═══════════════════════════════════════════════════════════════════════

@celery_app.task(
    name="growth.send_payment_upsells",
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_kwargs={"max_retries": 2},
    soft_time_limit=300,
    time_limit=360,
)
def send_payment_upsells() -> dict[str, Any]:
    """Send outcome-based upsell to free users who have collected money.

    Triggers when a free user has:
    - Received ≥2 payments, OR
    - Collected ≥₦50,000 total

    Sent once per user (tracked via UserEmailLog).
    Runs daily at 15:00 WAT.
    """
    from app.models.models import Invoice, SubscriptionPlan, User, UserEmailLog

    stats = {"whatsapp_sent": 0, "email_sent": 0, "skipped": 0, "failed": 0}

    try:
        with session_scope() as db:
            # Find free users who have collected payments
            paid_data = (
                db.query(
                    Invoice.issuer_id,
                    sqlfunc.sum(Invoice.amount).label("total_collected"),
                    sqlfunc.count(Invoice.id).label("paid_count"),
                )
                .filter(
                    Invoice.invoice_type == "revenue",
                    Invoice.status == "paid",
                )
                .group_by(Invoice.issuer_id)
                .having(
                    (sqlfunc.count(Invoice.id) >= 2)
                    | (sqlfunc.sum(Invoice.amount) >= 50000)
                )
                .all()
            )

            if not paid_data:
                logger.info("No users qualify for payment upsell")
                return {"success": True, **stats}

            from app.core.whatsapp import get_whatsapp_client
            from app.bot.conversation_window import is_window_open

            client = get_whatsapp_client()

            for row in paid_data:
                user = db.query(User).filter(User.id == row.issuer_id).first()
                if not user:
                    continue

                # Only target free users
                if user.plan != SubscriptionPlan.FREE:
                    stats["skipped"] += 1
                    continue

                # Dedup: only send once
                already = (
                    db.query(UserEmailLog.id)
                    .filter(
                        UserEmailLog.user_id == user.id,
                        UserEmailLog.email_type == "payment_upsell",
                    )
                    .first()
                )
                if already:
                    stats["skipped"] += 1
                    continue

                total = float(row.total_collected)
                count = int(row.paid_count)
                name = (user.name or "").split()[0] or "there"

                message = (
                    f"🎉 *You've collected ₦{total:,.0f}!*\n\n"
                    f"Hi {name}, you've received {count} payment{'s' if count != 1 else ''} "
                    f"through SuoOps — your business is growing!\n\n"
                    f"Upgrade to *Pro* for ₦3,250/mo to:\n"
                    f"✅ 50 invoices/month included\n"
                    f"✅ Tax reports (PIT + CIT)\n"
                    f"✅ Daily WhatsApp business summary\n"
                    f"✅ Customer insights & alerts\n"
                    f"✅ Priority support\n\n"
                    f"🔗 suoops.com/dashboard/settings/subscription"
                )

                sent = False
                has_phone = _is_valid_phone(user.phone)

                # Try WhatsApp template first
                if has_phone:
                    template_name = getattr(settings, "WHATSAPP_TEMPLATE_PAYMENT_UPSELL", None)
                    if template_name:
                        lang = settings.WHATSAPP_TEMPLATE_LANGUAGE or "en"
                        ok = client.send_template(
                            user.phone,
                            template_name,
                            lang,
                            components=[{
                                "type": "body",
                                "parameters": [
                                    {"type": "text", "text": name},
                                    {"type": "text", "text": f"₦{total:,.0f}"},
                                ],
                            }],
                        )
                        if ok:
                            stats["whatsapp_sent"] += 1
                            sent = True

                    if not sent and is_window_open(user.phone):
                        if client.send_text(user.phone, message):
                            stats["whatsapp_sent"] += 1
                            sent = True

                # Email fallback
                if not sent and user.email:
                    subject = f"You've collected ₦{total:,.0f} — ready for Pro?"
                    plain = (
                        f"Hi {name},\n\n"
                        f"You've received {count} payment{'s' if count != 1 else ''} "
                        f"totalling ₦{total:,.0f} through SuoOps.\n\n"
                        f"Upgrade to Pro (₦3,250/mo) for tax reports, daily summaries, "
                        f"customer insights, and 50 invoices/month.\n\n"
                        f"Upgrade: https://suoops.com/dashboard/settings/subscription\n\n"
                        f"— SuoOps"
                    )
                    if _send_smtp_email(user.email, subject, None, plain):
                        stats["email_sent"] += 1
                        sent = True

                if sent:
                    db.add(UserEmailLog(user_id=user.id, email_type="payment_upsell"))
                    db.flush()
                else:
                    stats["failed"] += 1

            db.commit()

        logger.info(
            "Payment upsells: wa=%d email=%d skipped=%d failed=%d",
            stats["whatsapp_sent"], stats["email_sent"],
            stats["skipped"], stats["failed"],
        )
        return {"success": True, **stats}

    except Exception as exc:
        logger.error("Payment upsell task failed: %s", exc)
        raise
