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
                )
                plain = (
                    f"Hi {name}! 🎉\n\n"
                    "Welcome to SuoOps — you're all set!\n\n"
                    "You can now:\n"
                    "📄 Create and send invoices in under 60 seconds\n"
                    "💬 Or just message us on WhatsApp: +234 818 376 3636\n\n"
                    "Your first 5 invoices are free. Go ahead and send one now:\n"
                    "https://suoops.com/dashboard/invoices/new\n\n"
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
