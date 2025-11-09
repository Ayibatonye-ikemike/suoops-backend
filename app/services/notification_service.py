from __future__ import annotations

import logging
from datetime import datetime, timezone
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
    
    def __init__(self):
        """Initialize notification service."""
        self.whatsapp_key = getattr(settings, "WHATSAPP_API_KEY", None)
        self.whatsapp_phone_number_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", None)
        
        # SMS provider configuration
        self.sms_provider = getattr(settings, "SMS_PROVIDER", "brevo")
        
        # Brevo (Sendinblue) configuration
        self.brevo_api_key = getattr(settings, "BREVO_API_KEY", None)
        self.brevo_sender_name = getattr(settings, "BREVO_SENDER_NAME", "SuoOps")
        
        # Termii configuration (alternative)
        self.termii_api_key = getattr(settings, "TERMII_API_KEY", None)
        self.termii_sender_id = getattr(settings, "TERMII_SENDER_ID", "SuoOps")
        self.termii_device_id = getattr(settings, "TERMII_DEVICE_ID", "TID")
    
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
            
            # Build payment link
            frontend_url = getattr(settings, "FRONTEND_URL", "https://suoops.com")
            payment_link = f"{frontend_url.rstrip('/')}/pay/{invoice.invoice_id}"
            
            # Email body
            body = f"""
Hello {invoice.customer.name if invoice.customer else 'Customer'},

Your invoice {invoice.invoice_id} for ₦{invoice.amount:,.2f} has been generated.

Invoice Details:
- Invoice ID: {invoice.invoice_id}
- Amount: ₦{invoice.amount:,.2f}
- Status: {invoice.status.upper()}
{f"- Due Date: {invoice.due_date.strftime('%B %d, %Y')}" if invoice.due_date else ""}

📌 Click here to make payment:
{payment_link}

The payment page will show you our bank details which you can copy and use to transfer the amount. After transferring, please confirm your payment on the page.

Please find your invoice attached as a PDF.

Thank you for your business!

---
Powered by SuoOps
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

    async def send_invoice_whatsapp(
        self,
        invoice: "models.Invoice",
        recipient_phone: str,
        pdf_url: str | None = None,
    ) -> bool:
        """Send invoice via WhatsApp with PDF attachment.
        
        Args:
            invoice: Invoice model instance
            recipient_phone: Customer phone number
            pdf_url: URL to invoice PDF (will be sent as document)
            
        Returns:
            bool: True if WhatsApp message sent successfully, False otherwise
        """
        try:
            if not self.whatsapp_key or not self.whatsapp_phone_number_id:
                logger.warning("WhatsApp not configured. Set WHATSAPP_API_KEY and WHATSAPP_PHONE_NUMBER_ID")
                return False
            
            from app.bot.whatsapp_client import WhatsAppClient
            
            client = WhatsAppClient(self.whatsapp_key)
            
            # Get business name from issuer
            business_name = "Business"
            if hasattr(invoice, 'issuer') and invoice.issuer:
                business_name = getattr(invoice.issuer, 'business_name', None) or business_name
            
            # Send invoice notification message
            customer_name = invoice.customer.name if invoice.customer else "Customer"
            message = f"📄 New Invoice from {business_name}\n\n"
            message += f"Invoice ID: {invoice.invoice_id}\n"
            message += f"Amount: ₦{invoice.amount:,.2f}\n"
            message += f"Status: {invoice.status.upper()}\n"
            if invoice.due_date:
                message += f"Due: {invoice.due_date.strftime('%B %d, %Y')}\n"
            
            # Build payment link
            frontend_url = getattr(settings, "FRONTEND_URL", "https://suoops.com")
            payment_link = f"{frontend_url.rstrip('/')}/pay/{invoice.invoice_id}"
            message += f"\n🔗 View & Pay: {payment_link}"
            
            client.send_text(recipient_phone, message)
            logger.info("Sent invoice WhatsApp message to %s", recipient_phone)
            
            # Send PDF if available
            if pdf_url and pdf_url.startswith("http"):
                client.send_document(
                    recipient_phone,
                    pdf_url,
                    f"Invoice_{invoice.invoice_id}.pdf",
                    f"Invoice {invoice.invoice_id} - ₦{invoice.amount:,.2f}"
                )
                logger.info("Sent invoice PDF to %s via WhatsApp", recipient_phone)
            
            return True
            
        except Exception as e:
            logger.error("Failed to send invoice via WhatsApp: %s", e)
            return False

    async def send_receipt_whatsapp(
        self,
        invoice: "models.Invoice",
        recipient_phone: str,
        pdf_url: str | None = None,
    ) -> bool:
        """Send payment receipt via WhatsApp with PDF attachment.
        
        Args:
            invoice: Invoice model instance
            recipient_phone: Customer phone number
            pdf_url: URL to receipt PDF (will be sent as document)
            
        Returns:
            bool: True if WhatsApp message sent successfully, False otherwise
        """
        try:
            if not self.whatsapp_key or not self.whatsapp_phone_number_id:
                logger.warning("WhatsApp not configured for receipt")
                return False
            
            from app.bot.whatsapp_client import WhatsAppClient
            
            client = WhatsAppClient(self.whatsapp_key)
            
            # Send receipt message
            receipt_message = f"🎉 Payment Received!\n\n"
            receipt_message += f"Thank you for your payment!\n\n"
            receipt_message += f"📄 Invoice: {invoice.invoice_id}\n"
            receipt_message += f"💰 Amount Paid: ₦{invoice.amount:,.2f}\n"
            receipt_message += f"✅ Status: PAID\n\n"
            receipt_message += f"Your receipt is attached below."
            
            client.send_text(recipient_phone, receipt_message)
            logger.info("Sent receipt WhatsApp message to %s", recipient_phone)
            
            # Send receipt PDF if available
            if pdf_url and pdf_url.startswith("http"):
                client.send_document(
                    recipient_phone,
                    pdf_url,
                    f"Receipt_{invoice.invoice_id}.pdf",
                    f"Payment Receipt - ₦{invoice.amount:,.2f}"
                )
                logger.info("Sent receipt PDF to %s via WhatsApp", recipient_phone)
            
            return True
            
        except Exception as e:
            logger.error("Failed to send receipt via WhatsApp: %s", e)
            return False

    async def send_invoice_sms(
        self,
        invoice: "models.Invoice",
        recipient_phone: str,
    ) -> bool:
        """Send invoice notification via SMS.
        
        Args:
            invoice: Invoice model instance
            recipient_phone: Customer phone number
            
        Returns:
            bool: True if SMS sent successfully, False otherwise
        """
        try:
            # Get business name from issuer
            business_name = "Business"
            if hasattr(invoice, 'issuer') and invoice.issuer:
                business_name = getattr(invoice.issuer, 'business_name', None) or business_name
            
            # Build payment link
            frontend_url = getattr(settings, "FRONTEND_URL", "https://suoops.com")
            payment_link = f"{frontend_url.rstrip('/')}/pay/{invoice.invoice_id}"
            
            # SMS message (160 characters max for single SMS)
            message = f"New invoice from {business_name}: {invoice.invoice_id}\n"
            message += f"Amount: ₦{invoice.amount:,.2f}\n"
            message += f"Pay here: {payment_link}"
            
            # Send via configured provider
            if self.sms_provider == "brevo":
                if not self.brevo_api_key:
                    logger.warning("SMS not configured. Set BREVO_API_KEY")
                    return False
                success = await self._send_brevo_sms(recipient_phone, message)
            elif self.sms_provider == "termii":
                if not self.termii_api_key:
                    logger.warning("SMS not configured. Set TERMII_API_KEY")
                    return False
                success = await self._send_termii_sms(recipient_phone, message)
            else:
                logger.warning("Unsupported SMS provider: %s", self.sms_provider)
                return False
            
            if success:
                logger.info("Sent invoice SMS to %s via %s", recipient_phone, self.sms_provider)
            return success
            
        except Exception as e:
            logger.error("Failed to send invoice via SMS: %s", e)
            return False

    async def send_receipt_sms(
        self,
        invoice: "models.Invoice",
        recipient_phone: str,
    ) -> bool:
        """Send payment receipt notification via SMS.
        
        Args:
            invoice: Invoice model instance
            recipient_phone: Customer phone number
            
        Returns:
            bool: True if SMS sent successfully, False otherwise
        """
        try:
            # Get business name from issuer
            business_name = "Business"
            if hasattr(invoice, 'issuer') and invoice.issuer:
                business_name = getattr(invoice.issuer, 'business_name', None) or business_name
            
            # SMS message
            message = f"Payment received! Thank you for paying invoice {invoice.invoice_id}\n"
            message += f"Amount: ₦{invoice.amount:,.2f}\n"
            message += f"Status: PAID\n"
            message += f"- {business_name}"
            
            # Send via configured provider
            if self.sms_provider == "brevo":
                if not self.brevo_api_key:
                    logger.warning("SMS not configured for receipt")
                    return False
                success = await self._send_brevo_sms(recipient_phone, message)
            elif self.sms_provider == "termii":
                if not self.termii_api_key:
                    logger.warning("SMS not configured for receipt")
                    return False
                success = await self._send_termii_sms(recipient_phone, message)
            else:
                logger.warning("Unsupported SMS provider: %s", self.sms_provider)
                return False
            
            if success:
                logger.info("Sent receipt SMS to %s via %s", recipient_phone, self.sms_provider)
            return success
            
        except Exception as e:
            logger.error("Failed to send receipt via SMS: %s", e)
            return False

    async def _send_brevo_sms(self, to: str, message: str) -> bool:
        """Send SMS via Brevo (Sendinblue) API.
        
        Args:
            to: Phone number (with country code, e.g., +2348012345678)
            message: SMS message text
            
        Returns:
            bool: True if sent successfully
        """
        try:
            url = "https://api.brevo.com/v3/transactionalSMS/send"
            
            # Remove + prefix and any spaces for Brevo (they expect just numbers with country code)
            phone = to.replace("+", "").replace(" ", "").replace("-", "")
            
            payload = {
                "sender": self.brevo_sender_name,
                "recipient": phone,
                "content": message,
                "type": "transactional",
            }
            
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "api-key": self.brevo_api_key,
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                # Brevo returns messageId on success
                if data.get("messageId"):
                    logger.info("Brevo SMS sent successfully to %s (messageId: %s)", to, data.get("messageId"))
                    return True
                else:
                    logger.error("Brevo SMS failed: %s", data)
                    return False
                    
        except Exception as e:
            logger.error("Failed to send Brevo SMS: %s", e)
            return False

    async def _send_termii_sms(self, to: str, message: str) -> bool:
        """Send SMS via Termii API.
        
        Args:
            to: Phone number (with country code)
            message: SMS message text
            
        Returns:
            bool: True if sent successfully
        """
        try:
            url = "https://api.ng.termii.com/api/sms/send"
            
            # Clean phone number (remove + if present, Termii expects it without +)
            phone = to.replace("+", "")
            
            payload = {
                "to": phone,
                "from": self.termii_sender_id,
                "sms": message,
                "type": "plain",
                "channel": "generic",
                "api_key": self.termii_api_key,
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                
                # Termii returns message_id on success
                if data.get("message_id"):
                    logger.info("Termii SMS sent successfully to %s", to)
                    return True
                else:
                    logger.error("Termii SMS failed: %s", data)
                    return False
                    
        except Exception as e:
            logger.error("Failed to send Termii SMS: %s", e)
            return False

    async def send_invoice_notification(
        self,
        invoice: "models.Invoice",
        customer_email: str | None = None,
        customer_phone: str | None = None,
        pdf_url: str | None = None,
    ) -> dict[str, bool]:
        """Send invoice notification via all available channels.
        
        Sends via Email, WhatsApp, and SMS if the customer contact info is provided.
        
        Args:
            invoice: Invoice model instance
            customer_email: Customer email address (optional)
            customer_phone: Customer phone number (optional)
            pdf_url: URL to invoice PDF
            
        Returns:
            dict: Status of each channel {"email": bool, "whatsapp": bool, "sms": bool}
        """
        results = {"email": False, "whatsapp": False, "sms": False}
        
        # Send Email if email provided
        if customer_email:
            results["email"] = await self.send_invoice_email(
                invoice=invoice,
                recipient_email=customer_email,
                pdf_url=pdf_url,
                subject="New Invoice"
            )
        
        # Send WhatsApp if phone provided
        if customer_phone:
            results["whatsapp"] = await self.send_invoice_whatsapp(
                invoice=invoice,
                recipient_phone=customer_phone,
                pdf_url=pdf_url,
            )
            
            # Send SMS (text message) as well
            results["sms"] = await self.send_invoice_sms(
                invoice=invoice,
                recipient_phone=customer_phone,
            )
        
        logger.info("Invoice notification sent - Email: %s, WhatsApp: %s, SMS: %s",
                   results["email"], results["whatsapp"], results["sms"])
        return results

    async def send_receipt_notification(
        self,
        invoice: "models.Invoice",
        customer_email: str | None = None,
        customer_phone: str | None = None,
        pdf_url: str | None = None,
    ) -> dict[str, bool]:
        """Send payment receipt via all available channels.
        
        Sends via Email, WhatsApp, and SMS if the customer contact info is provided.
        
        Args:
            invoice: Invoice model instance
            customer_email: Customer email address (optional)
            customer_phone: Customer phone number (optional)
            pdf_url: URL to receipt PDF (same as invoice PDF for now)
            
        Returns:
            dict: Status of each channel {"email": bool, "whatsapp": bool, "sms": bool}
        """
        results = {"email": False, "whatsapp": False, "sms": False}
        
        # Send Email if email provided  
        if customer_email:
            results["email"] = await self._send_receipt_email(
                invoice=invoice,
                recipient_email=customer_email,
                pdf_url=pdf_url,
            )
        
        # Send WhatsApp if phone provided
        if customer_phone:
            results["whatsapp"] = await self.send_receipt_whatsapp(
                invoice=invoice,
                recipient_phone=customer_phone,
                pdf_url=pdf_url,
            )
            
            # Send SMS (text message) as well
            results["sms"] = await self.send_receipt_sms(
                invoice=invoice,
                recipient_phone=customer_phone,
            )
        
        logger.info("Receipt notification sent - Email: %s, WhatsApp: %s, SMS: %s",
                   results["email"], results["whatsapp"], results["sms"])
        return results

    async def _send_receipt_email(
        self,
        invoice: "models.Invoice",
        recipient_email: str,
        pdf_url: str | None = None,
    ) -> bool:
        """Send payment receipt email with receipt PDF attachment (currently using invoice PDF).
        
        Args:
            invoice: Invoice model instance
            recipient_email: Customer email address
            pdf_url: URL to invoice PDF
            
        Returns:
            bool: True if email sent successfully
        """
        try:
            smtp_config = self._get_smtp_config()
            if not smtp_config:
                logger.warning("No email provider configured")
                return False
            
            smtp_host = smtp_config["host"]
            smtp_port = smtp_config["port"]
            smtp_user = smtp_config["user"]
            smtp_password = smtp_config["password"]
            
            from_email = getattr(settings, "FROM_EMAIL", smtp_user)
            
            # Create email message
            msg = MIMEMultipart()
            msg['From'] = from_email
            msg['To'] = recipient_email
            msg['Subject'] = f"Payment Receipt - {invoice.invoice_id}"
            
            # Receipt email body
            body = f"""
Hello {invoice.customer.name if invoice.customer else 'Customer'},

Thank you for your payment! We have received your payment for invoice {invoice.invoice_id}.

Payment Confirmation:
- Invoice ID: {invoice.invoice_id}
- Amount Paid: ₦{invoice.amount:,.2f}
- Status: PAID ✓
- Payment Date: {datetime.now(timezone.utc).strftime('%B %d, %Y')}

Your receipt is attached as a PDF for your records.

Thank you for your business!

---
Powered by SuoOps
"""
            msg.attach(MIMEText(body, 'plain'))
            
            # Download and attach PDF if available
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
                        filename=f'Receipt_{invoice.invoice_id}.pdf'
                    )
                    msg.attach(pdf_attachment)
                except Exception as e:
                    logger.error("Failed to download PDF for receipt: %s", e)
            
            # Send email
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
            
            logger.info("Sent receipt email to %s for invoice %s", recipient_email, invoice.invoice_id)
            return True
            
        except Exception as e:
            logger.error("Failed to send receipt email: %s", e)
            return False

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
    ) -> bool:
        """Send a simple text email.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Email body text
            
        Returns:
            bool: True if sent successfully
        """
        try:
            smtp_config = self._get_smtp_config()
            if not smtp_config:
                logger.warning("No email provider configured")
                return False
            
            smtp_host = smtp_config["host"]
            smtp_port = smtp_config["port"]
            smtp_user = smtp_config["user"]
            smtp_password = smtp_config["password"]
            
            from_email = getattr(settings, "FROM_EMAIL", smtp_user)
            
            msg = MIMEMultipart()
            msg['From'] = from_email
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
            
            logger.info("Simple email sent to %s", to_email)
            return True
            
        except Exception as e:
            logger.error("Failed to send email to %s: %s", to_email, e)
            return False



