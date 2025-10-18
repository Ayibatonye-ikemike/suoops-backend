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

    def generate_invoice_pdf(self, invoice: Invoice, payment_url: str | None = None) -> str:
        """Generate PDF using HTML->PDF if enabled, else fallback to ReportLab."""
        if settings.HTML_PDF_ENABLED and _WEASY_AVAILABLE:
            try:
                html_str = self._render_invoice_html(invoice, payment_url)
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
        c.drawString(40, 760, f"Amount: {invoice.amount}")
        if payment_url:
            c.drawString(40, 740, f"Pay: {payment_url}")
        y = 700
        for line in invoice.lines:
            c.drawString(50, y, f"- {line.description} x{line.quantity} @ {line.unit_price}")
            y -= 20
        c.showPage()
        c.save()
        pdf_bytes = buffer.getvalue()
        key = f"invoices/{invoice.invoice_id}.pdf"
        url = self.s3.upload_bytes(pdf_bytes, key)
        logger.info("Uploaded fallback PDF for %s", invoice.invoice_id)
        return url

    def _render_invoice_html(self, invoice: Invoice, payment_url: str | None) -> str:
        template = self.jinja.get_template("invoice.html")
        return template.render(invoice=invoice, payment_url=payment_url)
