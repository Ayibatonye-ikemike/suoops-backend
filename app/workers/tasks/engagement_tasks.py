"""
User Engagement Email Tasks.

Celery tasks for lifecycle email notifications:
- Activation: Push new users to create their first invoice (Day 0, 1, 3)
- Monetization: Nudge toward Starter plan after value is felt (3+ invoices, 80% limit, limit hit)
- Education: Tips every 2 days for active users
"""
from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func

from app.core.config import settings
from app.db.session import session_scope
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Jinja2 template setup
_template_dir = Path(__file__).parent.parent.parent.parent / "templates" / "email"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_template_dir)),
    autoescape=select_autoescape(["html", "xml"]),
)

# ── Email type constants ─────────────────────────────────────────────
# Activation sequence (one-time sends)
EMAIL_WELCOME_FIRST_INVOICE = "activation_day0"
EMAIL_SEND_ONE_INVOICE = "activation_day1"
EMAIL_DAILY_HABIT = "activation_day3"

# Monetization (one-time sends based on behavior)
EMAIL_3_INVOICES_SENT = "monetization_3_invoices"
EMAIL_80PCT_LIMIT = "monetization_80pct_limit"
EMAIL_LIMIT_REACHED = "monetization_limit_reached"

# Education tips (rotating, tracked by index)
EMAIL_TIP_PREFIX = "tip_"

# Tips pool — rotated every 2 days
TIPS = [
    {
        "subject": "Get paid faster with payment verification",
        "headline": "Tip: Get Paid Faster",
        "body": "When a customer says they've paid, verify it instantly on SuoOps. "
                "Mark invoices as paid and your records stay accurate — no more guessing.",
        "tip": "Go to any pending invoice → Mark as Paid. Your cash position updates automatically.",
        "cta_url": "https://suoops.com/dashboard",
        "cta_label": "Check Your Invoices →",
    },
    {
        "subject": "Your professionalism score matters",
        "headline": "Tip: Look Professional",
        "body": "Businesses that add their logo and bank details to invoices get paid 40% faster. "
                "Your professionalism score shows how complete your setup is.",
        "tip": "Upload your logo in Settings → Business Profile to boost your score.",
        "cta_url": "https://suoops.com/dashboard/settings",
        "cta_label": "Update Your Profile →",
    },
    {
        "subject": "Send invoices via WhatsApp — it's faster",
        "headline": "Tip: WhatsApp Delivery",
        "body": "You can create and send invoices right from WhatsApp. "
                "Just message your SuoOps number with the customer name, item, and amount.",
        "tip": "Try it: Send \"Invoice Amina ₦5000 for consulting\" to your SuoOps WhatsApp.",
        "cta_url": None,
        "cta_label": None,
    },
    {
        "subject": "Track your expenses alongside revenue",
        "headline": "Tip: Track Expenses Too",
        "body": "SuoOps isn't just for invoices. Record your business expenses so you can see "
                "your true profit — not just revenue.",
        "tip": "Go to Dashboard → Expenses → Add Expense to start tracking.",
        "cta_url": "https://suoops.com/dashboard/expenses",
        "cta_label": "Add an Expense →",
    },
    {
        "subject": "Beware of fake payment alerts",
        "headline": "Tip: Spot Fake Alerts",
        "body": "Fake bank alerts are everywhere. Always verify payments through your actual bank app "
                "before releasing goods. SuoOps helps you track what's truly paid vs. pending.",
        "tip": "Never rely on screenshots alone. Check your bank, then mark it paid on SuoOps.",
        "cta_url": "https://suoops.com/dashboard",
        "cta_label": "Review Pending Invoices →",
    },
]


def _send_smtp_email(to_email: str, subject: str, html_body: str, plain_body: str) -> bool:
    """Send an email via Brevo SMTP. Returns True on success."""
    smtp_host = getattr(settings, "SMTP_HOST", None) or "smtp-relay.brevo.com"
    smtp_port = getattr(settings, "SMTP_PORT", 587)
    smtp_user = getattr(settings, "SMTP_USER", None) or getattr(settings, "BREVO_SMTP_LOGIN", None)
    smtp_password = getattr(settings, "SMTP_PASSWORD", None) or getattr(settings, "BREVO_API_KEY", None)
    from_email = getattr(settings, "FROM_EMAIL", None) or "noreply@suoops.com"

    if not smtp_user or not smtp_password:
        logger.warning("SMTP not configured, skipping email to %s", to_email)
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return True
    except Exception as e:
        logger.warning("SMTP send failed to %s: %s", to_email, e)
        return False


def _was_sent(db, user_id: int, email_type: str) -> bool:
    """Check if this email type was already sent to this user."""
    from app.models.models import UserEmailLog

    return (
        db.query(UserEmailLog.id)
        .filter(UserEmailLog.user_id == user_id, UserEmailLog.email_type == email_type)
        .first()
        is not None
    )


def _record_sent(db, user_id: int, email_type: str) -> None:
    """Record that this email type was sent to this user."""
    from app.models.models import UserEmailLog

    db.add(UserEmailLog(user_id=user_id, email_type=email_type))
    db.flush()


def _get_user_name(user) -> str:
    """Get a display name from user, falling back to 'there'."""
    return user.name.split()[0] if user.name else "there"


# ── Main scheduled task ──────────────────────────────────────────────

@celery_app.task(
    name="engagement.send_lifecycle_emails",
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_kwargs={"max_retries": 2},
    soft_time_limit=300,
    time_limit=360,
)
def send_engagement_emails() -> dict[str, Any]:
    """Send lifecycle engagement emails to users based on their behavior.

    Runs daily at 09:00 UTC (10:00 WAT).

    Segments:
    1. Activation — new users who haven't created an invoice yet (Day 0/1/3)
    2. Monetization — active users approaching or at invoice limits
    3. Tips — every-2-days education for active FREE-tier users
    """
    from app.models.models import Invoice, User, UserEmailLog

    now = datetime.now(timezone.utc)
    stats: dict[str, int] = {
        "activation_sent": 0,
        "monetization_sent": 0,
        "tips_sent": 0,
        "skipped": 0,
        "failed": 0,
    }

    try:
        with session_scope() as db:
            all_users = (
                db.query(User)
                .filter(
                    User.email != None,  # noqa: E711 – need email to send
                    User.is_active.is_(True),
                )
                .all()
            )

            for user in all_users:
                try:
                    _process_user(db, user, now, stats)
                except Exception as e:
                    logger.warning("Engagement email failed for user %s: %s", user.id, e)
                    stats["failed"] += 1

            db.commit()

        logger.info(
            "Engagement emails complete: activation=%d monetization=%d tips=%d skipped=%d failed=%d",
            stats["activation_sent"],
            stats["monetization_sent"],
            stats["tips_sent"],
            stats["skipped"],
            stats["failed"],
        )
        return {"success": True, **stats}

    except Exception as exc:
        logger.error("Engagement email task failed: %s", exc)
        raise


def _process_user(db, user, now: datetime, stats: dict[str, int]) -> None:
    """Determine which email (if any) to send to a single user."""
    from app.models.models import Invoice

    name = _get_user_name(user)
    signup_age = now - user.created_at.replace(tzinfo=timezone.utc) if user.created_at.tzinfo is None else now - user.created_at

    # Count user's total invoices
    invoice_count = (
        db.query(func.count(Invoice.id))
        .filter(Invoice.issuer_id == user.id, Invoice.invoice_type == "revenue")
        .scalar()
    ) or 0

    # ── 1. ACTIVATION (users with 0 invoices, first 3 days) ──────────
    if invoice_count == 0 and signup_age.days <= 3:
        _send_activation(db, user, name, signup_age.days, stats)
        return

    # ── 2. MONETIZATION (FREE users with invoices) ───────────────────
    if user.plan.value == "free" and invoice_count > 0:
        if _send_monetization(db, user, name, invoice_count, stats):
            return

    # ── 3. EDUCATION TIPS (active FREE users, every 2 days) ──────────
    if invoice_count > 0 and user.plan.value == "free":
        _send_tip(db, user, name, stats)
        return

    stats["skipped"] += 1


def _send_activation(db, user, name: str, days_since_signup: int, stats: dict[str, int]) -> None:
    """Send activation email based on days since signup."""
    email_map = {
        0: (
            EMAIL_WELCOME_FIRST_INVOICE,
            "Welcome to SuoOps — Create Your First Invoice",
            "Create Your First Invoice",
            "You just signed up for SuoOps — great move! The best way to get started is simple: "
            "create your first invoice right now. It takes less than a minute.",
        ),
        1: (
            EMAIL_SEND_ONE_INVOICE,
            "Send 1 invoice today",
            "Send 1 Invoice Today",
            "Just one invoice. That's all it takes to see how SuoOps keeps your business organized. "
            "Enter a customer name, amount, and hit send.",
        ),
        3: (
            EMAIL_DAILY_HABIT,
            "Most businesses use SuoOps daily",
            "Make Invoicing a Habit",
            "The businesses that grow fastest are the ones that track every naira. "
            "SuoOps makes it easy — create invoices, track payments, and stay on top of your cash flow.",
        ),
    }

    entry = email_map.get(days_since_signup)
    if not entry:
        stats["skipped"] += 1
        return

    email_type, subject, headline, body_text = entry

    if _was_sent(db, user.id, email_type):
        stats["skipped"] += 1
        return

    template = _jinja_env.get_template("engagement_first_invoice.html")
    html = template.render(name=name, headline=headline, body_text=body_text)
    plain = f"Hi {name},\n\n{body_text}\n\nCreate your first invoice: https://suoops.com/dashboard/invoices/new\n\n— SuoOps"

    if _send_smtp_email(user.email, subject, html, plain):
        _record_sent(db, user.id, email_type)
        stats["activation_sent"] += 1
        logger.info("Sent activation email '%s' to user %s", email_type, user.id)
    else:
        stats["failed"] += 1


def _send_monetization(db, user, name: str, invoice_count: int, stats: dict[str, int]) -> bool:
    """Send monetization email if user hits a threshold. Returns True if sent."""
    invoice_balance = getattr(user, "invoice_balance", 5)

    # At limit reached (0 invoices remaining)
    if invoice_balance <= 0 and not _was_sent(db, user.id, EMAIL_LIMIT_REACHED):
        subject = "You've used all your free invoices"
        headline = "Invoice Limit Reached"
        body = (
            f"You've sent {invoice_count} invoices — that's great progress! "
            "You've used all your available invoices. To keep sending, "
            "grab a Starter pack — 50 more invoices for just ₦1,250."
        )
        tip = "Go to Settings → Subscription to get more invoices instantly."
        cta_url = "https://suoops.com/dashboard/settings/subscription"
        cta_label = "Get More Invoices →"
        email_type = EMAIL_LIMIT_REACHED

    # At 80% of initial free balance (1 invoice remaining out of 5)
    elif invoice_balance == 1 and not _was_sent(db, user.id, EMAIL_80PCT_LIMIT):
        subject = "You have 1 invoice left"
        headline = "Almost Out of Invoices"
        body = (
            f"You've sent {invoice_count} invoices so far — you're clearly getting value from SuoOps. "
            "You have just 1 invoice left on your free plan. "
            "The Starter pack gives you 50 more for ₦1,250."
        )
        tip = "Upgrade before you run out so there's no interruption."
        cta_url = "https://suoops.com/dashboard/settings/subscription"
        cta_label = "Upgrade to Starter →"
        email_type = EMAIL_80PCT_LIMIT

    # After 3 invoices sent (soft mention)
    elif invoice_count >= 3 and not _was_sent(db, user.id, EMAIL_3_INVOICES_SENT):
        subject = "You've sent 3 invoices — keep going!"
        headline = "You're on a Roll 🎉"
        body = (
            f"You've already sent {invoice_count} invoices through SuoOps. "
            "You're building a real record of your business transactions. "
            "When you're ready for more, the Starter plan gives you 50 invoices and extra features."
        )
        tip = None
        cta_url = "https://suoops.com/dashboard"
        cta_label = "Back to Dashboard →"
        email_type = EMAIL_3_INVOICES_SENT

    else:
        return False

    template = _jinja_env.get_template("engagement_tip.html")
    html = template.render(
        name=name, headline=headline, body_text=body,
        tip_text=tip, cta_url=cta_url, cta_label=cta_label,
    )
    plain = f"Hi {name},\n\n{body}\n\n{'💡 ' + tip if tip else ''}\n\n{cta_url}\n\n— SuoOps"

    if _send_smtp_email(user.email, subject, html, plain):
        _record_sent(db, user.id, email_type)
        stats["monetization_sent"] += 1
        logger.info("Sent monetization email '%s' to user %s", email_type, user.id)
    else:
        stats["failed"] += 1
    return True


def _send_tip(db, user, name: str, stats: dict[str, int]) -> None:
    """Send next unsent tip to a user (max one every 2 days)."""
    from app.models.models import UserEmailLog

    # Check when the last tip was sent
    last_tip = (
        db.query(UserEmailLog.sent_at)
        .filter(
            UserEmailLog.user_id == user.id,
            UserEmailLog.email_type.like(f"{EMAIL_TIP_PREFIX}%"),
        )
        .order_by(UserEmailLog.sent_at.desc())
        .first()
    )

    if last_tip:
        last_sent = last_tip[0]
        if last_sent.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - last_sent).days < 2:
            stats["skipped"] += 1
            return

    # Find next unsent tip
    for i, tip in enumerate(TIPS):
        tip_type = f"{EMAIL_TIP_PREFIX}{i}"
        if not _was_sent(db, user.id, tip_type):
            template = _jinja_env.get_template("engagement_tip.html")
            html = template.render(
                name=name,
                headline=tip["headline"],
                body_text=tip["body"],
                tip_text=tip["tip"],
                cta_url=tip.get("cta_url"),
                cta_label=tip.get("cta_label"),
            )
            plain = f"Hi {name},\n\n{tip['body']}\n\n💡 {tip['tip']}\n\n— SuoOps"

            if _send_smtp_email(user.email, tip["subject"], html, plain):
                _record_sent(db, user.id, tip_type)
                stats["tips_sent"] += 1
                logger.info("Sent tip_%d to user %s", i, user.id)
            else:
                stats["failed"] += 1
            return

    # All tips sent — nothing more to do
    stats["skipped"] += 1
