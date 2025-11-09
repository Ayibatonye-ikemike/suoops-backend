from __future__ import annotations

import datetime as dt
import logging
import asyncio
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
        
        # Validate bank details are set
        if not user.bank_name or not user.account_number:
            raise ValueError(
                "Bank details required. Please add your bank information in Settings before creating invoices."
            )
        
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
        # Normalize timezone for paid_at in case backend (e.g., SQLite) returned naive datetime
        if invoice.paid_at is not None and invoice.paid_at.tzinfo is None:
            invoice.paid_at = invoice.paid_at.replace(tzinfo=dt.timezone.utc)
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
        # Set paid_at when transitioning to paid
        if status == "paid" and invoice.paid_at is None:
            # Use timezone-aware UTC timestamp
            invoice.paid_at = dt.datetime.now(dt.timezone.utc)
        self.db.commit()
        # Normalize timezone awareness in case backend (e.g., SQLite) strips tzinfo on round-trip
        if invoice.paid_at and invoice.paid_at.tzinfo is None:
            invoice.paid_at = invoice.paid_at.replace(tzinfo=dt.timezone.utc)
            self.db.commit()
        if status == "paid" and previous_status != "paid":
            metrics.invoice_paid()
            # Generate receipt PDF if missing
            try:
                if not invoice.receipt_pdf_url:
                    invoice.receipt_pdf_url = self.pdf_service.generate_receipt_pdf(invoice)
                    self.db.commit()
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to generate receipt PDF for %s: %s", invoice_id, e)
            # Send receipt to customer (manual payment confirmation) using NotificationService facade
            logger.info("Invoice %s manually marked as paid, sending receipt", invoice_id)
            try:
                from app.services.notification.service import NotificationService

                service = NotificationService()
                customer_email = getattr(invoice.customer, "email", None) if invoice.customer else None
                customer_phone = getattr(invoice.customer, "phone", None) if invoice.customer else None
                async def _run():  # pragma: no cover - network IO
                    return await service.send_receipt_notification(
                        invoice=invoice,
                        customer_email=customer_email,
                        customer_phone=customer_phone,
                        pdf_url=invoice.pdf_url,
                    )
                results = asyncio.run(_run())
                logger.info(
                    "Receipt sent for invoice %s - Email: %s, WhatsApp: %s, SMS: %s",
                    invoice.invoice_id,
                    results["email"],
                    results["whatsapp"],
                    results["sms"],
                )
            except Exception as e:  # noqa: BLE001
                logger.error("Failed to send receipt notifications for %s: %s", invoice.invoice_id, e)
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
            # Notify business owner directly via NotificationService (legacy helper removed)
            try:
                from app.models import models as _models  # local import to avoid circulars
                user = (
                    self.db.query(_models.User)
                    .filter(_models.User.id == invoice.issuer_id)
                    .one_or_none()
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to load issuer for invoice %s: %s", invoice.invoice_id, exc)
                return invoice
            if not user:
                logger.warning("Cannot notify business for invoice %s: issuer missing", invoice.invoice_id)
                return invoice
            message = (
                "Customer reported a transfer.\n\n"
                f"Invoice: {invoice.invoice_id}\n"
                f"Amount: ₦{invoice.amount:,.2f}\n\n"
                "Please confirm the funds and mark the invoice as paid to send their receipt."
            )
            try:
                from app.services.notification.service import NotificationService
                service = NotificationService()
                async def _run():  # pragma: no cover - network IO
                    results = {"email": False, "sms": False}
                    if user.email:
                        try:
                            results["email"] = await service.send_email(
                                to_email=user.email,
                                subject=f"Payment Confirmation - Invoice {invoice.invoice_id}",
                                body=message,
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.error("Failed email notify business %s: %s", invoice.invoice_id, exc)
                    if user.phone:
                        try:
                            results["sms"] = await service.send_receipt_sms(invoice, user.phone)
                        except Exception as exc:  # noqa: BLE001
                            logger.error("Failed SMS notify business %s: %s", invoice.invoice_id, exc)
                    logger.info(
                        "Business notification for invoice %s - Email: %s, SMS: %s",
                        invoice.invoice_id,
                        results["email"],
                        results["sms"],
                    )
                asyncio.run(_run())
            except Exception as e:  # noqa: BLE001
                logger.error("Notification dispatch failed for invoice %s: %s", invoice.invoice_id, e)

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

    # (legacy invoice_notifications helpers removed; direct NotificationService facade usage in methods)

    # ---------- Internal helpers ----------
    def _get_or_create_customer(
        self, name: str, phone: str | None, email: str | None = None
    ) -> models.Customer:
        q = self.db.query(models.Customer).filter(models.Customer.name == name)
        if phone:
            q = q.filter(models.Customer.phone == phone)
        elif email:
            q = q.filter(models.Customer.email == email)
        # Use first() instead of one_or_none() to tolerate duplicate legacy rows with same (name, phone)
        existing = q.first()
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

