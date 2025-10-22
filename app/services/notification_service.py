from __future__ import annotations

import logging
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

import httpx

from app.core.config import settings

if TYPE_CHECKING:
    from app.models import models

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending invoice notifications via email and WhatsApp."""
    
    def _get_smtp_config(self) -> dict[str, str | int] | None:
        """Get SMTP configuration based on EMAIL_PROVIDER setting.
        
        Returns:
            dict with host, port, user, password or None if not configured
        """
        provider = getattr(settings, "EMAIL_PROVIDER", "gmail").lower()
        
        if provider == "ses":
            # Amazon SES configuration
            host = getattr(settings, "SES_SMTP_HOST", None)
            port = getattr(settings, "SES_SMTP_PORT", 587)
            user = getattr(settings, "SES_SMTP_USER", None)
            password = getattr(settings, "SES_SMTP_PASSWORD", None)
            
            if not all([host, user, password]):
                logger.warning("Amazon SES not configured. Set SES_SMTP_USER and SES_SMTP_PASSWORD")
                return None
                
            logger.info("Using Amazon SES for email: %s", host)
            return {
                "host": host,
                "port": port,
                "user": user,
                "password": password,
                "provider": "Amazon SES"
            }
        
        else:  # Default to Gmail
            # Gmail SMTP configuration
            host = getattr(settings, "SMTP_HOST", None)
            port = getattr(settings, "SMTP_PORT", 587)
            user = getattr(settings, "SMTP_USER", None)
            password = getattr(settings, "SMTP_PASSWORD", None)
            
            if not all([host, user, password]):
                logger.warning("Gmail SMTP not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD")
                return None
                
            logger.info("Using Gmail SMTP for email: %s", host)
            return {
                "host": host,
                "port": port,
                "user": user,
                "password": password,
                "provider": "Gmail"
            }
    
    def send_invoice_created(self, to: str, invoice_id: str):
        logger.info("Notify %s invoice %s created", to, invoice_id)
    
    async def send_invoice_email(
        self,
        invoice: "models.Invoice",
        recipient_email: str,
        pdf_url: str | None = None,
        subject: str = "New Invoice"
    ) -> bool:
        """Send invoice email with PDF attachment.
        
        Args:
            invoice: Invoice model instance
            recipient_email: Customer email address
            pdf_url: URL to invoice PDF (will be downloaded and attached)
            subject: Email subject line
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            # Get SMTP configuration based on provider
            smtp_config = self._get_smtp_config()
            if not smtp_config:
                logger.warning("No email provider configured")
                return False
            
            smtp_host = smtp_config["host"]
            smtp_port = smtp_config["port"]
            smtp_user = smtp_config["user"]
            smtp_password = smtp_config["password"]
            provider_name = smtp_config["provider"]
            
            # Get FROM email (use FROM_EMAIL if set, otherwise use SMTP_USER)
            from_email = getattr(settings, "FROM_EMAIL", smtp_user)
            
            logger.info("Sending email via %s to %s", provider_name, recipient_email)
            
            # Create email message
            msg = MIMEMultipart()
            msg['From'] = from_email
            msg['To'] = recipient_email
            msg['Subject'] = f"{subject} - {invoice.invoice_id}"
            
            # Email body
            body = f"""
Hello {invoice.customer.name if invoice.customer else 'Customer'},

Your invoice {invoice.invoice_id} for ₦{invoice.amount:,.2f} has been generated.

Invoice Details:
- Invoice ID: {invoice.invoice_id}
- Amount: ₦{invoice.amount:,.2f}
- Status: {invoice.status.upper()}
{f"- Due Date: {invoice.due_date.strftime('%B %d, %Y')}" if invoice.due_date else ""}

Please find your invoice attached as a PDF.

Thank you for your business!

---
Powered by SuoPay
"""
            msg.attach(MIMEText(body, 'plain'))
            
            # Download and attach PDF if URL provided
            if pdf_url:
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.get(pdf_url)
                        response.raise_for_status()
                        pdf_data = response.content
                    
                    pdf_attachment = MIMEApplication(pdf_data, _subtype='pdf')
                    pdf_attachment.add_header(
                        'Content-Disposition',
                        'attachment',
                        filename=f'Invoice_{invoice.invoice_id}.pdf'
                    )
                    msg.attach(pdf_attachment)
                    logger.info("Attached PDF from %s", pdf_url)
                except Exception as e:
                    logger.error("Failed to download PDF for email attachment: %s", e)
            
            # Send email via SMTP
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
            
            logger.info("Sent invoice email to %s for invoice %s", recipient_email, invoice.invoice_id)
            return True
            
        except Exception as e:
            logger.error("Failed to send invoice email: %s", e)
            return False

