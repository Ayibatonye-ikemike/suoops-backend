from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app import metrics
from app.db.session import get_db
from app.models import models
from app.utils.id_generator import generate_id

if TYPE_CHECKING:
    from app.services.payment_service import PaymentService
    from app.services.pdf_service import PDFService

logger = logging.getLogger(__name__)


class InvoiceService:
    _allowed_statuses = {"pending", "paid", "failed"}

    def __init__(self, db: Session, pdf_service: PDFService, payment_service: PaymentService):
        self.db = db
        self.pdf_service = pdf_service
        self.payment_service = payment_service

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
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "invoice_limit_reached",
                    "message": quota_check["message"],
                    "plan": quota_check["plan"],
                    "used": quota_check["used"],
                    "limit": quota_check["limit"],
                }
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

        # Payment link
        pay_link = self.payment_service.create_payment_link(invoice.invoice_id, invoice.amount)
        invoice.payment_url = pay_link
        
        # PDF
        pdf_url = self.pdf_service.generate_invoice_pdf(invoice, payment_url=pay_link)
        invoice.pdf_url = pdf_url
        
        # Increment usage counter
        user = self.db.query(models.User).filter(models.User.id == issuer_id).one()
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

    def handle_payment_webhook(self, payload: dict) -> None:
        ref = payload.get("reference")
        status = payload.get("status")
        if not ref:
            return
        inv = (
            self.db.query(models.Invoice)
            .options(selectinload(models.Invoice.customer))
            .filter(models.Invoice.invoice_id == ref)
            .one_or_none()
        )
        if not inv:
            logger.warning("Webhook for unknown invoice ref=%s", ref)
            return
        if status == "success":
            previous_status = inv.status
            inv.status = "paid"
            self.db.commit()
            logger.info("Invoice %s marked paid", ref)
            metrics.invoice_paid()
            
            # Send receipt to customer via WhatsApp
            if previous_status != "paid" and inv.customer and inv.customer.phone:
                self._send_receipt_to_customer(inv)

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


# Dependency factory (simple placeholder)
def build_invoice_service(db: Session) -> InvoiceService:
    from app.services.payment_service import PaymentService
    from app.services.pdf_service import PDFService
    from app.storage.s3_client import S3Client

    pdf = PDFService(S3Client())
    payment = PaymentService()
    return InvoiceService(db, pdf, payment)


def get_invoice_service(db: Annotated[Session, Depends(get_db)]) -> InvoiceService:
    return build_invoice_service(db)
