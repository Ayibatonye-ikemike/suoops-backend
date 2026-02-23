"""
Messaging and WhatsApp Tasks.

Celery tasks for WhatsApp processing, reminders, OCR, and payment sync.
"""
from __future__ import annotations

import asyncio
import gc
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from celery import Task

from app.core.config import settings
from app.db.session import session_scope
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="whatsapp.process_inbound",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def process_whatsapp_inbound(self: Task, payload: dict[str, Any]) -> None:
    """Process inbound WhatsApp message.

    Heavy NLP / adapter imports are done lazily to keep baseline worker RSS low.
    """
    from app.bot.nlp_service import NLPService
    from app.bot.whatsapp_adapter import WhatsAppClient, WhatsAppHandler

    with session_scope() as db:
        handler = WhatsAppHandler(
            client=WhatsAppClient(settings.WHATSAPP_API_KEY),
            nlp=NLPService(),
            db=db,
        )
        asyncio.run(handler.handle_incoming(payload))

    gc.collect()


@celery_app.task(
    name="maintenance.send_overdue_reminders",
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def send_overdue_reminders() -> dict[str, Any]:
    """Send escalating reminders to BUSINESS OWNERS about their overdue invoices.

    Escalation tiers (by days overdue):
      owner_light    — 1-3 days  : gentle nudge
      owner_action   — 4-7 days  : action required
      owner_urgent   — 8-14 days : suggest calling customer
      owner_critical — 14+ days  : final warning / write-off hint

    Each tier is sent only once per invoice (tracked in InvoiceReminderLog).
    Runs daily at 09:00 WAT (08:00 UTC).
    """
    from sqlalchemy.orm import joinedload

    from app.models.models import InvoiceReminderLog, Invoice, User

    sent = 0
    skipped = 0
    failed = 0

    try:
        with session_scope() as db:
            today = date.today()
            now_dt = datetime.combine(today, datetime.min.time())

            overdue_invoices = (
                db.query(Invoice)
                .options(joinedload(Invoice.customer))
                .filter(
                    Invoice.status == "pending",
                    Invoice.invoice_type == "revenue",
                    Invoice.due_date != None,  # noqa: E711
                    Invoice.due_date < now_dt,
                )
                .all()
            )

            if not overdue_invoices:
                logger.info("No overdue invoices found")
                return {"success": True, "sent": 0, "total_overdue": 0}

            # Group by issuer
            by_issuer: dict[int, list[Invoice]] = {}
            for inv in overdue_invoices:
                by_issuer.setdefault(inv.issuer_id, []).append(inv)

            logger.info(
                "Found %d overdue invoices for %d users",
                len(overdue_invoices),
                len(by_issuer),
            )

            from app.bot.whatsapp_client import WhatsAppClient

            client = WhatsAppClient(settings.WHATSAPP_API_KEY)

            for issuer_id, invoices in by_issuer.items():
                user = db.query(User).filter(User.id == issuer_id).first()
                if not user or not user.phone:
                    continue

                # Classify invoices by escalation tier
                tiers: dict[str, list[Invoice]] = {
                    "owner_light": [],
                    "owner_action": [],
                    "owner_urgent": [],
                    "owner_critical": [],
                }
                for inv in invoices:
                    if not inv.due_date:
                        continue
                    days = (today - inv.due_date.date()).days
                    if days >= 14:
                        tier = "owner_critical"
                    elif days >= 8:
                        tier = "owner_urgent"
                    elif days >= 4:
                        tier = "owner_action"
                    else:
                        tier = "owner_light"

                    # Check if this tier was already sent for this invoice
                    already = (
                        db.query(InvoiceReminderLog)
                        .filter(
                            InvoiceReminderLog.invoice_id == inv.id,
                            InvoiceReminderLog.reminder_type == tier,
                            InvoiceReminderLog.channel == "whatsapp",
                        )
                        .first()
                    )
                    if already:
                        skipped += 1
                        continue
                    tiers[tier].append(inv)

                # Build a single consolidated message per user covering the highest tier
                message = _build_owner_escalation_message(tiers, today)
                if not message:
                    continue

                try:
                    success = client.send_text(user.phone, message)
                    if not success:
                        logger.warning(
                            "Overdue reminder delivery failed for user %s (phone=%s…)",
                            issuer_id,
                            user.phone[:6] if user.phone else "none",
                        )
                        failed += 1
                        continue

                    sent += 1

                    # Log all tiers we just notified about
                    for tier, tier_invoices in tiers.items():
                        for inv in tier_invoices:
                            db.add(
                                InvoiceReminderLog(
                                    invoice_id=inv.id,
                                    reminder_type=tier,
                                    channel="whatsapp",
                                    recipient=user.phone,
                                )
                            )
                    db.commit()
                except Exception as e:
                    logger.warning(
                        "Failed owner overdue reminder for user %s: %s", issuer_id, e
                    )
                    failed += 1

        logger.info(
            "Owner overdue reminders: sent=%d skipped=%d failed=%d",
            sent,
            skipped,
            failed,
        )
        return {
            "success": True,
            "sent": sent,
            "skipped": skipped,
            "failed": failed,
            "total_overdue": len(overdue_invoices),
        }

    except Exception as exc:
        logger.warning("Owner reminder task transient failure: %s", exc)
        raise


def _build_owner_escalation_message(
    tiers: dict[str, list[Any]], today: date
) -> str | None:
    """Build a consolidated escalation message for the business owner."""
    total = sum(len(v) for v in tiers.values())
    if total == 0:
        return None

    total_owed = sum(inv.amount for invs in tiers.values() for inv in invs)
    parts: list[str] = []

    critical = tiers["owner_critical"]
    urgent = tiers["owner_urgent"]
    action = tiers["owner_action"]
    light = tiers["owner_light"]

    if critical:
        days_list = ", ".join(
            f"{(today - inv.due_date.date()).days}d" for inv in critical[:3]
        )
        parts.append(
            f"🔴 *CRITICAL* — {len(critical)} invoice(s) 14+ days overdue ({days_list}).\n"
            "Consider calling these customers directly or reviewing your collection strategy."
        )

    if urgent:
        parts.append(
            f"🟠 *URGENT* — {len(urgent)} invoice(s) 8-14 days overdue.\n"
            "💡 Try calling your customers — a quick follow-up call recovers 70% of late payments."
        )

    if action:
        parts.append(
            f"🟡 *Action Required* — {len(action)} invoice(s) 4-7 days overdue.\n"
            "💡 Send a polite reminder from your dashboard to nudge them."
        )

    if light:
        parts.append(
            f"🟢 *Heads Up* — {len(light)} invoice(s) 1-3 days overdue.\n"
            "These are still fresh — customers may just need a gentle nudge."
        )

    header = (
        f"⚠️ *Overdue Invoice Report*\n"
        f"You have {total} overdue invoice(s) totalling ₦{total_owed:,.0f}.\n\n"
    )
    footer = "\n\n🔗 Review all invoices at suoops.com/dashboard"

    return header + "\n\n".join(parts) + footer


# ── Customer-Facing Payment Reminders ────────────────────────────────


@celery_app.task(
    name="reminders.send_customer_payment_reminders",
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def send_customer_payment_reminders() -> dict[str, Any]:
    """Send payment reminders directly to CUSTOMERS via WhatsApp and email.

    Reminder tiers (relative to due_date):
      customer_pre_due    — 3 days before due : gentle heads-up
      customer_due_today  — on the due date   : due today notice
      customer_overdue_1d — 1 day past due    : first nudge
      customer_overdue_7d — 7 days past due   : firmer follow-up
      customer_overdue_14d— 14+ days past due : final escalation (CC's owner)

    Each tier is sent only once per invoice per channel (tracked in
    InvoiceReminderLog).  Runs daily at 10:00 WAT (09:00 UTC).
    """
    from sqlalchemy.orm import joinedload

    from app.models.models import InvoiceReminderLog, Invoice, User

    stats = {"whatsapp_sent": 0, "email_sent": 0, "skipped": 0, "failed": 0}

    try:
        with session_scope() as db:
            today = date.today()
            now_dt = datetime.combine(today, datetime.min.time())

            # Window: 3 days before today → any overdue
            window_start = now_dt + timedelta(days=3)

            candidates = (
                db.query(Invoice)
                .options(
                    joinedload(Invoice.customer),
                    joinedload(Invoice.issuer),
                )
                .filter(
                    Invoice.status == "pending",
                    Invoice.invoice_type == "revenue",
                    Invoice.due_date != None,  # noqa: E711
                    Invoice.due_date <= window_start,
                )
                .all()
            )

            if not candidates:
                logger.info("No invoices due or overdue for customer reminders")
                return {"success": True, **stats}

            logger.info(
                "Customer reminders: %d candidate invoices", len(candidates)
            )

            for inv in candidates:
                customer = inv.customer
                issuer = inv.issuer
                if not customer or not issuer:
                    continue

                # Determine which tier this invoice falls into
                days_until_due = (inv.due_date.date() - today).days
                tier = _classify_customer_tier(days_until_due)
                if not tier:
                    continue

                customer_phone = customer.phone
                customer_email = customer.email
                business_name = issuer.business_name or issuer.name

                # --- WhatsApp ---
                if customer_phone:
                    already = (
                        db.query(InvoiceReminderLog)
                        .filter(
                            InvoiceReminderLog.invoice_id == inv.id,
                            InvoiceReminderLog.reminder_type == tier,
                            InvoiceReminderLog.channel == "whatsapp",
                        )
                        .first()
                    )
                    if already:
                        stats["skipped"] += 1
                    else:
                        ok = _send_customer_whatsapp_reminder(
                            inv, customer, issuer, tier, business_name
                        )
                        if ok:
                            db.add(
                                InvoiceReminderLog(
                                    invoice_id=inv.id,
                                    reminder_type=tier,
                                    channel="whatsapp",
                                    recipient=customer_phone,
                                )
                            )
                            stats["whatsapp_sent"] += 1
                        else:
                            stats["failed"] += 1

                # --- Email ---
                if customer_email:
                    already = (
                        db.query(InvoiceReminderLog)
                        .filter(
                            InvoiceReminderLog.invoice_id == inv.id,
                            InvoiceReminderLog.reminder_type == tier,
                            InvoiceReminderLog.channel == "email",
                        )
                        .first()
                    )
                    if already:
                        stats["skipped"] += 1
                    else:
                        ok = _send_customer_email_reminder(
                            inv, customer, issuer, tier, business_name
                        )
                        if ok:
                            db.add(
                                InvoiceReminderLog(
                                    invoice_id=inv.id,
                                    reminder_type=tier,
                                    channel="email",
                                    recipient=customer_email,
                                )
                            )
                            stats["email_sent"] += 1
                        else:
                            stats["failed"] += 1

                # For 14d+ overdue, also ping the owner about this specific invoice
                if tier == "customer_overdue_14d" and issuer.phone:
                    _notify_owner_escalation(inv, issuer, customer, business_name)

            db.commit()

        logger.info("Customer payment reminders: %s", stats)
        return {"success": True, **stats}

    except Exception as exc:
        logger.warning("Customer reminder task transient failure: %s", exc)
        raise


def _classify_customer_tier(days_until_due: int) -> str | None:
    """Map days-until-due to customer reminder tier.

    Returns None if the invoice doesn't match any tier window.
    """
    if days_until_due == 3:
        return "customer_pre_due"
    elif days_until_due == 0:
        return "customer_due_today"
    elif days_until_due == -1:
        return "customer_overdue_1d"
    elif days_until_due == -7:
        return "customer_overdue_7d"
    elif days_until_due <= -14:
        # Only trigger once at -14 (the log prevents re-sends)
        return "customer_overdue_14d"
    return None


def _send_customer_whatsapp_reminder(
    inv: Any,
    customer: Any,
    issuer: Any,
    tier: str,
    business_name: str,
) -> bool:
    """Send a WhatsApp payment reminder to a customer.

    Prefers the ``payment_reminder`` template (deliverable outside the 24-hour
    window) and falls back to free-form text when the template is not configured.
    """
    try:
        from app.bot.whatsapp_client import WhatsAppClient

        client = WhatsAppClient(settings.WHATSAPP_API_KEY)

        # Prefer template (works outside 24h window)
        template_name = settings.WHATSAPP_TEMPLATE_PAYMENT_REMINDER
        if template_name:
            customer_name = customer.name or "Customer"
            amount_str = f"₦{inv.amount:,.0f}"
            payment_link = f"{settings.FRONTEND_URL}/pay/{inv.invoice_id}"

            days_until_due = (inv.due_date.date() - date.today()).days
            if days_until_due > 0:
                days_info = f"due in {days_until_due} day(s)"
            elif days_until_due == 0:
                days_info = "due today"
            else:
                days_info = f"{abs(days_until_due)} day(s) overdue"

            bank_name = issuer.bank_name or "N/A"
            account_number = issuer.account_number or "N/A"

            components = [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": customer_name},
                        {"type": "text", "text": inv.invoice_id},
                        {"type": "text", "text": amount_str},
                        {"type": "text", "text": days_info},
                        {"type": "text", "text": bank_name},
                        {"type": "text", "text": account_number},
                        {"type": "text", "text": payment_link},
                    ],
                }
            ]
            lang = settings.WHATSAPP_TEMPLATE_LANGUAGE or "en"
            return client.send_template(customer.phone, template_name, lang, components)

        # Fallback: free-form text (only works within 24h window)
        message = _format_customer_reminder(inv, tier, business_name)
        return client.send_text(customer.phone, message)
    except Exception as e:
        logger.warning(
            "WhatsApp reminder failed for invoice %s to %s: %s",
            inv.invoice_id,
            customer.phone,
            e,
        )
        return False


def _send_customer_email_reminder(
    inv: Any,
    customer: Any,
    issuer: Any,
    tier: str,
    business_name: str,
) -> bool:
    """Send an email payment reminder to a customer."""
    try:
        from app.services.notification.service import NotificationService

        svc = NotificationService()
        subject = _email_subject_for_tier(inv, tier, business_name)
        body = _format_customer_reminder(inv, tier, business_name)
        return asyncio.run(svc.send_email(customer.email, subject, body))
    except Exception as e:
        logger.warning(
            "Email reminder failed for invoice %s to %s: %s",
            inv.invoice_id,
            customer.email,
            e,
        )
        return False


def _notify_owner_escalation(
    inv: Any, issuer: Any, customer: Any, business_name: str
) -> None:
    """Alert the business owner about a severely overdue invoice."""
    try:
        from app.bot.whatsapp_client import WhatsAppClient

        client = WhatsAppClient(settings.WHATSAPP_API_KEY)
        customer_name = customer.name or "a customer"
        msg = (
            f"🔴 *Escalation Alert*\n\n"
            f"Invoice {inv.invoice_id} for {customer_name} "
            f"(₦{inv.amount:,.0f}) is now 14+ days overdue.\n\n"
            "We've sent a final reminder to the customer. "
            "Consider calling them directly or reviewing your collection options.\n\n"
            "🔗 suoops.com/dashboard"
        )
        client.send_text(issuer.phone, msg)
    except Exception as e:
        logger.warning(
            "Owner escalation alert failed for invoice %s: %s", inv.invoice_id, e
        )


def _format_customer_reminder(inv: Any, tier: str, business_name: str) -> str:
    """Format a customer-facing payment reminder message."""
    payment_link = f"{settings.BASE_URL}/pay/{inv.invoice_id}"
    amount_str = f"₦{inv.amount:,.0f}"
    due_str = inv.due_date.strftime("%d %b %Y") if inv.due_date else "N/A"

    if tier == "customer_pre_due":
        return (
            f"👋 Hi{_name_greeting(inv.customer)},\n\n"
            f"Friendly reminder: your invoice {inv.invoice_id} for {amount_str} "
            f"from *{business_name}* is due on *{due_str}* (in 3 days).\n\n"
            f"💳 Pay now: {payment_link}\n\n"
            "Thank you for your prompt attention!"
        )
    elif tier == "customer_due_today":
        return (
            f"⏰ Hi{_name_greeting(inv.customer)},\n\n"
            f"Your invoice {inv.invoice_id} for {amount_str} "
            f"from *{business_name}* is *due today*.\n\n"
            f"💳 Pay now: {payment_link}\n\n"
            "Please make your payment to avoid it becoming overdue."
        )
    elif tier == "customer_overdue_1d":
        return (
            f"📌 Hi{_name_greeting(inv.customer)},\n\n"
            f"Your invoice {inv.invoice_id} for {amount_str} "
            f"from *{business_name}* was due yesterday and is now overdue.\n\n"
            f"💳 Pay now: {payment_link}\n\n"
            "If you've already paid, please disregard this message."
        )
    elif tier == "customer_overdue_7d":
        return (
            f"⚠️ Hi{_name_greeting(inv.customer)},\n\n"
            f"This is a follow-up regarding invoice {inv.invoice_id} for "
            f"{amount_str} from *{business_name}*, which is now 7 days overdue.\n\n"
            f"💳 Pay now: {payment_link}\n\n"
            "Please settle this at your earliest convenience. "
            "If you're experiencing any issues with payment, please reach out to "
            f"{business_name} directly."
        )
    else:  # customer_overdue_14d
        return (
            f"🔴 Hi{_name_greeting(inv.customer)},\n\n"
            f"*Final reminder:* Invoice {inv.invoice_id} for {amount_str} "
            f"from *{business_name}* is now over 14 days past due.\n\n"
            f"💳 Pay now: {payment_link}\n\n"
            "Please arrange payment immediately. If you have questions or "
            f"need to discuss payment terms, please contact {business_name} directly."
        )


def _email_subject_for_tier(inv: Any, tier: str, business_name: str) -> str:
    """Return an email subject line appropriate for the reminder tier."""
    ref = inv.invoice_id
    if tier == "customer_pre_due":
        return f"Reminder: Invoice {ref} from {business_name} due in 3 days"
    elif tier == "customer_due_today":
        return f"Invoice {ref} from {business_name} is due today"
    elif tier == "customer_overdue_1d":
        return f"Overdue: Invoice {ref} from {business_name}"
    elif tier == "customer_overdue_7d":
        return f"Follow-up: Invoice {ref} from {business_name} — 7 days overdue"
    else:
        return f"Final Notice: Invoice {ref} from {business_name} — 14+ days overdue"


def _name_greeting(customer: Any) -> str:
    """Return ' Name' if customer has a name, else empty string."""
    name = getattr(customer, "name", None)
    if name and name.strip():
        return f" {name.split()[0]}"
    return ""


@celery_app.task(
    bind=True,
    name="payments.sync_provider_status",
    autoretry_for=(Exception,),
    retry_backoff=10,
    retry_jitter=True,
    retry_kwargs={"max_retries": 4},
)
def sync_provider_status(self: Task, provider: str, reference: str) -> dict[str, Any]:
    """Sync payment provider status with retries on transient errors.

    Calls Paystack verify endpoint and updates the local invoice status
    to match what the payment provider reports.
    """
    import requests as http_requests

    from app.models.models import Invoice

    logger.info("Syncing provider status | provider=%s reference=%s", provider, reference)

    if provider != "paystack":
        logger.warning("Unsupported provider: %s", provider)
        return {"success": False, "error": f"Unsupported provider: {provider}"}

    paystack_key = settings.PAYSTACK_SECRET_KEY
    if not paystack_key:
        logger.error("PAYSTACK_SECRET_KEY not configured, cannot verify")
        return {"success": False, "error": "Paystack key not configured"}

    try:
        resp = http_requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {paystack_key}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("Paystack verify call failed for %s: %s", reference, e)
        raise  # triggers Celery retry

    tx_data = data.get("data", {})
    tx_status = tx_data.get("status", "unknown")  # success / failed / abandoned
    logger.info(
        "Paystack status for %s: %s (gateway_response=%s)",
        reference,
        tx_status,
        tx_data.get("gateway_response"),
    )

    # Map Paystack status to local invoice status
    status_map = {
        "success": "paid",
        "failed": "failed",
        "abandoned": "pending",
        "reversed": "failed",
    }
    new_status = status_map.get(tx_status)
    if not new_status:
        logger.warning("Unknown Paystack status '%s' for reference %s", tx_status, reference)
        return {"success": False, "error": f"Unknown provider status: {tx_status}"}

    with session_scope() as db:
        invoice = (
            db.query(Invoice)
            .filter(Invoice.invoice_id == reference)
            .first()
        )
        if not invoice:
            logger.warning("No invoice found for reference %s", reference)
            return {"success": False, "error": "Invoice not found"}

        old_status = invoice.status
        if old_status == new_status:
            logger.info("Invoice %s already %s, no update needed", invoice.invoice_id, new_status)
            return {"success": True, "status": new_status, "changed": False}

        invoice.status = new_status
        if new_status == "paid":
            invoice.status_updated_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            "Invoice %s status synced: %s → %s (ref=%s)",
            invoice.invoice_id,
            old_status,
            new_status,
            reference,
        )

    return {"success": True, "status": new_status, "changed": True, "old_status": old_status}


@celery_app.task(
    bind=True,
    name="ocr.parse_image",
    autoretry_for=(Exception,),
    retry_backoff=15,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def ocr_parse_image(
    self: Task, image_bytes_b64: str, context: str | None = None
) -> dict[str, Any]:
    """Run OCR parse with retries (handles rate limits/timeouts)."""
    import base64

    from app.services.ocr_service import OCRService

    raw = base64.b64decode(image_bytes_b64)
    service = OCRService()
    result = asyncio.run(service.parse_receipt(raw, context))

    if not result.get("success"):
        if "timeout" in str(result.get("error", "")).lower():
            raise Exception(result["error"])

    return result


# ── Daily Business Summary ───────────────────────────────────────────


@celery_app.task(
    name="summary.send_daily_summaries",
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_kwargs={"max_retries": 2},
)
def send_daily_summaries() -> dict[str, Any]:
    """Send daily business summary to all active users via WhatsApp.

    Runs every evening (18:00 UTC / 19:00 WAT).  Skips users with zero
    activity for the day so it never feels like spam.
    """
    from sqlalchemy import func as sqlfunc
    from sqlalchemy.orm import joinedload

    from app.models.models import Invoice, SubscriptionPlan, User

    sent = 0
    failed = 0

    try:
        with session_scope() as db:
            today = date.today()
            start_of_day = datetime.combine(today, datetime.min.time())

            # Debug: count PRO / pro_override users first
            pro_count = (
                db.query(sqlfunc.count(User.id))
                .filter(
                    (User.plan == SubscriptionPlan.PRO) | (User.pro_override.is_(True)),
                )
                .scalar()
            )
            with_phone = (
                db.query(sqlfunc.count(User.id))
                .filter(
                    User.phone != None,  # noqa: E711
                    (User.plan == SubscriptionPlan.PRO) | (User.pro_override.is_(True)),
                )
                .scalar()
            )
            logger.info(
                "Daily summary debug: pro/override_users=%d with_phone=%d",
                pro_count, with_phone,
            )

            # Get users who have at least one invoice and a phone number
            # PRO users and users with admin-granted pro_override get daily summaries
            active_users = (
                db.query(User)
                .filter(
                    User.phone != None,  # noqa: E711
                    (User.plan == SubscriptionPlan.PRO) | (User.pro_override.is_(True)),
                )
                .outerjoin(Invoice, Invoice.issuer_id == User.id)
                .group_by(User.id)
                .all()
            )
            logger.info("Daily summary: %d users after join", len(active_users))

            from app.bot.whatsapp_client import WhatsAppClient

            client = WhatsAppClient(settings.WHATSAPP_API_KEY)
            summary_template = getattr(settings, "WHATSAPP_TEMPLATE_DAILY_SUMMARY", None)
            template_lang = getattr(settings, "WHATSAPP_TEMPLATE_LANGUAGE", "en")

            for user in active_users:
                try:
                    # Revenue collected today
                    revenue_today = (
                        db.query(sqlfunc.coalesce(sqlfunc.sum(Invoice.amount), 0))
                        .filter(
                            Invoice.issuer_id == user.id,
                            Invoice.invoice_type == "revenue",
                            Invoice.status == "paid",
                            Invoice.paid_at >= start_of_day,
                        )
                        .scalar()
                    )

                    # Expenses recorded today
                    expenses_today = (
                        db.query(sqlfunc.coalesce(sqlfunc.sum(Invoice.amount), 0))
                        .filter(
                            Invoice.issuer_id == user.id,
                            Invoice.invoice_type == "expense",
                            Invoice.created_at >= start_of_day,
                        )
                        .scalar()
                    )

                    # Total outstanding
                    outstanding = (
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
                            Invoice.due_date < start_of_day,
                        )
                        .scalar()
                    ) or 0

                    # PRO users always get a daily summary, even on quiet days

                    message = _format_daily_summary(
                        revenue_today, expenses_today, outstanding, overdue_count
                    )

                    # Try template first (works outside WhatsApp 24h window),
                    # fall back to plain text if no template configured.
                    success = False
                    if summary_template:
                        success = client.send_template(
                            user.phone,
                            summary_template,
                            template_lang,
                            components=[{
                                "type": "body",
                                "parameters": [{"type": "text", "text": message}],
                            }],
                        )
                        if not success:
                            logger.warning(
                                "Template delivery failed for user %s, trying plain text",
                                user.id,
                            )

                    if not success:
                        success = client.send_text(user.phone, message)

                    if success:
                        sent += 1
                    else:
                        failed += 1
                        logger.warning(
                            "Daily summary delivery failed for user %s (phone=%s…)",
                            user.id,
                            user.phone[:6] if user.phone else "none",
                        )

                except Exception as e:
                    logger.warning("Failed daily summary for user %s: %s", user.id, e)
                    failed += 1

        logger.info("Daily summaries: sent=%d failed=%d", sent, failed)
        return {"success": True, "sent": sent, "failed": failed}

    except Exception as exc:
        logger.error("Daily summary task failed: %s", exc)
        raise


def _format_daily_summary(
    revenue: Any, expenses: Any, outstanding: Any, overdue_count: int
) -> str:
    """Format the daily WhatsApp summary message."""
    rev = float(revenue)
    exp = float(expenses)
    net = rev - exp
    out = float(outstanding)

    msg = "📊 *Today's Business Summary*\n\n"

    if rev == 0 and exp == 0 and out == 0 and overdue_count == 0:
        msg += "✨ All clear today — no new transactions or outstanding invoices.\n"
        msg += "💡 Create an invoice to start tracking your cash flow!\n"
    else:
        if rev > 0:
            msg += f"💰 Cash In: ₦{rev:,.0f}\n"
        if exp > 0:
            msg += f"💸 Expenses: ₦{exp:,.0f}\n"
        if rev > 0 or exp > 0:
            emoji = "📈" if net >= 0 else "📉"
            msg += f"{emoji} Net: ₦{net:,.0f}\n"

        msg += "\n"

        if out > 0:
            msg += f"⏳ Outstanding: ₦{out:,.0f}\n"
        if overdue_count > 0:
            s = "s" if overdue_count != 1 else ""
            msg += (
                f"⚠️ Overdue: {overdue_count} invoice{s}\n"
                "💡 Send reminders from your dashboard to collect faster!\n"
            )

    msg += "\n🔗 suoops.com/dashboard"
    return msg
