from __future__ import annotations

import base64
import logging
from io import BytesIO
from typing import TYPE_CHECKING

import qrcode
from jinja2 import Environment, FileSystemLoader, select_autoescape
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.core.config import settings
from app.models.models import Invoice

if TYPE_CHECKING:  # pragma: no cover - for type hints only
    from app.models.tax_models import MonthlyTaxReport

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

    def generate_invoice_pdf(
        self,
        invoice: Invoice,
        bank_details: dict | None = None,
        logo_url: str | None = None,
        user_plan: str = "free",  # Default to free plan
    ) -> str:
        """Generate PDF with bank transfer payment instructions and business logo.
        
        Args:
            invoice: Invoice model instance
            bank_details: Dict with bank_name, account_number, account_name
            logo_url: URL to business logo image
            user_plan: User's subscription plan (free/starter/pro/business)
            
        Returns:
            URL or path to generated PDF
        """
        customer_portal_url = self._build_customer_portal_url(invoice.invoice_id)
        qr_code_data = self._generate_qr_code(invoice.invoice_id)

        if settings.HTML_PDF_ENABLED and _WEASY_AVAILABLE:
            try:
                html_str = self._render_invoice_html(
                    invoice,
                    bank_details,
                    logo_url,
                    customer_portal_url,
                    qr_code_data,
                    user_plan,  # Pass plan to template
                )
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

        c.setFont("Helvetica", 10)
        c.drawString(40, y, "After transferring, let us know here:")
        y -= 15
        c.setFillColorRGB(0, 0, 0.6)
        c.drawString(40, y, customer_portal_url)
        c.setFillColorRGB(0, 0, 0)
        y -= 25
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

    def generate_receipt_pdf(self, invoice: Invoice) -> str:
        """Generate a payment receipt PDF with PAID watermark.

        Uses HTML template if available (receipt.html), otherwise
        falls back to a minimal ReportLab layout with diagonal PAID watermark.
        """
        paid_at_display = None
        if getattr(invoice, "paid_at", None):
            try:
                paid_at_display = invoice.paid_at.strftime("%B %d, %Y %H:%M UTC")
            except Exception:  # noqa: BLE001
                paid_at_display = str(invoice.paid_at)
        else:
            paid_at_display = "(time not recorded)"

        # Generate QR code for receipt verification
        qr_code_data = self._generate_qr_code(invoice.invoice_id)
        
        if settings.HTML_PDF_ENABLED and _WEASY_AVAILABLE:
            try:
                # If a dedicated receipt template exists use it; otherwise reuse invoice.html
                template_name = "receipt.html"
                try:
                    template = self.jinja.get_template(template_name)
                except Exception:  # noqa: BLE001
                    template = self.jinja.get_template("invoice.html")
                watermark_text = "PAID"  # force PAID watermark on receipt
                
                # Get creator name if available
                created_by_name = None
                if hasattr(invoice, 'created_by') and invoice.created_by:
                    created_by_name = invoice.created_by.name
                
                # Get confirmer name if available
                confirmed_by_name = None
                if hasattr(invoice, 'status_updated_by') and invoice.status_updated_by:
                    confirmed_by_name = invoice.status_updated_by.name
                
                html_str = template.render(
                    invoice=invoice,
                    bank_details=None,
                    logo_url=None,
                    customer_portal_url=None,
                    qr_code=qr_code_data,
                    watermark_text=watermark_text,
                    paid_at_display=paid_at_display,
                    is_receipt=True,
                    created_by_name=created_by_name,
                    confirmed_by_name=confirmed_by_name,
                )
                from weasyprint import HTML  # type: ignore
                pdf_bytes = HTML(string=html_str).write_pdf()  # type: ignore
                key = f"receipts/{invoice.invoice_id}.pdf"
                url = self.s3.upload_bytes(pdf_bytes, key)
                logger.info("Uploaded receipt HTML PDF for %s", invoice.invoice_id)
                return url
            except Exception as e:  # noqa: BLE001
                logger.warning("Receipt HTML generation failed (%s); using fallback", e)

        # Fallback ReportLab rendering
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(40, 800, f"Payment Receipt {invoice.invoice_id}")
        c.setFont("Helvetica", 11)
        y = 775
        c.drawString(40, y, f"Customer: {getattr(invoice.customer, 'name', 'Customer')}")
        y -= 15
        c.drawString(40, y, f"Amount Paid: ₦{invoice.amount:,.2f}")
        y -= 15
        c.drawString(40, y, "Status: PAID")
        y -= 15
        c.drawString(40, y, f"Payment Date: {paid_at_display}")
        y -= 15
        
        # Add creator and confirmer info
        if hasattr(invoice, 'created_by') and invoice.created_by:
            c.drawString(40, y, f"Invoice Created by: {invoice.created_by.name}")
            y -= 15
        if hasattr(invoice, 'status_updated_by') and invoice.status_updated_by:
            c.drawString(40, y, f"Payment Confirmed by: {invoice.status_updated_by.name}")
            y -= 15
        
        y -= 10
        c.setFont("Helvetica", 9)
        c.drawString(
            40,
            y,
            "Thank you for your payment. This receipt confirms full settlement of this invoice.",
        )
        # PAID watermark
        c.saveState()
        c.setFont("Helvetica-Bold", 70)
        c.setFillColorRGB(0.0, 0.6, 0.2)  # solid color (ReportLab lacks alpha pre 3.0)
        c.translate(300, 400)
        c.rotate(30)
        c.drawString(-160, 0, "PAID")
        c.restoreState()
        c.showPage()
        c.save()
        pdf_bytes = buf.getvalue()
        key = f"receipts/{invoice.invoice_id}.pdf"
        url = self.s3.upload_bytes(pdf_bytes, key)
        logger.info("Uploaded fallback receipt PDF for %s", invoice.invoice_id)
        return url

    def _render_invoice_html(
        self,
        invoice: Invoice,
        bank_details: dict | None,
        logo_url: str | None = None,
        customer_portal_url: str | None = None,
        qr_code_data: str | None = None,
        user_plan: str = "free",
    ) -> str:
        """Render invoice HTML template with bank transfer details and business logo."""
        # Use expense template for expense invoices
        template_name = "expense_invoice.html" if invoice.invoice_type == "expense" else "invoice.html"
        template = self.jinja.get_template(template_name)
        watermark_text = (
            settings.PDF_WATERMARK_TEXT
            if getattr(settings, "PDF_WATERMARK_ENABLED", False)
            else None
        )
        
        # Fetch and encode receipt image for expense invoices
        receipt_data_url = None
        if invoice.invoice_type == "expense" and invoice.receipt_url:
            receipt_data_url = self._fetch_receipt_as_data_url(invoice.receipt_url)
        
        # Check if user is eligible for VAT tracking (BUSINESS plan only)
        is_vat_eligible = user_plan.lower() == "business"
        
        # Get creator name if available
        created_by_name = None
        if hasattr(invoice, 'created_by') and invoice.created_by:
            created_by_name = invoice.created_by.name
        
        return template.render(
            invoice=invoice,
            bank_details=bank_details,
            logo_url=logo_url,
            customer_portal_url=customer_portal_url,
            qr_code=qr_code_data,
            watermark_text=watermark_text,
            receipt_data_url=receipt_data_url,
            user_plan=user_plan.lower(),
            is_vat_eligible=is_vat_eligible,
            created_by_name=created_by_name,
        )

    # ---------------- Monthly Tax Report PDF -----------------
    def generate_monthly_tax_report_pdf(
        self,
        report: MonthlyTaxReport,  # forward reference resolved under TYPE_CHECKING
        basis: str,
    ) -> str:
        """Generate monthly tax compliance PDF (levy + VAT breakdown).

        Uses HTML template if WeasyPrint enabled; else simple ReportLab fallback.
        """
        from app.models.tax_models import MonthlyTaxReport  # local import to avoid circular
        assert isinstance(report, MonthlyTaxReport)
        # Attempt HTML path first
        if settings.HTML_PDF_ENABLED and _WEASY_AVAILABLE:
            try:
                template = self.jinja.get_template("monthly_tax_report.html")
                watermark_text = (
                    settings.PDF_WATERMARK_TEXT
                    if getattr(settings, "PDF_WATERMARK_ENABLED", False)
                    else None
                )
                html_str = template.render(
                    report=report,
                    basis=basis,
                    watermark_text=watermark_text,
                )
                from weasyprint import HTML  # type: ignore
                pdf_bytes = HTML(string=html_str).write_pdf()  # type: ignore
                key = f"tax-reports/{report.user_id}/{report.year}-{report.month}.pdf"
                return self.s3.upload_bytes(pdf_bytes, key)
            except Exception as e:  # noqa: BLE001
                logger.warning("Monthly tax report HTML generation failed (%s); using fallback", e)
        # Fallback ReportLab rendering
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        c.setFont("Helvetica-Bold", 16)
        title = f"Monthly Tax Report {report.year}-{report.month:02d}"
        c.drawString(40, 800, title)
        c.setFont("Helvetica", 11)
        y = 770
        lines = [
            f"Assessable Profit: ₦{float(report.assessable_profit):,.2f}",
            f"Development Levy: ₦{float(report.levy_amount):,.2f}",
            f"VAT Collected: ₦{float(report.vat_collected):,.2f}",
            f"Taxable Sales: ₦{float(report.taxable_sales):,.2f}",
            f"Zero-rated Sales: ₦{float(report.zero_rated_sales):,.2f}",
            f"Exempt Sales: ₦{float(report.exempt_sales):,.2f}",
            f"Profit Basis: {basis}",
        ]
        for line in lines:
            c.drawString(40, y, line)
            y -= 18
        # Watermark (diagonal) if enabled
        if getattr(settings, "PDF_WATERMARK_ENABLED", False):
            c.saveState()
            c.setFont("Helvetica", 60)
            # Simulate lighter watermark by using a mid-tone color; alpha unsupported
            c.setFillColorRGB(0.7, 0.85, 1.0) if hasattr(c, 'setFillColorRGB') else None
            c.translate(300, 400)
            c.rotate(30)
            c.drawString(-200, 0, settings.PDF_WATERMARK_TEXT[:30])
            c.restoreState()
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(
            40,
            y - 10,
            "Generated by Suoops tax automation module (refunded invoices excluded)",
        )
        c.showPage()
        c.save()
        pdf_bytes = buf.getvalue()
        key = f"tax-reports/{report.user_id}/{report.year}-{report.month}.pdf"
        return self.s3.upload_bytes(pdf_bytes, key)

    def _build_customer_portal_url(self, invoice_id: str) -> str:
        base = settings.FRONTEND_URL.rstrip("/")
        return f"{base}/pay/{invoice_id}"

    def _generate_qr_code(self, invoice_id: str) -> str:
        """Generate QR code as base64 data URI for verification URL.
        
        Args:
            invoice_id: Invoice ID to encode in QR code
            
        Returns:
            Base64 encoded QR code image as data URI
        """
        # Generate verification URL
        api_base = settings.BACKEND_URL.rstrip("/")
        verify_url = f"{api_base}/invoices/{invoice_id}/verify"
        
        # Create QR code
        qr = qrcode.QRCode(
            version=1,  # Size of QR code (1-40, 1 is smallest)
            error_correction=qrcode.constants.ERROR_CORRECT_M,  # ~15% error correction
            box_size=10,  # Size of each box in pixels
            border=2,  # Border size in boxes
        )
        qr.add_data(verify_url)
        qr.make(fit=True)
        
        # Generate image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64 data URI
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        return f"data:image/png;base64,{img_base64}"

    def _fetch_receipt_as_data_url(self, receipt_url: str) -> str | None:
        """Fetch receipt image from S3 and convert to base64 data URL.
        
        Args:
            receipt_url: S3 URL of the receipt image
            
        Returns:
            Base64 encoded image as data URI, or None if fetch fails
        """
        try:
            import requests
            import mimetypes
            
            # Fetch the image from S3 with timeout
            response = requests.get(receipt_url, timeout=15)
            response.raise_for_status()
            image_data = response.content
            
            # Determine MIME type from URL or response headers
            mime_type = response.headers.get('Content-Type')
            if not mime_type:
                mime_type = mimetypes.guess_type(receipt_url)[0]
            if not mime_type:
                # Default to jpeg if unknown
                mime_type = "image/jpeg"
            
            # Convert to base64
            img_base64 = base64.b64encode(image_data).decode('utf-8')
            logger.info("Successfully fetched and encoded receipt image from %s (size: %d bytes)", receipt_url, len(image_data))
            return f"data:{mime_type};base64,{img_base64}"
            
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to fetch receipt image from %s: %s", receipt_url, e)
            return None
