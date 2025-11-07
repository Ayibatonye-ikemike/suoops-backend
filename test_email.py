"""Test email sending with Brevo SMTP"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings
import os
import pytest

@pytest.mark.integration
def test_email():
    """Connectivity smoke test for SMTP settings.

    Converted to a non-interactive assertion-based test; skipped automatically if SMTP credentials
    are not configured to avoid hanging on input() in CI.
    """
    if not os.getenv("INTEGRATION"):
        pytest.skip("Skipping SMTP connectivity test (set INTEGRATION=1 to run)")
    if not (settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD and settings.FROM_EMAIL):
        pytest.skip("SMTP credentials not configured; skipping")

    msg = MIMEMultipart()
    msg['From'] = settings.FROM_EMAIL
    # Use FROM_EMAIL as recipient for loopback test to avoid interactive input
    test_recipient = settings.FROM_EMAIL
    msg['To'] = test_recipient
    msg['Subject'] = "SMTP Loopback Test"

    body = "SMTP connectivity loopback test from SuoOps backend."
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=5) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
    except Exception as e:  # noqa: BLE001
        assert False, f"SMTP send failed: {e}"
    # If no exception, test passes
    assert True

if __name__ == "__main__":
    test_email()
