from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session, selectinload, joinedload

from app import metrics
from app.models import models
from app.utils.id_generator import generate_id

if TYPE_CHECKING:
    from app.services.pdf_service import PDFService

logger = logging.getLogger(__name__)


class InvoiceService:
    _allowed_statuses = {"pending", "awaiting_confirmation", "paid", "failed"}

    def __init__(self, db: Session, pdf_service: PDFService):
        """Core invoice workflow built around manual bank-transfer confirmations."""
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
            data.get("customer_email"),
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
        
        # Generate PDF with bank transfer details and logo
        pdf_url = self.pdf_service.generate_invoice_pdf(
            invoice, 
            bank_details=bank_details,
            logo_url=user.logo_url
        )
        invoice.pdf_url = pdf_url
        
        # Increment usage counter
        user.invoices_this_month += 1
        
        self.db.commit()
        
        # Reload invoice with relationships for notifications
        self.db.refresh(invoice)
        invoice = (
            self.db.query(models.Invoice)
            .options(
                joinedload(models.Invoice.customer),
                joinedload(models.Invoice.issuer),
            )
            .filter(models.Invoice.id == invoice.id)
            .one()
        )
        
        logger.info("Created invoice %s for issuer %s (usage: %s/%s)", 
                   invoice.invoice_id, issuer_id, user.invoices_this_month, 
                   user.plan.invoice_limit or "unlimited")
        metrics.invoice_created()
        return invoice

    def list_invoices(self, issuer_id: int) -> list[models.Invoice]:
        """List recent invoices with related entities preloaded to avoid N+1.

        Uses joinedload for small one-to-one/one-to-many sets and selectinload for collections.
        """
        return (
            self.db.query(models.Invoice)
            .filter(models.Invoice.issuer_id == issuer_id)
            .options(
                joinedload(models.Invoice.customer),
                selectinload(models.Invoice.lines),
                joinedload(models.Invoice.issuer),
            )
            .order_by(models.Invoice.id.desc())
            .limit(50)
            .all()
        )

    def get_invoice(self, issuer_id: int, invoice_id: str) -> models.Invoice:
        invoice = (
            self.db.query(models.Invoice)
            .options(
                selectinload(models.Invoice.lines),
                joinedload(models.Invoice.customer),
                joinedload(models.Invoice.issuer),
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
            .options(joinedload(models.Invoice.customer), joinedload(models.Invoice.issuer))
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

    def confirm_transfer(self, invoice_id: str) -> models.Invoice:
        """Mark an invoice as awaiting business confirmation after the customer reports payment."""

        invoice = (
            self.db.query(models.Invoice)
            .options(
                selectinload(models.Invoice.customer),
            )
            .filter(models.Invoice.invoice_id == invoice_id)
            .one_or_none()
        )

        if not invoice:
            raise ValueError("Invoice not found")

        if invoice.status == "paid":
            return invoice

        if invoice.status != "awaiting_confirmation":
            previous_status = invoice.status
            invoice.status = "awaiting_confirmation"
            self.db.commit()
            logger.info(
                "Invoice %s status transitioned %s → awaiting_confirmation after customer confirmation",
                invoice_id,
                previous_status,
            )
            self._notify_business_of_customer_confirmation(invoice)

        return invoice

    def get_public_invoice(self, invoice_id: str) -> tuple[models.Invoice, models.User]:
        invoice = (
            self.db.query(models.Invoice)
            .options(
                selectinload(models.Invoice.customer),
                selectinload(models.Invoice.lines),
            )
            .filter(models.Invoice.invoice_id == invoice_id)
            .one_or_none()
        )

        if not invoice:
            raise ValueError("Invoice not found")

        issuer = (
            self.db.query(models.User)
            .filter(models.User.id == invoice.issuer_id)
            .one_or_none()
        )

        if not issuer:
            raise ValueError("Invoice issuer not found")

        return invoice, issuer

    def _send_receipt_to_customer(self, invoice: models.Invoice) -> None:
        """Send payment receipt to customer via Email, WhatsApp, and SMS."""
        import asyncio
        
        try:
            from app.services.notification_service import NotificationService
            
            notification_service = NotificationService()
            
            if not invoice.customer:
                logger.info("Cannot send receipt: no customer on invoice %s", invoice.invoice_id)
                return
            
            # Get customer contact info
            customer_email = getattr(invoice.customer, 'email', None)
            customer_phone = getattr(invoice.customer, 'phone', None)
            
            if not customer_email and not customer_phone:
                logger.info("Cannot send receipt: no contact info for invoice %s", invoice.invoice_id)
                return
            
            # Send receipts via all channels
            try:
                # Create and run async task for sending receipt notifications
                async def send_receipt():
                    return await notification_service.send_receipt_notification(
                        invoice=invoice,
                        customer_email=customer_email,
                        customer_phone=customer_phone,
                        pdf_url=invoice.pdf_url,
                    )
                
                # Run the async function
                results = asyncio.run(send_receipt())
                logger.info("Receipt sent for invoice %s - Email: %s, WhatsApp: %s, SMS: %s",
                           invoice.invoice_id, results["email"], results["whatsapp"], results["sms"])
            except Exception as e:
                logger.error("Failed to send receipt notifications: %s", e)
            
        except Exception as e:
            logger.error("Failed to send receipt to customer: %s", e)

    def _notify_business_of_customer_confirmation(self, invoice: models.Invoice) -> None:
        """Notify the business owner that the customer marked the invoice as transferred.
        
        Sends notification via Email and SMS to the business owner.
        """
        from app.core.config import settings
        import asyncio

        try:
            user = self.db.query(models.User).filter(models.User.id == invoice.issuer_id).one_or_none()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to load issuer for invoice %s: %s", invoice.invoice_id, exc)
            return

        if not user:
            logger.warning("Cannot notify business for invoice %s: issuer missing", invoice.invoice_id)
            return

        # Prepare notification message
        message = (
            "🔔 Customer reported a transfer.\n\n"
            f"Invoice: {invoice.invoice_id}\n"
            f"Amount: ₦{invoice.amount:,.2f}\n\n"
            "Please confirm the funds and mark the invoice as paid to send their receipt."
        )

        # Send via Email and SMS
        async def send_notifications():
            from app.services.notification_service import NotificationService
            notification_service = NotificationService()
            
            results = {"email": False, "sms": False}
            
            # Send Email notification to business
            if user.email:
                try:
                    results["email"] = await notification_service.send_email(
                        to_email=user.email,
                        subject=f"Payment Confirmation - Invoice {invoice.invoice_id}",
                        body=message.replace("🔔", ""),  # Remove emoji for email
                    )
                except Exception as exc:
                    logger.error("Failed to send email notification to business for invoice %s: %s", 
                               invoice.invoice_id, exc)
            
            # Send SMS notification to business phone
            if user.phone:
                try:
                    results["sms"] = await notification_service._send_brevo_sms(
                        to_phone=user.phone,
                        message=message.replace("🔔", ""),  # Remove emoji for SMS
                    )
                except Exception as exc:
                    logger.error("Failed to send SMS notification to business for invoice %s: %s", 
                               invoice.invoice_id, exc)
            
            logger.info(
                "Business notification for invoice %s - Email: %s, SMS: %s",
                invoice.invoice_id,
                results["email"],
                results["sms"],
            )
        
        # Run async notifications
        try:
            asyncio.create_task(send_notifications())
        except RuntimeError:
            # If no event loop, run in new loop
            asyncio.run(send_notifications())

    # ---------- Internal helpers ----------
    def _get_or_create_customer(
        self, name: str, phone: str | None, email: str | None = None
    ) -> models.Customer:
        q = self.db.query(models.Customer).filter(models.Customer.name == name)
        if phone:
            q = q.filter(models.Customer.phone == phone)
        elif email:
            q = q.filter(models.Customer.email == email)
        existing = q.one_or_none()
        if existing:
            # Update email if provided and not already set
            if email and not existing.email:
                existing.email = email
            return existing
        c = models.Customer(name=name, phone=phone, email=email)
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

