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
from app.core.exceptions import (
    InvoiceNotFoundError,
    InvoiceLimitExceededError,
    InvalidInvoiceStatusError,
    MissingBankDetailsError,
    UserNotFoundError,
)

if TYPE_CHECKING:
    from app.services.pdf_service import PDFService
    from app.services.cache_service import InvoiceCacheRepository

logger = logging.getLogger(__name__)


class InvoiceService:
    _allowed_statuses = {"pending", "awaiting_confirmation", "paid", "failed"}

    def __init__(self, db: Session, pdf_service: PDFService, cache: InvoiceCacheRepository | None = None):
        """Core invoice workflow with optional caching layer.
        
        Args:
            db: Database session
            pdf_service: PDF generation service
            cache: Optional invoice cache repository (follows Dependency Inversion Principle)
        """
        self.db = db
        self.pdf_service = pdf_service
        self.cache = cache

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
            raise UserNotFoundError()
        
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

    def create_invoice(
        self,
        issuer_id: int,
        data: dict[str, object],
        async_pdf: bool = False,
    ) -> models.Invoice:
        # Check quota before creating invoice (only for revenue invoices)
        invoice_type = data.get("invoice_type", "revenue")
        if invoice_type == "revenue":
            quota_check = self.check_invoice_quota(issuer_id)
            if not quota_check["can_create"]:
                raise InvoiceLimitExceededError(
                    plan=quota_check["plan"],
                    limit=quota_check["limit"],
                    used=quota_check["used"],
                )
        
        # Handle customer/vendor based on invoice type
        if invoice_type == "revenue":
            # Revenue invoice: need customer
            customer = self._get_or_create_customer(
                data.get("customer_name"),
                data.get("customer_phone"),
                data.get("customer_email"),
            )
        else:
            # Expense invoice: create customer from vendor_name
            vendor_name = data.get("vendor_name") or data.get("merchant") or "Expense Vendor"
            customer = self._get_or_create_customer(
                vendor_name,
                None,  # vendors typically don't have phone
                None,  # vendors typically don't have email
            )
        
        discount_raw = data.get("discount_amount")
        discount_amount = Decimal(str(discount_raw)) if discount_raw else None
        
        # Expense invoices are automatically marked as paid (already paid expenses)
        status = "paid" if invoice_type == "expense" else "pending"
        paid_at = dt.datetime.now(dt.timezone.utc) if invoice_type == "expense" else None
        
        invoice = models.Invoice(
            invoice_id=generate_id("INV" if invoice_type == "revenue" else "EXP"),
            issuer_id=issuer_id,
            customer=customer,
            amount=Decimal(str(data.get("amount"))),
            discount_amount=discount_amount,
            due_date=data.get("due_date"),
            status=status,  # Auto-paid for expenses
            paid_at=paid_at,  # Set paid timestamp for expenses
            invoice_type=invoice_type,
            category=data.get("category"),
            vendor_name=data.get("vendor_name"),
            merchant=data.get("merchant"),
            receipt_url=data.get("receipt_url"),
            receipt_text=data.get("receipt_text"),
            input_method=data.get("input_method"),
            channel=data.get("channel"),
            verified=data.get("verified", False),
            notes=data.get("notes"),
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
        
        # Invalidate cache
        if self.cache:
            self.cache.invalidate_user_invoices(issuer_id)
        
        # Record metrics
        from app import metrics
        user = self.db.query(models.User).filter(models.User.id == issuer_id).one()
        metrics.invoice_created_by_plan(user.plan.value)
        total_amount = sum(float(line.unit_price) * line.quantity for line in invoice.lines)
        metrics.record_invoice_amount(total_amount)

        # Get issuer's details for the PDF
        
        # Generate PDF (different templates for revenue vs expense)
        if async_pdf:
            # Queue PDF generation as background task
            from app.workers.tasks import generate_invoice_pdf_async
            
            bank_details = None
            if invoice_type == "revenue":
                # Validate bank details are set for revenue invoices
                if not user.bank_name or not user.account_number:
                    raise MissingBankDetailsError()
                
                bank_details = {
                    "bank_name": user.bank_name,
                    "account_number": user.account_number,
                    "account_name": user.account_name,
                }
            
            # Queue task - PDF will be generated in background
            generate_invoice_pdf_async.delay(
                invoice_id=invoice.id,
                bank_details=bank_details,
                logo_url=user.logo_url,
                user_plan=user.plan.value,
            )
            
            # PDF URL will be updated by the background task
            invoice.pdf_url = None
            logger.info("Queued async PDF generation for invoice %s", invoice.invoice_id)
        else:
            # Generate PDF synchronously (original behavior)
            if invoice_type == "revenue":
                # Validate bank details are set for revenue invoices
                if not user.bank_name or not user.account_number:
                    raise MissingBankDetailsError()
                
                bank_details = {
                    "bank_name": user.bank_name,
                    "account_number": user.account_number,
                    "account_name": user.account_name,
                }
                
                # Generate revenue invoice PDF with bank transfer details and logo
                pdf_url = self.pdf_service.generate_invoice_pdf(
                    invoice, 
                    bank_details=bank_details,
                    logo_url=user.logo_url,
                    user_plan=user.plan.value  # Pass plan for VAT visibility
                )
            else:
                # Generate expense receipt PDF (simpler, no bank details needed)
                # For now, use the same PDF generator
                # TODO: Create expense-specific PDF template
                pdf_url = self.pdf_service.generate_invoice_pdf(
                    invoice,
                    bank_details=None,  # No bank details for expenses
                    logo_url=user.logo_url,
                    user_plan=user.plan.value  # Pass plan for VAT visibility
                )
            
            invoice.pdf_url = pdf_url
        
        # Increment usage counter (only for revenue invoices)
        if invoice_type == "revenue":
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
        
        logger.info("Created %s invoice %s for issuer %s", 
                   invoice_type, invoice.invoice_id, issuer_id)
        if invoice_type == "revenue":
            logger.info("Revenue invoice usage: %s/%s", 
                       user.invoices_this_month, user.plan.invoice_limit or "unlimited")
            metrics.invoice_created()
        
        # Invalidate cache after creating invoice
        if self.cache:
            self.cache.invalidate_user_invoices(issuer_id)
        
        return invoice

    def list_invoices(self, issuer_id: int) -> list[models.Invoice]:
        """List recent invoices with optional caching layer.

        Uses joinedload for small one-to-one/one-to-many sets and selectinload for collections.
        Cache-aside pattern: check cache first, fallback to database, then populate cache.
        """
        # Try cache first (if available)
        if self.cache:
            cached = self.cache.get_invoice_list(issuer_id)
            if cached is not None:
                # Note: Returning dict representation instead of models for simplicity
                # In production, might want to reconstruct models or return dicts consistently
                logger.info(f"Cache hit for user {issuer_id} invoice list")
                # For now, fall through to database (cache is read-through only)
        
        # Database query
        invoices = (
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
        
        # Populate cache
        if self.cache and invoices:
            self.cache.set_invoice_list(issuer_id, invoices)
        
        return invoices

    def get_invoice(self, issuer_id: int, invoice_id: str) -> models.Invoice:
        """Get single invoice with cache-aside pattern."""
        # Try cache first (if available)
        if self.cache:
            cached = self.cache.get_invoice(invoice_id)
            if cached:
                logger.info(f"Cache hit for invoice {invoice_id}")
                # For now, fall through to database for full model with relationships
                # In production, might cache relationships too
        
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
            raise InvoiceNotFoundError(invoice_id)
        
        # Populate cache
        if self.cache:
            self.cache.set_invoice(invoice)
        # Normalize timezone for paid_at in case backend (e.g., SQLite) returned naive datetime
        if invoice.paid_at is not None and invoice.paid_at.tzinfo is None:
            invoice.paid_at = invoice.paid_at.replace(tzinfo=dt.timezone.utc)
        return invoice

    def update_status(self, issuer_id: int, invoice_id: str, status: str) -> models.Invoice:
        if status not in self._allowed_statuses:
            raise InvalidInvoiceStatusError(new_status=status)
        invoice = (
            self.db.query(models.Invoice)
            .options(joinedload(models.Invoice.customer), joinedload(models.Invoice.issuer))
            .filter(models.Invoice.invoice_id == invoice_id, models.Invoice.issuer_id == issuer_id)
            .one_or_none()
        )
        if not invoice:
            raise InvoiceNotFoundError(invoice_id)
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
        
        # Invalidate cache after status update
        if self.cache:
            self.cache.invalidate_invoice(invoice_id)
            self.cache.invalidate_user_invoices(issuer_id)
        
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
        InvoiceService configured with PDF generation and optional caching
    """
    from app.services.pdf_service import PDFService
    from app.storage.s3_client import S3Client
    from app.services.cache_service import InvoiceCacheRepository
    from app.db.redis_client import get_redis_client
    from app.core.config import settings

    pdf = PDFService(S3Client())
    
    # Add cache if Redis is configured
    cache = None
    if getattr(settings, "REDIS_URL", None):
        try:
            redis_client = get_redis_client()
            cache = InvoiceCacheRepository(redis_client)
        except Exception as e:
            logger.warning(f"Failed to initialize invoice cache: {e}")
    
    return InvoiceService(db, pdf, cache=cache)

