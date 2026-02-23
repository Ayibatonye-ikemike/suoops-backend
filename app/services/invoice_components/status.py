"""Status update and public retrieval helpers."""
from __future__ import annotations

import asyncio
import datetime as dt
import logging

from sqlalchemy.orm import Session, joinedload, selectinload

from app import metrics
from app.core.exceptions import InvalidInvoiceStatusError, InvoiceNotFoundError
from app.models import models

logger = logging.getLogger(__name__)


class InvoiceStatusMixin:
    db: Session

    def update_status(
        self,
        issuer_id: int,
        invoice_id: str,
        status: str,
        updated_by_user_id: int | None = None,
    ) -> models.Invoice:
        if status not in {"pending", "awaiting_confirmation", "paid", "cancelled"}:
            raise InvalidInvoiceStatusError(new_status=status)

        invoice = (
            self.db.query(models.Invoice)
            .options(
                joinedload(models.Invoice.customer),
                joinedload(models.Invoice.issuer),
                joinedload(models.Invoice.created_by),  # Load creator for PDF
                joinedload(models.Invoice.status_updated_by),  # Load confirmer for PDF
                selectinload(models.Invoice.lines),  # Load lines for inventory processing
            )
            .filter(models.Invoice.invoice_id == invoice_id, models.Invoice.issuer_id == issuer_id)
            .one_or_none()
        )
        if not invoice:
            raise InvoiceNotFoundError(invoice_id)

        previous_status = invoice.status
        if previous_status == status:
            return invoice

        # ── Invoice status state machine ─────────────────────────────
        # pending             → awaiting_confirmation, paid, cancelled
        # awaiting_confirmation → pending, paid, cancelled
        # paid                → (terminal — no further changes)
        # cancelled           → pending (re-open only)
        _VALID_TRANSITIONS: dict[str, set[str]] = {
            "pending": {"awaiting_confirmation", "paid", "cancelled"},
            "awaiting_confirmation": {"pending", "paid", "cancelled"},
            "paid": set(),  # terminal state
            "cancelled": {"pending"},  # can only re-open
        }

        allowed = _VALID_TRANSITIONS.get(previous_status, set())
        if status not in allowed:
            raise ValueError(
                f"Cannot change invoice from '{previous_status}' to '{status}'"
            )

        invoice.status = status
        
        # Track who updated the status and when
        if updated_by_user_id and status in {"paid", "cancelled"}:
            invoice.status_updated_by_user_id = updated_by_user_id
            invoice.status_updated_at = dt.datetime.now(dt.timezone.utc)
        
        if status == "paid" and invoice.paid_at is None:
            invoice.paid_at = dt.datetime.now(dt.timezone.utc)
        self.db.commit()

        if invoice.paid_at and invoice.paid_at.tzinfo is None:
            invoice.paid_at = invoice.paid_at.replace(tzinfo=dt.timezone.utc)
            self.db.commit()

        if status == "paid" and previous_status != "paid":
            # Refresh invoice to load updated relationships (created_by, status_updated_by)
            self.db.refresh(invoice)
            # Explicitly load the status_updated_by relationship if we just set it
            if invoice.status_updated_by_user_id and not invoice.status_updated_by:
                invoice = (
                    self.db.query(models.Invoice)
                    .options(
                        joinedload(models.Invoice.customer),
                        joinedload(models.Invoice.issuer),  # Load issuer for logo/business name
                        joinedload(models.Invoice.created_by),
                        joinedload(models.Invoice.status_updated_by),
                        selectinload(models.Invoice.lines),
                    )
                    .filter(models.Invoice.invoice_id == invoice_id)
                    .one()
                )
            self._handle_manual_payment(invoice)

        if self.cache:
            self.cache.invalidate_invoice(invoice_id)
            self.cache.invalidate_user_invoices(issuer_id)

        return self.get_invoice(issuer_id, invoice_id)

    def confirm_transfer(self, invoice_id: str) -> models.Invoice:
        invoice = (
            self.db.query(models.Invoice)
            .options(selectinload(models.Invoice.customer))
            .filter(models.Invoice.invoice_id == invoice_id)
            .one_or_none()
        )
        if not invoice:
            raise ValueError("Invoice not found")

        if invoice.status in {"paid", "awaiting_confirmation"}:
            return invoice

        previous_status = invoice.status
        invoice.status = "awaiting_confirmation"
        self.db.commit()
        logger.info(
            "Invoice %s status transitioned %s → awaiting_confirmation after customer confirmation",
            invoice_id,
            previous_status,
        )
        self._notify_business_of_transfer(invoice)
        return invoice

    def get_public_invoice(self, invoice_id: str) -> tuple[models.Invoice, models.User]:
        invoice = (
            self.db.query(models.Invoice)
            .options(selectinload(models.Invoice.customer), selectinload(models.Invoice.lines))
            .filter(models.Invoice.invoice_id == invoice_id)
            .one_or_none()
        )
        if not invoice:
            raise ValueError("Invoice not found")

        issuer = self.db.query(models.User).filter(models.User.id == invoice.issuer_id).one_or_none()
        if not issuer:
            raise ValueError("Invoice issuer not found")
        return invoice, issuer

    def _handle_manual_payment(self, invoice: models.Invoice) -> None:
        metrics.invoice_paid()
        
        # Capture invoice_id early to avoid DB access issues after potential errors
        invoice_id = invoice.invoice_id
        
        # Process inventory deduction for revenue invoices when paid
        self._process_inventory_on_payment(invoice)
        
        # Generate receipt PDF first
        try:
            if not invoice.receipt_pdf_url:
                invoice.receipt_pdf_url = self.pdf_service.generate_receipt_pdf(invoice)
                self.db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to generate receipt PDF for %s: %s", invoice_id, exc)

        # Send receipt notification (do this BEFORE low stock check to ensure receipt is sent)
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
                "Receipt sent for invoice %s - Email: %s, WhatsApp: %s",
                invoice_id,
                results["email"],
                results["whatsapp"],
            )
            
            # If no customer contact info, notify business with receipt PDF via WhatsApp
            if not customer_email and not customer_phone:
                self._notify_business_with_receipt(invoice)
                
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send receipt notifications for %s: %s", invoice_id, exc)
        
        # Check for low stock and send alerts (non-critical, done after receipt is sent)
        self._check_and_send_low_stock_alerts(invoice)

    def _notify_business_of_transfer(self, invoice: models.Invoice) -> None:
        try:
            user = self.db.query(models.User).filter(models.User.id == invoice.issuer_id).one_or_none()
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load issuer for invoice %s: %s", invoice.invoice_id, exc)
            return

        if not user:
            logger.warning("Cannot notify business for invoice %s: issuer missing", invoice.invoice_id)
            return

        from app.core.config import settings
        frontend_url = getattr(settings, "FRONTEND_URL", "https://suoops.com")
        verify_link = f"{frontend_url.rstrip('/')}/dashboard/invoices/{invoice.invoice_id}"

        customer_name = invoice.customer.name if invoice.customer else "Customer"
        message = (
            f"💰 Payment Notification!\n\n"
            f"Customer reported a bank transfer for:\n\n"
            f"📄 Invoice: {invoice.invoice_id}\n"
            f"💵 Amount: ₦{invoice.amount:,.2f}\n"
            f"👤 Customer: {customer_name}\n\n"
            f"🔗 Verify & Mark as Paid:\n{verify_link}\n\n"
            f"✅ Please verify the funds in your bank account "
            f"and mark the invoice as PAID to send the customer their receipt."
        )

        try:
            from app.services.notification.service import NotificationService

            service = NotificationService()

            async def _run():  # pragma: no cover - network IO
                results = {"email": False, "whatsapp": False}
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
                        # Send WhatsApp notification to business
                        from app.bot.whatsapp_client import WhatsAppClient
                        from app.core.config import settings
                        whatsapp_key = getattr(settings, "WHATSAPP_API_KEY", None)
                        if whatsapp_key:
                            client = WhatsAppClient(whatsapp_key)
                            frontend_url = getattr(settings, "FRONTEND_URL", "https://suoops.com")
                            verify_link = f"{frontend_url.rstrip('/')}/dashboard/invoices/{invoice.invoice_id}"
                            whatsapp_message = (
                                f"💰 Payment Notification!\n\n"
                                f"Customer reported a bank transfer for:\n\n"
                                f"📄 Invoice: {invoice.invoice_id}\n"
                                f"💵 Amount: ₦{invoice.amount:,.2f}\n"
                            )
                            if invoice.customer:
                                whatsapp_message += f"👤 Customer: {invoice.customer.name}\n"
                            whatsapp_message += (
                                f"\n🔗 Verify & Mark as Paid:\n{verify_link}\n\n"
                                f"✅ Please verify the funds in your bank account "
                                f"and mark the invoice as PAID to send the customer their receipt.\n\n"
                                f"💡 _Tip: If link doesn't load, long-press and select 'Open in Browser'_"
                            )
                            client.send_text(user.phone, whatsapp_message)
                            results["whatsapp"] = True
                    except Exception as exc:  # noqa: BLE001
                        logger.error("Failed WhatsApp notify business %s: %s", invoice.invoice_id, exc)
                logger.info(
                    "Business notification for invoice %s - Email: %s, WhatsApp: %s",
                    invoice.invoice_id,
                    results["email"],
                    results["whatsapp"],
                )

            asyncio.run(_run())
        except Exception as exc:  # noqa: BLE001
            logger.error("Notification dispatch failed for invoice %s: %s", invoice.invoice_id, exc)

    def _notify_business_with_receipt(self, invoice: models.Invoice) -> None:
        """
        Notify the business owner with the receipt PDF via WhatsApp.
        
        This is called when an invoice is marked as paid but has no customer
        contact info (no email/phone). In this case, the business needs the
        receipt PDF to give to the customer manually.
        """
        if not invoice.issuer:
            logger.warning("No issuer found for invoice %s", invoice.invoice_id)
            return
            
        user = invoice.issuer
        if not user.phone:
            logger.warning("Business %s has no phone for receipt notification", user.id)
            return
            
        try:
            from app.bot.whatsapp_client import WhatsAppClient
            from app.core.config import settings
            
            whatsapp_key = getattr(settings, "WHATSAPP_API_KEY", None)
            if not whatsapp_key:
                logger.warning("No WhatsApp API key configured for receipt notification")
                return
                
            client = WhatsAppClient(whatsapp_key)
            
            customer_name = invoice.customer.name if invoice.customer else "Customer"
            
            receipt_message = (
                f"✅ Invoice Paid!\n\n"
                f"📄 Invoice: {invoice.invoice_id}\n"
                f"💵 Amount: ₦{invoice.amount:,.2f}\n"
                f"👤 Customer: {customer_name}\n\n"
                f"Share this receipt with your customer."
            )
            
            client.send_text(user.phone, receipt_message)
            
            # Send receipt PDF as document (better UX than URL link)
            if invoice.pdf_url and invoice.pdf_url.startswith("http"):
                client.send_document(
                    user.phone,
                    invoice.pdf_url,
                    f"Receipt_{invoice.invoice_id}.pdf",
                    f"🧾 Receipt for {customer_name} - ₦{invoice.amount:,.2f}",
                )
                
            logger.info("Receipt PDF sent to business %s for invoice %s", user.id, invoice.invoice_id)
            
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send receipt to business %s: %s", invoice.invoice_id, exc)

    def _process_inventory_on_payment(self, invoice: models.Invoice) -> None:
        """
        Process inventory deduction when a revenue invoice is marked as paid.
        
        This is the key automation point:
        - Deducts stock for all line items linked to products
        - Records stock movements for audit trail
        - Updates COGS for tax reporting
        
        For expense invoices, inventory is added at creation time (purchases).
        For revenue invoices, inventory is deducted at payment time (sales).
        """
        if invoice.invoice_type != "revenue":
            return  # Only process revenue invoices on payment
        
        try:
            from decimal import Decimal

            from app.services.inventory import build_inventory_service
            
            # Check if any lines have products linked
            has_inventory_items = any(
                line.product_id for line in invoice.lines
            )
            if not has_inventory_items:
                return
            
            inventory_service = build_inventory_service(self.db, invoice.issuer_id)
            
            # Process each line item
            for line in invoice.lines:
                if not line.product_id:
                    continue
                    
                try:
                    inventory_service.record_sale(
                        product_id=line.product_id,
                        quantity=line.quantity,
                        unit_price=Decimal(str(line.unit_price)),
                        invoice_line_id=line.id,
                        reference_id=invoice.invoice_id,
                    )
                    logger.info(
                        f"Stock deducted for product {line.product_id}: "
                        f"{line.quantity} units via invoice {invoice.invoice_id}"
                    )
                except ValueError as e:
                    # Log insufficient stock but don't block payment
                    logger.warning(
                        "Insufficient stock for product %s on invoice %s: %s",
                        line.product_id,
                        invoice.invoice_id,
                        e,
                    )
                    
        except Exception as e:
            logger.error("Inventory processing failed for invoice %s: %s", invoice.invoice_id, e)

    def _check_and_send_low_stock_alerts(self, invoice: models.Invoice) -> None:
        """
        Check for low stock items after a sale and send alerts.
        
        This implements the alert workflow:
        - After inventory is deducted, check all affected products
        - If any product is at or below reorder level, send alert
        - Optionally generate draft purchase order suggestions
        """
        if invoice.invoice_type != "revenue":
            return
        
        # Capture values upfront to avoid DB access after potential errors
        invoice_id = invoice.invoice_id
        issuer_id = invoice.issuer_id
        
        try:
            from app.models.inventory_models import Product
            
            # Get products that were just affected
            affected_product_ids = [
                line.product_id for line in invoice.lines 
                if line.product_id
            ]
            
            if not affected_product_ids:
                return
            
            # Check which products are now low stock
            low_stock_products = self.db.query(Product).filter(
                Product.id.in_(affected_product_ids),
                Product.track_stock.is_(True),
                Product.quantity_in_stock <= Product.reorder_level,
            ).all()
            
            if not low_stock_products:
                return
            
            # Build alert message
            alert_items = []
            for product in low_stock_products:
                status = "OUT OF STOCK" if product.quantity_in_stock <= 0 else "LOW STOCK"
                alert_items.append(
                    f"• {product.name} ({product.sku}): {product.quantity_in_stock} {product.unit} "
                    f"[Reorder: {product.reorder_quantity}] - {status}"
                )
            
            # Generate draft purchase order for low stock products
            # Note: This may fail if purchase_order table doesn't exist yet - that's OK
            purchase_order = None
            try:
                from app.services.inventory import build_inventory_service
                inventory_service = build_inventory_service(self.db, issuer_id)
                product_ids = [p.id for p in low_stock_products]
                purchase_order = inventory_service.generate_draft_purchase_order(
                    product_ids=product_ids,
                    trigger_invoice_id=invoice_id,
                )
                if purchase_order:
                    logger.info(
                        "Draft purchase order %s generated for %s low stock products",
                        purchase_order.order_number,
                        len(low_stock_products),
                    )
            except Exception as e:
                # Rollback to clear any pending rollback state from failed PO creation
                self.db.rollback()
                logger.warning("Could not generate purchase order: %s", e)
            
            po_message = ""
            if purchase_order:
                po_message = f"\n\n📋 Draft Purchase Order #{purchase_order.id} has been created for your review."
            
            message = (
                f"⚠️ Stock Alert after Invoice {invoice_id}\n\n"
                f"The following products need reordering:\n\n"
                + "\n".join(alert_items)
                + po_message
                + "\n\nPlease review and place orders with suppliers."
            )
            
            # Send notification to business owner
            po_id = purchase_order.id if purchase_order else None
            self._send_low_stock_notification(issuer_id, message, low_stock_products, po_id)
            
            logger.info(
                "Low stock alert sent for %s products after invoice %s",
                len(low_stock_products),
                invoice_id,
            )
            
        except Exception as e:
            # Rollback to prevent cascading errors
            try:
                self.db.rollback()
            except Exception:
                pass
            logger.error("Low stock check failed for invoice %s: %s", invoice_id, e)

    def _send_low_stock_notification(
        self, 
        user_id: int, 
        message: str, 
        products: list,
        purchase_order_id: int | None = None
    ) -> None:
        """Send low stock alert to business owner via email and WhatsApp."""
        try:
            user = self.db.query(models.User).filter(models.User.id == user_id).one_or_none()
            if not user:
                return
            
            from app.services.notification.service import NotificationService
            
            service = NotificationService()
            
            po_suffix = f" - PO #{purchase_order_id}" if purchase_order_id else ""
            
            async def _run():
                if user.email:
                    try:
                        await service.send_email(
                            to_email=user.email,
                            subject=f"⚠️ Low Stock Alert - {len(products)} products need reordering{po_suffix}",
                            body=message,
                        )
                    except Exception as exc:
                        logger.error("Failed to send low stock email: %s", exc)
            
            asyncio.run(_run())

            # Also send WhatsApp template if configured
            from app.core.config import settings as _settings

            template_name = _settings.WHATSAPP_TEMPLATE_LOW_STOCK_ALERT
            if template_name and user.phone:
                try:
                    from app.bot.whatsapp_client import WhatsAppClient

                    client = WhatsAppClient(_settings.WHATSAPP_API_KEY)
                    user_name = user.name.split()[0] if user.name else "there"
                    lang = _settings.WHATSAPP_TEMPLATE_LANGUAGE or "en"
                    components = [
                        {
                            "type": "body",
                            "parameters": [
                                {"type": "text", "text": user_name},
                                {"type": "text", "text": str(len(products))},
                            ],
                        }
                    ]
                    client.send_template(user.phone, template_name, lang, components)
                except Exception as exc:
                    logger.error("Failed to send low stock WhatsApp: %s", exc)
            
        except Exception as e:
            logger.error("Low stock notification failed: %s", e)

