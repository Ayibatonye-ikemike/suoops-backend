from __future__ import annotations

import logging
from io import BytesIO

from jinja2 import Environment, FileSystemLoader, select_autoescape
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.core.config import settings
from app.models.models import Invoice

try:
    from weasyprint import HTML  # type: ignore
    _WEASY_AVAILABLE = True
except Exception:  # noqa: BLE001
    _WEASY_AVAILABLE = False

logger = logging.getLogger(__name__)


class PDFService:
    def __init__(self, s3_client):
        self.s3 = s3_client
        self.jinja = Environment(
            loader=FileSystemLoader("templates"),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def generate_invoice_pdf(self, invoice: Invoice, bank_details: dict | None = None, logo_url: str | None = None) -> str:
        """Generate PDF with bank transfer payment instructions and business logo.
        
        Args:
            invoice: Invoice model instance
            bank_details: Dict with bank_name, account_number, account_name
            logo_url: URL to business logo image
            
        Returns:
            URL or path to generated PDF
        """
        if settings.HTML_PDF_ENABLED and _WEASY_AVAILABLE:
            try:
                html_str = self._render_invoice_html(invoice, bank_details, logo_url)
                pdf_bytes = HTML(string=html_str).write_pdf()  # type: ignore
                key = f"invoices/{invoice.invoice_id}.pdf"
                url = self.s3.upload_bytes(pdf_bytes, key)
                logger.info("Uploaded HTML PDF for %s", invoice.invoice_id)
                return url
            except Exception as e:  # noqa: BLE001
                logger.warning("HTML PDF generation failed (%s); falling back to ReportLab", e)
        # fallback path
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(40, 800, f"Invoice {invoice.invoice_id}")
        c.setFont("Helvetica", 12)
        c.drawString(40, 780, f"Customer: {invoice.customer.name}")
        c.drawString(40, 760, f"Amount: ₦{invoice.amount:,.2f}")
        
        # Add bank transfer details
        if bank_details:
            y = 720
            c.setFont("Helvetica-Bold", 12)
            c.drawString(40, y, "Payment Details (Bank Transfer):")
            c.setFont("Helvetica", 10)
            y -= 20
            if bank_details.get("bank_name"):
                c.drawString(50, y, f"Bank: {bank_details['bank_name']}")
                y -= 15
            if bank_details.get("account_number"):
                c.drawString(50, y, f"Account Number: {bank_details['account_number']}")
                y -= 15
            if bank_details.get("account_name"):
                c.drawString(50, y, f"Account Name: {bank_details['account_name']}")
                y -= 20
        else:
            y = 720
            
        # Invoice lines
        c.setFont("Helvetica-Bold", 12)
        y -= 10
        c.drawString(40, y, "Items:")
        c.setFont("Helvetica", 10)
        y -= 20
        for line in invoice.lines:
            c.drawString(50, y, f"- {line.description} x{line.quantity} @ ₦{line.unit_price:,.2f}")
            y -= 20
        c.showPage()
        c.save()
        pdf_bytes = buffer.getvalue()
        key = f"invoices/{invoice.invoice_id}.pdf"
        url = self.s3.upload_bytes(pdf_bytes, key)
        logger.info("Uploaded fallback PDF for %s", invoice.invoice_id)
        return url

    def _render_invoice_html(self, invoice: Invoice, bank_details: dict | None, logo_url: str | None = None) -> str:
        """Render invoice HTML template with bank transfer details and business logo."""
        template = self.jinja.get_template("invoice.html")
        return template.render(invoice=invoice, bank_details=bank_details, logo_url=logo_url)
