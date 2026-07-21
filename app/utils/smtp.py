"""Shared SMTP email helper used by Celery tasks."""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)

# Reusable SMTP connection for batch sends (avoids reconnect per email)
_smtp_connection: smtplib.SMTP | None = None


def get_smtp_config() -> tuple[str, int, str | None, str | None, str]:
    """Provider-agnostic SMTP config with block precedence:

        1. ZeptoMail  (SMTP_*_ZEP)   — primary, once its user+password are set
        2. Generic    (SMTP_*)
        3. Brevo      (BREVO_SMTP_LOGIN / BREVO_API_KEY) — automatic fallback

    Each tier is used as a whole block (host+creds together) so a new provider's
    host is never paired with another provider's credentials. Switching is a pure
    env change; Brevo stays available as a safety net.
    """
    # 1) ZeptoMail (explicit _ZEP vars).
    zep_user = getattr(settings, "SMTP_USER_ZEP", None)
    zep_pass = getattr(settings, "SMTP_PASSWORD_ZEP", None)
    if zep_user and zep_pass:
        host = getattr(settings, "SMTP_HOST_ZEP", None) or "smtp.zeptomail.com"
        port = getattr(settings, "SMTP_PORT_ZEP", None) or getattr(settings, "SMTP_PORT", 587)
        from_email = (
            getattr(settings, "FROM_EMAIL_ZEP", None)
            or getattr(settings, "FROM_EMAIL", None)
            or "noreply@suoops.com"
        )
        return host, port, zep_user, zep_pass, from_email

    # 2) Generic SMTP_*.
    user = getattr(settings, "SMTP_USER", None)
    password = getattr(settings, "SMTP_PASSWORD", None)
    if user and password:
        host = getattr(settings, "SMTP_HOST", None) or "smtp-relay.brevo.com"
        port = getattr(settings, "SMTP_PORT", 587)
        from_email = getattr(settings, "FROM_EMAIL", None) or "noreply@suoops.com"
        return host, port, user, password, from_email

    # 3) Legacy Brevo fallback.
    host = getattr(settings, "SMTP_HOST", None) or "smtp-relay.brevo.com"
    port = getattr(settings, "SMTP_PORT", 587)
    user = getattr(settings, "BREVO_SMTP_LOGIN", None)
    password = getattr(settings, "BREVO_API_KEY", None)
    from_email = getattr(settings, "FROM_EMAIL", None) or "noreply@suoops.com"
    return host, port, user, password, from_email


# Backwards-compat alias (was module-private).
_get_smtp_config = get_smtp_config


def send_smtp_email(to_email: str, subject: str, html_body: str | None, plain_body: str) -> bool:
    """Send an email via Brevo SMTP. Returns True on success."""
    smtp_host, smtp_port, smtp_user, smtp_password, from_email = _get_smtp_config()

    if not smtp_user or not smtp_password:
        logger.warning("SMTP not configured, skipping email to %s", to_email)
        return False

    # Never email a hard-bounced / complained address — protects sender reputation.
    from app.services.email_suppression import is_suppressed
    if is_suppressed(to_email):
        logger.info("Skipping suppressed address %s", to_email)
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(plain_body, "plain"))
    if html_body:
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


def send_smtp_batch(
    emails: list[tuple[str, str, str | None, str]],
) -> list[bool]:
    """Send a batch of emails over a single SMTP connection.

    Each item is (to_email, subject, html_body, plain_body).
    Returns a list of booleans (True=success) in the same order.

    Much faster than calling send_smtp_email() in a loop because
    the TLS handshake + login happens once instead of per-email.
    """
    smtp_host, smtp_port, smtp_user, smtp_password, from_email = _get_smtp_config()

    if not smtp_user or not smtp_password:
        logger.warning("SMTP not configured, skipping batch of %d emails", len(emails))
        return [False] * len(emails)

    from app.services.email_suppression import is_suppressed

    results: list[bool] = []
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)

            for to_email, subject, html_body, plain_body in emails:
                if is_suppressed(to_email):
                    logger.info("Skipping suppressed address %s", to_email)
                    results.append(False)
                    continue
                msg = MIMEMultipart("alternative")
                msg["From"] = from_email
                msg["To"] = to_email
                msg["Subject"] = subject
                msg.attach(MIMEText(plain_body, "plain"))
                if html_body:
                    msg.attach(MIMEText(html_body, "html"))
                try:
                    server.send_message(msg)
                    results.append(True)
                except Exception as e:
                    logger.warning("Batch SMTP send failed to %s: %s", to_email, e)
                    results.append(False)
    except Exception as e:
        logger.warning("Batch SMTP connection failed: %s", e)
        # Mark all remaining as failed
        results.extend([False] * (len(emails) - len(results)))

    return results
