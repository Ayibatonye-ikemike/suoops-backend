"""
Celery Tasks Module.

This module provides a modular, SRP-compliant task organization.
All tasks are registered with the Celery app.

Sub-modules:
- pdf_tasks: Invoice and receipt PDF generation
- messaging_tasks: WhatsApp, OCR, and payment sync
- tax_tasks: Tax reports and fiscalization
- expense_tasks: Expense summaries and reminders
"""
from __future__ import annotations

# Re-export all tasks for backward compatibility
from .pdf_tasks import (
    generate_invoice_pdf_async,
    generate_receipt_pdf_async,
)
from .messaging_tasks import (
    process_whatsapp_inbound,
    send_overdue_reminders,
    sync_provider_status,
    ocr_parse_image,
)
from .tax_tasks import (
    generate_previous_month_reports,
    transmit_invoice,
)
from .expense_tasks import (
    send_expense_summary,
    send_expense_reminders,
)

__all__ = [
    # PDF tasks
    "generate_invoice_pdf_async",
    "generate_receipt_pdf_async",
    # Messaging tasks
    "process_whatsapp_inbound",
    "send_overdue_reminders",
    "sync_provider_status",
    "ocr_parse_image",
    # Tax tasks
    "generate_previous_month_reports",
    "transmit_invoice",
    # Expense tasks
    "send_expense_summary",
    "send_expense_reminders",
]
