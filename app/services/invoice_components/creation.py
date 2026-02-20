"""Invoice creation workflow mixin."""
from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal

from sqlalchemy.orm import Session, joinedload

from app import metrics
from app.core.exceptions import MissingBankDetailsError
from app.models import models
from app.services.fiscalization_service import VATCalculator
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
        created_by_user_id: int | None = None,
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

        # ── VAT calculation (opt-in: only for VAT-registered businesses) ──
        # SuoOps calculates VAT from what the business charges — not what the law assumes.
        from app.models.tax_models import TaxProfile
        tax_profile = self.db.query(TaxProfile).filter(TaxProfile.user_id == issuer_id).first()
        is_vat_registered = tax_profile.vat_registered if tax_profile else False

        default_description = (data.get("description") or "Item").strip() or "Item"

        if is_vat_registered:
            # VAT enabled: auto-detect category from item descriptions, then calculate
            lines_data_preview = data.get("lines") or [{"description": default_description}]
            combined_desc = " ".join(ld.get("description", "") for ld in lines_data_preview)
            vat_category = data.get("vat_category") or VATCalculator.detect_category(combined_desc)

            inv_amount = Decimal(str(data.get("amount")))
            taxable_amount = inv_amount - (discount_amount or Decimal(0))
            vat_result = VATCalculator.calculate(taxable_amount, vat_category)
        else:
            # VAT OFF by default — no VAT assumptions for non-registered businesses
            vat_category = "none"
            vat_result = {"vat_rate": Decimal("0"), "vat_amount": Decimal("0")}

        # Determine initial status based on invoice type and contact info
        customer_phone = data.get("customer_phone")
        customer_email = data.get("customer_email")
        has_contact_info = bool(customer_phone or customer_email)
        
        if invoice_type == "expense":
            status = "paid"
            paid_at = dt.datetime.now(dt.timezone.utc)
        elif has_contact_info:
            # Has contact info - pending notification
            status = "pending"
            paid_at = None
        else:
            # No contact info - skip to awaiting confirmation (manual payment tracking)
            status = "awaiting_confirmation"
            paid_at = None

        # ── Professional defaults ──────────────────────────────────────
        # Auto due-date: 3 days from now for revenue invoices when client
        # doesn't specify one.  Businesses that set due dates collect faster.
        due_date = data.get("due_date")
        if due_date is None and invoice_type == "revenue":
            due_date = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=3)

        # Professional payment instruction default for revenue invoices
        notes = data.get("notes")
        if not notes and invoice_type == "revenue":
            notes = "Payment is due by the date shown above. Thank you for your business."

        invoice = models.Invoice(
            invoice_id=generate_id("INV" if invoice_type == "revenue" else "EXP"),
            issuer_id=issuer_id,
            created_by_user_id=created_by_user_id or issuer_id,  # Track actual creator
            customer=customer,
            amount=Decimal(str(data.get("amount"))),
            discount_amount=discount_amount,
            due_date=due_date,
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
            notes=notes,
            vat_rate=float(vat_result["vat_rate"]),
            vat_amount=vat_result["vat_amount"],
            vat_category=str(vat_category),
        )

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

        # Deduct from invoice_balance for revenue invoices (new billing model)
        if invoice_type == "revenue":
            self.deduct_invoice_balance(issuer_id)

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
            # Refresh user to get updated balance
            self.db.refresh(user)
            logger.info(
                "Revenue invoice - remaining balance: %d",
                getattr(user, 'invoice_balance', 0),
            )
            metrics.invoice_created()

        if self.cache:
            self.cache.invalidate_user_invoices(issuer_id)

        return invoice

    def _queue_pdf_generation(self, invoice: models.Invoice, invoice_type: str, user: models.User) -> None:
        from app.storage.s3_client import s3_client
        from app.workers.tasks import generate_invoice_pdf_async

        bank_details = None
        if invoice_type == "revenue":
            bank_details = self._ensure_bank_details(user)

        # Generate fresh presigned URL for logo
        logo_url = None
        if user.logo_url:
            logo_key = s3_client.extract_key_from_url(user.logo_url)
            if logo_key:
                logo_url = s3_client.get_presigned_url(logo_key, expires_in=3600)
            if not logo_url:
                logo_url = user.logo_url  # Fallback to stored URL

        generate_invoice_pdf_async.delay(
            invoice_id=invoice.id,
            bank_details=bank_details,
            logo_url=logo_url,
            user_plan=user.plan.value,
        )
        invoice.pdf_url = None
        logger.info("Queued async PDF generation for invoice %s", invoice.invoice_id)

    def _generate_pdf(self, invoice: models.Invoice, invoice_type: str, user: models.User) -> str | None:
        from app.storage.s3_client import s3_client
        
        bank_details = self._ensure_bank_details(user) if invoice_type == "revenue" else None
        
        # Generate fresh presigned URL for logo
        logo_url = None
        if user.logo_url:
            logo_key = s3_client.extract_key_from_url(user.logo_url)
            if logo_key:
                logo_url = s3_client.get_presigned_url(logo_key, expires_in=3600)
            if not logo_url:
                logo_url = user.logo_url  # Fallback to stored URL
        
        return self.pdf_service.generate_invoice_pdf(
            invoice,
            bank_details=bank_details,
            logo_url=logo_url,
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

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number to consistent format for storage and lookup.
        
        Supports both Nigerian and international phone numbers.
        """
        if not phone:
            return phone
        
        # If already starts with +, assume it's properly formatted international
        if phone.startswith('+'):
            return phone
        
        # Remove all non-digit characters
        digits = "".join(ch for ch in phone if ch.isdigit())
        if not digits:
            return phone
        
        # Canonicalize Nigerian numbers to +234XXXXXXXXXX for storage.
        # Accept: +2348012345678, 2348012345678, 08012345678, 8012345678
        if digits.startswith("234") and len(digits) == 13:
            return "+" + digits
        if digits.startswith("0") and len(digits) == 11 and digits[1] in "789":
            return "+234" + digits[1:]
        if len(digits) == 10 and digits[0] in "789":
            return "+234" + digits
        
        # For other international numbers, add + prefix if needed
        # This handles cases like "14155551234" → "+14155551234"
        if len(digits) >= 7:
            return "+" + digits
        
        # For very short numbers, keep original input
        return phone

    def _get_or_create_customer(
        self, name: str, phone: str | None, email: str | None = None
    ) -> models.Customer:
        # Normalize phone for consistent lookup/storage
        normalized_phone = self._normalize_phone(phone) if phone else None
        
        # Build phone candidates for lookup (handle existing records with different formats)
        phone_candidates = set()
        if normalized_phone:
            phone_candidates.add(normalized_phone)
            # Also check legacy/local formats in case old records exist
            if normalized_phone.startswith("+234") and len(normalized_phone) == 14:
                digits_only = normalized_phone[1:]
                phone_candidates.add(digits_only)  # 234XXXXXXXXXX
                phone_candidates.add("0" + digits_only[3:])  # 0XXXXXXXXXX
            phone_candidates.add(phone)  # Original input too
        
        q = self.db.query(models.Customer).filter(models.Customer.name == name)
        if phone_candidates:
            q = q.filter(models.Customer.phone.in_(list(phone_candidates)))
        elif email:
            q = q.filter(models.Customer.email == email)
        else:
            # No phone or email provided - look for customer with same name AND no contact info
            # This prevents matching an existing customer with a different phone/email
            q = q.filter(models.Customer.phone.is_(None), models.Customer.email.is_(None))
        existing = q.first()
        if existing:
            if email and not existing.email:
                existing.email = email
            # Update phone to normalized format if different
            if normalized_phone and existing.phone != normalized_phone:
                existing.phone = normalized_phone
            return existing
        customer = models.Customer(name=name, phone=normalized_phone, email=email)
        self.db.add(customer)
        self.db.flush()
        return customer
