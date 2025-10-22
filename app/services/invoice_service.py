from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends
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
    def create_invoice(self, issuer_id: int, data: dict[str, object]) -> models.Invoice:
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
        self.db.commit()
        logger.info("Created invoice %s for issuer %s", invoice.invoice_id, issuer_id)
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
