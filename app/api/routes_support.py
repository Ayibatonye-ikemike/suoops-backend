"""Support routes for contact form and help center."""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.core.config import settings

router = APIRouter(prefix="/support", tags=["support"])
logger = logging.getLogger(__name__)


class ContactRequest(BaseModel):
    """Contact form request schema."""
    name: str
    email: EmailStr
    category: str
    subject: str
    message: str


class ContactResponse(BaseModel):
    """Contact form response schema."""
    success: bool
    message: str


def _get_smtp_config() -> dict | None:
    """Get SMTP configuration from settings."""
    if settings.BREVO_SMTP_HOST and settings.BREVO_SMTP_USER and settings.BREVO_SMTP_PASSWORD:
        return {
            "host": settings.BREVO_SMTP_HOST,
            "port": int(settings.BREVO_SMTP_PORT or 587),
            "user": settings.BREVO_SMTP_USER,
            "password": settings.BREVO_SMTP_PASSWORD,
        }
    return None


def _send_contact_email(contact: ContactRequest) -> bool:
    """Send contact form email to support."""
    try:
        smtp_config = _get_smtp_config()
        if not smtp_config:
            logger.warning("No email provider configured for support contact")
            return False

        smtp_host = smtp_config["host"]
        smtp_port = smtp_config["port"]
        smtp_user = smtp_config["user"]
        smtp_password = smtp_config["password"]
        from_email = getattr(settings, "FROM_EMAIL", smtp_user)
        support_email = getattr(settings, "SUPPORT_EMAIL", "support@suoops.com")

        # Email to support team
        msg = MIMEMultipart()
        msg["From"] = from_email
        msg["To"] = support_email
        msg["Reply-To"] = contact.email
        msg["Subject"] = f"[Support - {contact.category.upper()}] {contact.subject}"

        body = f"""
New Support Request from Help Center
=====================================

From: {contact.name}
Email: {contact.email}
Category: {contact.category}
Subject: {contact.subject}
Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

Message:
{'-' * 40}
{contact.message}
{'-' * 40}

---
This email was sent from the SuoOps Help Center contact form.
Reply directly to this email to respond to the customer.
"""
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        logger.info("Support contact email sent from %s (category: %s)", contact.email, contact.category)

        # Send confirmation to the user
        _send_confirmation_email(contact, smtp_config, from_email)

        return True
    except Exception as e:
        logger.error("Failed to send support contact email: %s", e)
        return False


def _send_confirmation_email(contact: ContactRequest, smtp_config: dict, from_email: str) -> None:
    """Send confirmation email to the user."""
    try:
        msg = MIMEMultipart()
        msg["From"] = from_email
        msg["To"] = contact.email
        msg["Subject"] = f"We received your message - {contact.subject}"

        body = f"""
Hello {contact.name},

Thank you for contacting SuoOps Support. We have received your message and will respond within 24 hours.

Your Request Summary:
- Category: {contact.category}
- Subject: {contact.subject}

Your Message:
{contact.message}

In the meantime, you may find answers to common questions in our Help Center:
https://support.suoops.com/faq

Thank you for using SuoOps!

Best regards,
The SuoOps Support Team

---
This is an automated confirmation. Please do not reply to this email.
For additional help, visit: https://support.suoops.com
"""
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(smtp_config["host"], smtp_config["port"]) as server:
            server.starttls()
            server.login(smtp_config["user"], smtp_config["password"])
            server.send_message(msg)

        logger.info("Confirmation email sent to %s", contact.email)
    except Exception as e:
        # Don't fail the main request if confirmation fails
        logger.warning("Failed to send confirmation email to %s: %s", contact.email, e)


@router.post("/contact", response_model=ContactResponse)
async def submit_contact_form(contact: ContactRequest) -> ContactResponse:
    """
    Submit a contact form from the support portal.
    
    This endpoint is public (no authentication required) to allow
    visitors and customers to reach support.
    """
    # Basic validation
    if not contact.name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name is required"
        )
    
    if not contact.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message is required"
        )
    
    if len(contact.message) > 10000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message is too long (max 10,000 characters)"
        )

    # Send email
    success = _send_contact_email(contact)
    
    if not success:
        # Log but don't expose internal details
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to send message at this time. Please try again later."
        )
    
    return ContactResponse(
        success=True,
        message="Your message has been sent. We'll respond within 24 hours."
    )
