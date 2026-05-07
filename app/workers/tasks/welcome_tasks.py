"""
Instant Welcome Message Task.

Fires immediately when a new user completes signup.
Sends a short, warm welcome via:
  - Email (all users)
  - WhatsApp (phone-verified users, using welcome_activation template)

This is distinct from the Day 0/1/3 activation sequence which runs
on the daily Beat schedule. The instant welcome arrives within seconds
of signup — no waiting until the next morning.
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

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


@celery_app.task(
    name="welcome.send_instant_welcome",
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_kwargs={"max_retries": 3},
    soft_time_limit=60,
    time_limit=90,
)
def send_instant_welcome(user_id: int) -> dict:
    """Send an instant welcome message right after signup.

    Called asynchronously from ``AuthService.complete_signup()``
    so the API response is not blocked.

    Args:
        user_id: The newly created user's ID.

    Returns:
        dict with keys: email_sent, whatsapp_sent
    """
    from app.models.models import User, UserEmailLog

    result = {"email_sent": False, "whatsapp_sent": False}

    with session_scope() as db:
        user = db.query(User).filter(User.id == user_id).one_or_none()
        if not user:
            logger.warning("Instant welcome: user %s not found", user_id)
            return result

        name = user.name.split()[0] if user.name else "there"

        # ── Get or create the user's referral code so we can include it in
        #    both the welcome email and a follow-up WhatsApp message. We do
        #    this BEFORE sending so users have their share link from day zero.
        referral_code: str | None = None
        referral_link: str | None = None
        referral_share_url: str | None = None
        try:
            from app.services.referral_service import ReferralService
            from app.services.referral_share import (
                build_referral_link,
                build_whatsapp_share_url,
            )

            code_obj = ReferralService(db).get_or_create_referral_code(user_id)
            referral_code = code_obj.code
            referral_link = build_referral_link(referral_code)
            referral_share_url = build_whatsapp_share_url(name, referral_code)
        except Exception as e:
            logger.warning("Could not provision referral code for user %s: %s", user_id, e)

        # ── De-dup: don't re-send if task retries after success ──────
        already = (
            db.query(UserEmailLog.id)
            .filter(
                UserEmailLog.user_id == user_id,
                UserEmailLog.email_type == "instant_welcome",
            )
            .first()
        )
        if already:
            logger.info("Instant welcome already sent to user %s", user_id)
            return result

        # ── 1. Email ─────────────────────────────────────────────────
        if user.email:
            try:
                template = _jinja_env.get_template("instant_welcome.html")
                html = template.render(
                    name=name,
                    dashboard_url="https://suoops.com/dashboard",
                    whatsapp_number="+234 818 376 3636",
                    referral_code=referral_code,
                    referral_link=referral_link,
                    referral_share_url=referral_share_url,
                )
                plain = (
                    f"Hi {name}! 🎉\n\n"
                    "Welcome to SuoOps — you're all set!\n\n"
                    "You can now:\n"
                    "📄 Create and send invoices in under 60 seconds\n"
                    "💬 Or just message us on WhatsApp: +234 818 376 3636\n\n"
                    "Your first 2 invoices are free. Go ahead and send one now:\n"
                    "https://suoops.com/dashboard/invoices/new\n\n"
                )
                if referral_code and referral_link:
                    plain += (
                        "🎁 Earn ₦488 per friend you refer\n"
                        f"Your referral code: {referral_code}\n"
                        f"Your invite link: {referral_link}\n"
                    )
                    if referral_share_url:
                        plain += f"Share on WhatsApp: {referral_share_url}\n"
                    plain += "Track earnings: https://suoops.com/dashboard/referrals\n\n"
                plain += (
                    "We're here if you need anything.\n\n"
                    "— The SuoOps Team"
                )
                result["email_sent"] = _send_email(
                    user.email,
                    "Welcome to SuoOps — You're All Set! 🎉",
                    html,
                    plain,
                )
            except Exception as e:
                logger.warning("Instant welcome email failed for user %s: %s", user_id, e)

        # ── 2. WhatsApp ──────────────────────────────────────────────
        if user.phone and settings.WHATSAPP_TEMPLATE_ACTIVATION_WELCOME:
            try:
                from app.core.whatsapp import get_whatsapp_client

                client = get_whatsapp_client()
                lang = settings.WHATSAPP_TEMPLATE_LANGUAGE or "en"
                components = [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": name}],
                    }
                ]
                ok = client.send_template(
                    user.phone,
                    settings.WHATSAPP_TEMPLATE_ACTIVATION_WELCOME,
                    lang,
                    components,
                )
                result["whatsapp_sent"] = bool(ok)
            except Exception as e:
                logger.warning("Instant welcome WhatsApp failed for user %s: %s", user_id, e)

        # ── 3. Guided onboarding (start first-invoice flow on WhatsApp) ──
        if user.phone and result.get("whatsapp_sent"):
            try:
                import time
                time.sleep(3)  # Brief pause so welcome template arrives first
                from app.bot.onboarding_flow import send_onboarding_prompt, start_onboarding
                from app.core.whatsapp import get_whatsapp_client

                client = get_whatsapp_client()
                start_onboarding(user.phone, user.id)
                send_onboarding_prompt(client, user.phone, name)
                logger.info("Started onboarding flow for user %s", user_id)
            except Exception as e:
                logger.warning("Onboarding prompt failed for user %s: %s", user_id, e)

        # ── 4. Referral nudge (so the code is one tap away from day zero) ──
        if user.phone and result.get("whatsapp_sent") and referral_code:
            try:
                import time
                time.sleep(4)  # Let onboarding prompt land first
                from app.core.whatsapp import get_whatsapp_client
                from app.services.referral_share import (
                    build_referral_whatsapp_message,
                )

                client = get_whatsapp_client()
                client.send_text(
                    user.phone,
                    build_referral_whatsapp_message(user.name or name, referral_code),
                )
                logger.info("Sent referral card to user %s", user_id)
            except Exception as e:
                logger.warning("Referral nudge failed for user %s: %s", user_id, e)

        # ── Record so Daily activation skips duplicate welcome ───────
        if result["email_sent"] or result["whatsapp_sent"]:
            db.add(UserEmailLog(user_id=user_id, email_type="instant_welcome"))
            db.flush()

        logger.info(
            "Instant welcome for user %s: email=%s, wa=%s",
            user_id,
            result["email_sent"],
            result["whatsapp_sent"],
        )

    return result


def _send_email(to_email: str, subject: str, html_body: str, plain_body: str) -> bool:
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
        logger.warning("Instant welcome SMTP failed to %s: %s", to_email, e)
        return False


# ─────────────────────────────────────────────────────────────────────
# First-paid-invoice referral nudge
# ─────────────────────────────────────────────────────────────────────
# Trigger: dispatched from InvoiceStatusMixin.update_status when an invoice
# transitions to "paid". We only actually message the user when this is
# their FIRST paid invoice — that's the moment of peak motivation
# ("SuoOps got me paid!") so the referral ask lands well.
FIRST_PAID_REFERRAL_LOG_TYPE = "first_paid_referral_nudge"


@celery_app.task(
    name="referral.send_first_paid_nudge",
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_kwargs={"max_retries": 2},
    soft_time_limit=30,
    time_limit=45,
)
def send_first_paid_referral_nudge(user_id: int) -> dict:
    """Send a one-time referral nudge after the user's first paid invoice.

    Idempotent — guarded by ``UserEmailLog`` so retries / repeated paid
    transitions don't spam the user.
    """
    from sqlalchemy import func

    from app.models import models
    from app.models.models import User, UserEmailLog

    result = {"sent": False, "skipped_reason": None}

    with session_scope() as db:
        user = db.query(User).filter(User.id == user_id).one_or_none()
        if not user or not user.phone:
            result["skipped_reason"] = "no_user_or_phone"
            return result

        # Dedup: only ever send this nudge once per user
        already = (
            db.query(UserEmailLog.id)
            .filter(
                UserEmailLog.user_id == user_id,
                UserEmailLog.email_type == FIRST_PAID_REFERRAL_LOG_TYPE,
            )
            .first()
        )
        if already:
            result["skipped_reason"] = "already_sent"
            return result

        # Confirm this really is the first paid invoice — guards against
        # races where status.py dispatches before checking, or back-fills.
        paid_count = (
            db.query(func.count(models.Invoice.id))
            .filter(
                models.Invoice.issuer_id == user_id,
                models.Invoice.status == "paid",
            )
            .scalar()
            or 0
        )
        if paid_count > 1:
            result["skipped_reason"] = "not_first_paid"
            db.add(UserEmailLog(user_id=user_id, email_type=FIRST_PAID_REFERRAL_LOG_TYPE))
            db.flush()
            return result

        try:
            from app.core.whatsapp import get_whatsapp_client
            from app.services.referral_service import ReferralService
            from app.services.referral_share import build_referral_whatsapp_message

            code_obj = ReferralService(db).get_or_create_referral_code(user_id)
            first_name = (user.name or "there").split()[0]

            intro = (
                f"🎉 *You just got paid, {first_name}!*\n\n"
                "Now's the perfect time — friends running businesses will trust "
                "*your* recommendation. Share SuoOps and earn *₦488* every time "
                "one of them upgrades to Pro 👇"
            )
            body = build_referral_whatsapp_message(user.name or first_name, code_obj.code)

            client = get_whatsapp_client()
            client.send_text(user.phone, intro)
            client.send_text(user.phone, body)

            db.add(UserEmailLog(user_id=user_id, email_type=FIRST_PAID_REFERRAL_LOG_TYPE))
            db.flush()
            result["sent"] = True
            logger.info("First-paid referral nudge sent to user %s", user_id)
        except Exception as e:
            logger.warning("First-paid referral nudge failed for user %s: %s", user_id, e)
            result["skipped_reason"] = f"error: {e}"

    return result
