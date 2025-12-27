from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:  # pragma: no cover
    from app.models import models
    from app.services.notification.service import NotificationService

logger = logging.getLogger(__name__)


class WhatsAppChannel:
    """Encapsulates WhatsApp messaging for invoices and receipts.
    
    Centralizes the WhatsApp first-time customer logic:
    - For customers who have opted-in (replied before): send full invoice with payment details
    - For new customers: send template message and mark invoice as pending follow-up
    
    This ensures consistent behavior whether invoices are created from:
    - Dashboard (via NotificationService)
    - WhatsApp bot (via InvoiceIntentProcessor)
    """

    def __init__(self, service: "NotificationService") -> None:
        self._service = service

    async def send_invoice(
        self,
        invoice: "models.Invoice",
        recipient_phone: str,
        pdf_url: str | None,
    ) -> bool:
        """Send invoice notification to customer via WhatsApp using template.
        
        Always uses template message for invoice notifications because:
        - Meta's 24-hour messaging window expires, so regular messages may fail
        - Templates work anytime, regardless of when customer last messaged
        - Provides consistent experience for all customers
        
        Returns True if template was sent successfully.
        """
        logger.info(
            "[WHATSAPP CHANNEL] send_invoice called for %s to phone=%s",
            invoice.invoice_id,
            recipient_phone,
        )
        try:
            if not self._service.whatsapp_key or not self._service.whatsapp_phone_number_id:
                logger.warning("WhatsApp not configured. Set WHATSAPP_API_KEY and WHATSAPP_PHONE_NUMBER_ID")
                return False
            
            from app.bot.whatsapp_client import WhatsAppClient
            client = WhatsAppClient(self._service.whatsapp_key)
            
            # Always use template for invoice notifications
            # This ensures delivery regardless of 24-hour messaging window
            return await self._send_template_only(client, invoice, recipient_phone)
                
        except Exception as e:  # pragma: no cover - network failures
            logger.error("Failed to send invoice via WhatsApp: %s", e)
            return False
    
    def _is_registered_user(self, phone: str, invoice: "models.Invoice") -> bool:
        """Check if a phone number belongs to a registered business user."""
        from sqlalchemy.orm import object_session
        from app.models import models
        
        # Normalize phone for lookup
        normalized = phone.replace(" ", "").replace("-", "")
        if not normalized.startswith("+"):
            if normalized.startswith("0"):
                normalized = "+234" + normalized[1:]
            elif normalized.startswith("234"):
                normalized = "+" + normalized
            else:
                normalized = "+" + normalized
        
        # Get db session from invoice object
        db = object_session(invoice)
        if not db:
            return False
            
        # Check if phone exists in users table
        user = db.query(models.User).filter(models.User.phone == normalized).first()
        if user:
            logger.info("[WHATSAPP] Recipient phone %s is a registered user (ID: %s)", phone, user.id)
            return True
        return False

    async def _send_full_invoice(
        self,
        client,
        invoice: "models.Invoice",
        recipient_phone: str,
        pdf_url: str | None,
    ) -> bool:
        """Send full invoice with payment details to opted-in customers."""
        business_name = "Business"
        if hasattr(invoice, "issuer") and invoice.issuer:
            business_name = getattr(invoice.issuer, "business_name", None) or business_name
        
        # Build payment message with bank details if available
        message = self._build_payment_message(invoice, business_name)
        
        client.send_text(recipient_phone, message)
        
        # Send PDF if available
        if pdf_url and pdf_url.startswith("http"):
            client.send_document(
                recipient_phone,
                pdf_url,
                f"Invoice_{invoice.invoice_id}.pdf",
                f"Invoice {invoice.invoice_id} - ₦{invoice.amount:,.2f}",
            )
        
        # Clear pending flag if it was set
        if getattr(invoice, "whatsapp_delivery_pending", False):
            invoice.whatsapp_delivery_pending = False
            # Note: Caller should commit the session
            
        logger.info("[WHATSAPP] Full invoice sent to opted-in customer %s", recipient_phone)
        return True

    async def _send_template_only(
        self,
        client,
        invoice: "models.Invoice",
        recipient_phone: str,
    ) -> bool:
        """Send invoice template with full payment details.
        
        Uses 'invoice_with_payment' template if configured (includes bank details),
        falls back to basic 'invoice_notification' template.
        """
        # Try the full invoice template with payment details first
        template_name = getattr(settings, "WHATSAPP_TEMPLATE_INVOICE_PAYMENT", None)
        
        if template_name:
            # Use the full template with bank details
            return await self._send_invoice_with_payment_template(
                client, invoice, recipient_phone, template_name
            )
        
        # Fall back to basic invoice template
        template_name = getattr(settings, "WHATSAPP_TEMPLATE_INVOICE", None)
        
        if not template_name:
            logger.warning("[WHATSAPP] No invoice template configured, cannot notify customer")
            return False
        
        customer_name = invoice.customer.name if invoice.customer else "valued customer"
        amount_text = f"₦{invoice.amount:,.2f}"
        
        # Build items text
        items_text = self._build_items_text(invoice)
        items_with_cta = f"{items_text}. Reply 'Hi' to get payment details"
        
        components = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": customer_name},
                    {"type": "text", "text": invoice.invoice_id},
                    {"type": "text", "text": amount_text},
                    {"type": "text", "text": items_with_cta},
                ],
            }
        ]
        
        template_sent = client.send_template(
            recipient_phone,
            template_name=template_name,
            language=getattr(settings, "WHATSAPP_TEMPLATE_LANGUAGE", "en"),
            components=components,
        )
        
        if template_sent:
            # Mark invoice as pending follow-up delivery
            invoice.whatsapp_delivery_pending = True
            # Note: Caller should commit the session
            logger.info("[WHATSAPP] Template sent to customer %s, invoice marked pending", recipient_phone)
        else:
            logger.warning("[WHATSAPP] Failed to send template to %s", recipient_phone)
        
        return template_sent

    async def _send_invoice_with_payment_template(
        self,
        client,
        invoice: "models.Invoice",
        recipient_phone: str,
        template_name: str,
    ) -> bool:
        """Send invoice template with full bank details and payment link."""
        customer_name = invoice.customer.name if invoice.customer else "valued customer"
        amount_text = f"₦{invoice.amount:,.2f}"
        items_text = self._build_items_text(invoice)
        
        # Get issuer's bank details
        issuer = getattr(invoice, "issuer", None)
        bank_name = getattr(issuer, "bank_name", "N/A") if issuer else "N/A"
        account_number = getattr(issuer, "account_number", "N/A") if issuer else "N/A"
        account_name = getattr(issuer, "account_name", "N/A") if issuer else "N/A"
        
        # Build payment link
        frontend_url = getattr(settings, "FRONTEND_URL", "https://suoops.com")
        payment_link = f"{frontend_url.rstrip('/')}/pay/{invoice.invoice_id}"
        
        # 8 parameters: customer_name, invoice_id, amount, items, bank, account, account_name, payment_link
        components = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": customer_name},
                    {"type": "text", "text": invoice.invoice_id},
                    {"type": "text", "text": amount_text},
                    {"type": "text", "text": items_text},
                    {"type": "text", "text": bank_name},
                    {"type": "text", "text": account_number},
                    {"type": "text", "text": account_name},
                    {"type": "text", "text": payment_link},
                ],
            }
        ]
        
        template_sent = client.send_template(
            recipient_phone,
            template_name=template_name,
            language=getattr(settings, "WHATSAPP_TEMPLATE_LANGUAGE", "en"),
            components=components,
        )
        
        if template_sent:
            logger.info("[WHATSAPP] Full invoice template sent to %s with payment details", recipient_phone)
        else:
            logger.warning("[WHATSAPP] Failed to send full invoice template to %s", recipient_phone)
        
        return template_sent
        
        return template_sent

    def _build_payment_message(self, invoice: "models.Invoice", business_name: str) -> str:
        """Build payment message with bank details."""
        message = (
            f"📄 New Invoice from {business_name}\n\n"
            f"Invoice ID: {invoice.invoice_id}\n"
            f"Amount: ₦{invoice.amount:,.2f}\n"
            f"Status: {invoice.status.upper()}\n"
        )
        
        if invoice.due_date:
            message += f"Due: {invoice.due_date.strftime('%B %d, %Y')}\n"
        
        # Add bank details if available
        issuer = getattr(invoice, "issuer", None)
        if issuer and getattr(issuer, "bank_name", None) and getattr(issuer, "account_number", None):
            message += (
                "\n💳 Payment Details (Bank Transfer):\n"
                f"Bank: {issuer.bank_name}\n"
                f"Account: {issuer.account_number}\n"
            )
            if getattr(issuer, "account_name", None):
                message += f"Name: {issuer.account_name}\n"
        
        # Add payment link
        frontend_url = getattr(settings, "FRONTEND_URL", "https://suoops.com")
        payment_link = f"{frontend_url.rstrip('/')}/pay/{invoice.invoice_id}"
        message += f"\n🔗 View & Pay: {payment_link}"
        
        return message

    def _build_items_text(self, invoice: "models.Invoice") -> str:
        """Build a text representation of invoice line items."""
        if not invoice.lines or len(invoice.lines) == 0:
            return "Invoice items"
        
        # Limit to first 3 items to keep message short
        lines = invoice.lines[:3]
        parts = []
        for line in lines:
            desc = getattr(line, "description", "Item")
            qty = getattr(line, "quantity", 1)
            parts.append(f"{desc} x{qty}")
        
        text = ", ".join(parts)
        if len(invoice.lines) > 3:
            text += f" +{len(invoice.lines) - 3} more"
        
        return text

    async def send_receipt(
        self,
        invoice: "models.Invoice",
        recipient_phone: str,
        pdf_url: str | None,
    ) -> bool:
        """Send payment receipt to customer via WhatsApp.
        
        Uses template message for reliability (works outside 24-hour window),
        then sends PDF document if available.
        """
        try:
            if not self._service.whatsapp_key or not self._service.whatsapp_phone_number_id:
                logger.warning("WhatsApp not configured for receipt")
                return False
            
            from app.bot.whatsapp_client import WhatsAppClient
            import datetime as dt
            
            client = WhatsAppClient(self._service.whatsapp_key)
            
            # Try to use receipt template first (works outside 24-hour window)
            template_name = getattr(settings, "WHATSAPP_TEMPLATE_RECEIPT", None)
            
            if template_name:
                # Use payment_receipt template
                customer_name = invoice.customer.name if invoice.customer else "valued customer"
                amount_text = f"₦{invoice.amount:,.2f}"
                date_text = dt.datetime.now().strftime("%b %d, %Y")
                
                components = [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": customer_name},
                            {"type": "text", "text": invoice.invoice_id},
                            {"type": "text", "text": amount_text},
                            {"type": "text", "text": date_text},
                        ],
                    }
                ]
                
                template_sent = client.send_template(
                    recipient_phone,
                    template_name=template_name,
                    language=getattr(settings, "WHATSAPP_TEMPLATE_LANGUAGE", "en"),
                    components=components,
                )
                
                if template_sent:
                    logger.info("[WHATSAPP] Receipt template sent to %s", recipient_phone)
                    # Now send PDF document (should work since template opened conversation)
                    if pdf_url and pdf_url.startswith("http"):
                        client.send_document(
                            recipient_phone,
                            pdf_url,
                            f"Receipt_{invoice.invoice_id}.pdf",
                            f"Payment Receipt - {amount_text}",
                        )
                    return True
                else:
                    logger.warning("[WHATSAPP] Receipt template failed for %s, trying regular message", recipient_phone)
            
            # Fallback to regular message (may fail if outside 24-hour window)
            receipt_message = (
                "🎉 Payment Received!\n\n"
                "Thank you for your payment!\n\n"
                f"📄 Invoice: {invoice.invoice_id}\n"
                f"💰 Amount Paid: ₦{invoice.amount:,.2f}\n"
                "✅ Status: PAID\n\n"
                "Your receipt is attached below."
            )
            
            client.send_text(recipient_phone, receipt_message)
            
            if pdf_url and pdf_url.startswith("http"):
                client.send_document(
                    recipient_phone,
                    pdf_url,
                    f"Receipt_{invoice.invoice_id}.pdf",
                    f"Payment Receipt - ₦{invoice.amount:,.2f}",
                )
            
            return True
        except Exception as e:  # pragma: no cover - network failures
            logger.error("Failed to send receipt via WhatsApp: %s", e)
            return False
