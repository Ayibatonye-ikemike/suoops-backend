"""Invoice creation workflow mixin."""
from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal

from sqlalchemy.orm import Session, joinedload, selectinload

from app import metrics
from app.core.exceptions import MissingBankDetailsError
from app.models import models
from app.utils.id_generator import generate_id

logger = logging.getLogger(__name__)


class InvoiceCreationMixin:
    """Handles invoice creation and caching concerns."""

    db: Session

    def create_invoice(
        self,
        issuer_id: int,
        data: dict[str, object],
        async_pdf: bool = False,
    ) -> models.Invoice:
        invoice_type = data.get("invoice_type", "revenue")
        self.enforce_quota(issuer_id, invoice_type)

        if invoice_type == "revenue":
            customer = self._get_or_create_customer(
                data.get("customer_name"),
                data.get("customer_phone"),
                data.get("customer_email"),
            )
        else:
            vendor_name = data.get("vendor_name") or data.get("merchant") or "Expense Vendor"
            customer = self._get_or_create_customer(vendor_name, None, None)

        discount_raw = data.get("discount_amount")
        discount_amount = Decimal(str(discount_raw)) if discount_raw else None
        status = "paid" if invoice_type == "expense" else "pending"
        paid_at = dt.datetime.now(dt.timezone.utc) if invoice_type == "expense" else None

        invoice = models.Invoice(
            invoice_id=generate_id("INV" if invoice_type == "revenue" else "EXP"),
            issuer_id=issuer_id,
            customer=customer,
            amount=Decimal(str(data.get("amount"))),
            discount_amount=discount_amount,
            due_date=data.get("due_date"),
            status=status,
            paid_at=paid_at,
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

        default_description = (data.get("description") or "Item").strip() or "Item"
        lines_data = data.get("lines") or [
            {"description": default_description, "quantity": 1, "unit_price": invoice.amount}
        ]
        for line_data in lines_data:
            description = (line_data.get("description") or default_description).strip() or default_description
            invoice.lines.append(
                models.InvoiceLine(
                    description=description,
                    quantity=line_data.get("quantity", 1),
                    unit_price=Decimal(str(line_data["unit_price"])),
                    product_id=line_data.get("product_id"),  # Link to inventory product
                )
            )

        self.db.add(invoice)
        self.db.commit()
        self.db.refresh(invoice)

        # Process inventory updates ONLY for expense invoices at creation time
        # Revenue invoices have inventory deducted when marked as PAID (see status.py)
        # This ensures proper workflow: Invoice Created -> Payment Received -> Stock Deducted
        if invoice_type == "expense" and hasattr(self, 'process_inventory_for_invoice'):
            self.process_inventory_for_invoice(invoice, lines_data)

        if self.cache:
            self.cache.invalidate_user_invoices(issuer_id)

        user = self.db.query(models.User).filter(models.User.id == issuer_id).one()
        metrics.invoice_created_by_plan(user.plan.value)
        total_amount = sum(float(line.unit_price) * line.quantity for line in invoice.lines)
        metrics.record_invoice_amount(total_amount)

        if async_pdf:
            self._queue_pdf_generation(invoice, invoice_type, user)
        else:
            invoice.pdf_url = self._generate_pdf(invoice, invoice_type, user)

        if invoice_type == "revenue":
            user.invoices_this_month += 1

        self.db.commit()
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

        logger.info(
            "Created %s invoice %s for issuer %s",
            invoice_type,
            invoice.invoice_id,
            issuer_id,
        )
        if invoice_type == "revenue":
            logger.info(
                "Revenue invoice usage: %s/%s",
                user.invoices_this_month,
                user.plan.invoice_limit or "unlimited",
            )
            metrics.invoice_created()

        if self.cache:
            self.cache.invalidate_user_invoices(issuer_id)

        return invoice

    def _queue_pdf_generation(self, invoice: models.Invoice, invoice_type: str, user: models.User) -> None:
        from app.workers.tasks import generate_invoice_pdf_async

        bank_details = None
        if invoice_type == "revenue":
            bank_details = self._ensure_bank_details(user)

        generate_invoice_pdf_async.delay(
            invoice_id=invoice.id,
            bank_details=bank_details,
            logo_url=user.logo_url,
            user_plan=user.plan.value,
        )
        invoice.pdf_url = None
        logger.info("Queued async PDF generation for invoice %s", invoice.invoice_id)

    def _generate_pdf(self, invoice: models.Invoice, invoice_type: str, user: models.User) -> str | None:
        bank_details = self._ensure_bank_details(user) if invoice_type == "revenue" else None
        return self.pdf_service.generate_invoice_pdf(
            invoice,
            bank_details=bank_details,
            logo_url=user.logo_url,
            user_plan=user.plan.value,
        )

    def _ensure_bank_details(self, user: models.User) -> dict[str, str]:
        if not user.bank_name or not user.account_number:
            raise MissingBankDetailsError()
        return {
            "bank_name": user.bank_name,
            "account_number": user.account_number,
            "account_name": user.account_name,
        }

    def _get_or_create_customer(
        self, name: str, phone: str | None, email: str | None = None
    ) -> models.Customer:
        q = self.db.query(models.Customer).filter(models.Customer.name == name)
        if phone:
            q = q.filter(models.Customer.phone == phone)
        elif email:
            q = q.filter(models.Customer.email == email)
        existing = q.first()
        if existing:
            if email and not existing.email:
                existing.email = email
            return existing
        customer = models.Customer(name=name, phone=phone, email=email)
        self.db.add(customer)
        self.db.flush()
        return customer
