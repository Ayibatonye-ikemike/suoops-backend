from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session, selectinload

from app import metrics
from app.models import models
from app.utils.id_generator import generate_id

if TYPE_CHECKING:
    from app.services.pdf_service import PDFService

logger = logging.getLogger(__name__)


class InvoiceService:
    _allowed_statuses = {"pending", "paid", "failed"}

    def __init__(self, db: Session, pdf_service: PDFService):
        """Initialize InvoiceService.
        
        Simple bank transfer model:
        - No payment platform integration
        - Invoices show business bank account details
        - Customers pay via bank transfer
        - Business manually marks as paid
        - System sends receipt automatically
        """
        self.db = db
        self.pdf_service = pdf_service

    # ---------- Public API ----------
    def check_invoice_quota(self, issuer_id: int) -> dict[str, object]:
        """Check if user can create more invoices this month.
        
        Returns:
            dict with:
                - can_create: bool - whether user can create invoice
                - plan: str - current subscription plan
                - used: int - invoices used this month
                - limit: int|None - invoice limit (None = unlimited)
                - message: str - upgrade message if at limit
        """
        user = self.db.query(models.User).filter(models.User.id == issuer_id).one_or_none()
        if not user:
            raise ValueError("User not found")
        
        # Reset usage if new month started
        self._reset_usage_if_needed(user)
        
        plan_limit = user.plan.invoice_limit
        
        # Unlimited plans (Enterprise)
        if plan_limit is None:
            return {
                "can_create": True,
                "plan": user.plan.value,
                "used": user.invoices_this_month,
                "limit": None,
                "message": "Unlimited invoices on Enterprise plan",
            }
        
        # Check if at limit
        if user.invoices_this_month >= plan_limit:
            upgrade_message = self._get_upgrade_message(user.plan)
            return {
                "can_create": False,
                "plan": user.plan.value,
                "used": user.invoices_this_month,
                "limit": plan_limit,
                "message": upgrade_message,
            }
        
        # Can create, but warn if approaching limit
        remaining = plan_limit - user.invoices_this_month
        message = f"{remaining} invoices remaining this month"
        if remaining <= 5:
            upgrade_message = self._get_upgrade_message(user.plan)
            message = f"⚠️ Only {remaining} invoices left! {upgrade_message}"
        
        return {
            "can_create": True,
            "plan": user.plan.value,
            "used": user.invoices_this_month,
            "limit": plan_limit,
            "message": message,
        }

    def _reset_usage_if_needed(self, user: models.User) -> None:
        """Reset monthly usage counter if we're in a new month."""
        now = dt.datetime.now(dt.timezone.utc)
        last_reset = user.usage_reset_at.replace(tzinfo=dt.timezone.utc)
        
        # Check if month changed
        if now.year > last_reset.year or (now.year == last_reset.year and now.month > last_reset.month):
            user.invoices_this_month = 0
            user.usage_reset_at = now
            self.db.commit()
            logger.info("Reset invoice usage for user %s (new month)", user.id)

    def _get_upgrade_message(self, current_plan: models.SubscriptionPlan) -> str:
        """Get upgrade prompt based on current plan."""
        messages = {
            models.SubscriptionPlan.FREE: "Upgrade to Starter (₦2,500/month) for 100 invoices!",
            models.SubscriptionPlan.STARTER: "Upgrade to Pro (₦7,500/month) for 1,000 invoices!",
            models.SubscriptionPlan.PRO: "Upgrade to Business (₦15,000/month) for 3,000 invoices!",
            models.SubscriptionPlan.BUSINESS: "Contact sales for Enterprise (unlimited invoices)!",
            models.SubscriptionPlan.ENTERPRISE: "",  # Should never reach limit
        }
        return messages.get(current_plan, "Upgrade to increase your invoice limit!")

    def create_invoice(self, issuer_id: int, data: dict[str, object]) -> models.Invoice:
        # Check quota before creating invoice
        quota_check = self.check_invoice_quota(issuer_id)
        if not quota_check["can_create"]:
            raise ValueError(
                f"Invoice limit reached. {quota_check['message']}"
            )
        
        customer = self._get_or_create_customer(
            data.get("customer_name"),
            data.get("customer_phone"),
        )
        discount_raw = data.get("discount_amount")
        discount_amount = Decimal(str(discount_raw)) if discount_raw else None
        invoice = models.Invoice(
            invoice_id=generate_id("INV"),
            issuer_id=issuer_id,
            customer=customer,
            amount=Decimal(str(data.get("amount"))),
            discount_amount=discount_amount,
            due_date=data.get("due_date"),
        )
        lines_data = data.get("lines") or [
            {
                "description": data.get("description", "Item"),
                "quantity": 1,
                "unit_price": invoice.amount,
            }
        ]
        for line_data in lines_data:
            line = models.InvoiceLine(
                description=line_data["description"],
                quantity=line_data.get("quantity", 1),
                unit_price=Decimal(str(line_data["unit_price"])),
            )
            invoice.lines.append(line)
        self.db.add(invoice)
        self.db.commit()
        self.db.refresh(invoice)

        # Get issuer's bank details for the PDF
        user = self.db.query(models.User).filter(models.User.id == issuer_id).one()
        bank_details = {
            "bank_name": user.bank_name,
            "account_number": user.account_number,
            "account_name": user.account_name,
        }
        
        # Generate PDF with bank transfer details
        pdf_url = self.pdf_service.generate_invoice_pdf(invoice, bank_details=bank_details)
        invoice.pdf_url = pdf_url
        
        # Increment usage counter
        user.invoices_this_month += 1
        
        self.db.commit()
        logger.info("Created invoice %s for issuer %s (usage: %s/%s)", 
                   invoice.invoice_id, issuer_id, user.invoices_this_month, 
                   user.plan.invoice_limit or "unlimited")
        metrics.invoice_created()
        return invoice

    def list_invoices(self, issuer_id: int) -> list[models.Invoice]:
        return (
            self.db.query(models.Invoice)
            .filter(models.Invoice.issuer_id == issuer_id)
            .options(selectinload(models.Invoice.customer))
            .order_by(models.Invoice.id.desc())
            .limit(50)
            .all()
        )

    def get_invoice(self, issuer_id: int, invoice_id: str) -> models.Invoice:
        invoice = (
            self.db.query(models.Invoice)
            .options(
                selectinload(models.Invoice.lines),
                selectinload(models.Invoice.customer),
            )
            .filter(models.Invoice.invoice_id == invoice_id, models.Invoice.issuer_id == issuer_id)
            .one_or_none()
        )
        if not invoice:
            raise ValueError("Invoice not found")
        return invoice

    def update_status(self, issuer_id: int, invoice_id: str, status: str) -> models.Invoice:
        if status not in self._allowed_statuses:
            raise ValueError("Unsupported status")
        invoice = (
            self.db.query(models.Invoice)
            .options(selectinload(models.Invoice.customer))
            .filter(models.Invoice.invoice_id == invoice_id, models.Invoice.issuer_id == issuer_id)
            .one_or_none()
        )
        if not invoice:
            raise ValueError("Invoice not found")
        previous_status = invoice.status
        if previous_status == status:
            return invoice
        invoice.status = status
        self.db.commit()
        if status == "paid" and previous_status != "paid":
            metrics.invoice_paid()
            # Send receipt to customer (manual payment confirmation)
            logger.info("Invoice %s manually marked as paid, sending receipt", invoice_id)
            self._send_receipt_to_customer(invoice)
        return self.get_invoice(issuer_id, invoice_id)

    def list_events(self, invoice_id: str) -> list[models.WebhookEvent]:
        return (
            self.db.query(models.WebhookEvent)
            .filter(models.WebhookEvent.external_id == invoice_id)
            .order_by(models.WebhookEvent.created_at.desc())
            .limit(20)
            .all()
        )

    def _send_receipt_to_customer(self, invoice: models.Invoice) -> None:
        """Send payment receipt to customer via WhatsApp."""
        try:
            from app.bot.whatsapp_adapter import WhatsAppClient
            from app.core.config import settings
            
            whatsapp_key = getattr(settings, "WHATSAPP_API_KEY", None)
            if not whatsapp_key or not invoice.customer or not invoice.customer.phone:
                logger.info("Cannot send receipt: missing WhatsApp config or customer phone")
                return
            
            client = WhatsAppClient(whatsapp_key)
            
            # Send receipt message
            receipt_message = f"🎉 Payment Received!\n\n"
            receipt_message += f"Thank you for your payment!\n\n"
            receipt_message += f"📄 Invoice: {invoice.invoice_id}\n"
            receipt_message += f"💰 Amount Paid: ₦{invoice.amount:,.2f}\n"
            receipt_message += f"✅ Status: PAID\n\n"
            receipt_message += f"Your receipt has been generated and sent to you."
            
            client.send_text(invoice.customer.phone, receipt_message)
            
            # If PDF URL is accessible, send receipt PDF
            if invoice.pdf_url and invoice.pdf_url.startswith("http"):
                client.send_document(
                    invoice.customer.phone,
                    invoice.pdf_url,
                    f"Receipt_{invoice.invoice_id}.pdf",
                    f"Payment Receipt - ₦{invoice.amount:,.2f}"
                )
            
            logger.info("Sent receipt for invoice %s to customer %s", 
                       invoice.invoice_id, invoice.customer.phone)
        except Exception as e:
            logger.error("Failed to send receipt to customer: %s", e)

    # ---------- Internal helpers ----------
    def _get_or_create_customer(self, name: str, phone: str | None) -> models.Customer:
        q = self.db.query(models.Customer).filter(models.Customer.name == name)
        if phone:
            q = q.filter(models.Customer.phone == phone)
        existing = q.one_or_none()
        if existing:
            return existing
        c = models.Customer(name=name, phone=phone)
        self.db.add(c)
        self.db.flush()
        return c


# Dependency factory
def build_invoice_service(db: Session, user_id: int | None = None) -> InvoiceService:
    """Factory function to construct InvoiceService with dependencies.
    
    Simple bank transfer model - no payment platform integration needed.
    
    Args:
        db: Database session
        user_id: Business owner's user ID (optional, not used in simple model)
    
    Returns:
        InvoiceService configured with PDF generation
    """
    from app.services.pdf_service import PDFService
    from app.storage.s3_client import S3Client

    pdf = PDFService(S3Client())
    return InvoiceService(db, pdf)

