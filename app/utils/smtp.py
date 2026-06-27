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


def _get_smtp_config() -> tuple[str, int, str | None, str | None, str]:
    smtp_host = getattr(settings, "SMTP_HOST", None) or "smtp-relay.brevo.com"
    smtp_port = getattr(settings, "SMTP_PORT", 587)
    smtp_user = getattr(settings, "SMTP_USER", None) or getattr(settings, "BREVO_SMTP_LOGIN", None)
    smtp_password = getattr(settings, "SMTP_PASSWORD", None) or getattr(settings, "BREVO_API_KEY", None)
    from_email = getattr(settings, "FROM_EMAIL", None) or "noreply@suoops.com"
    return smtp_host, smtp_port, smtp_user, smtp_password, from_email


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
