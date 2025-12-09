"""
Backward Compatibility Redirect.

This module redirects imports from the old tasks location
to the new modular tasks package.

DEPRECATED: Import directly from app.workers.tasks instead:
    from app.workers.tasks import generate_invoice_pdf_async
"""
from app.workers.tasks import (
    generate_invoice_pdf_async,
    generate_receipt_pdf_async,
    process_whatsapp_inbound,
    send_overdue_reminders,
    sync_provider_status,
    ocr_parse_image,
    generate_previous_month_reports,
    transmit_invoice,
    send_expense_summary,
    send_expense_reminders,
)

__all__ = [
    "generate_invoice_pdf_async",
    "generate_receipt_pdf_async",
    "process_whatsapp_inbound",
    "send_overdue_reminders",
    "sync_provider_status",
    "ocr_parse_image",
    "generate_previous_month_reports",
    "transmit_invoice",
    "send_expense_summary",
    "send_expense_reminders",
]
