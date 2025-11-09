from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.notification.email_helpers import (
    send_invoice_email,
    send_receipt_email,
    send_simple_email,
)

if TYPE_CHECKING:  # pragma: no cover
    from app.models import models
    from app.services.notification.service import NotificationService


class EmailChannel:
    """Encapsulates email send operations used by NotificationService."""

    def __init__(self, service: "NotificationService") -> None:
        self._service = service

    async def send_invoice(
        self,
        invoice: "models.Invoice",
        recipient_email: str,
        pdf_url: str | None,
        subject: str = "New Invoice",
    ) -> bool:
        return await send_invoice_email(self._service, invoice, recipient_email, pdf_url, subject)

    async def send_receipt(
        self,
        invoice: "models.Invoice",
        recipient_email: str,
        pdf_url: str | None,
    ) -> bool:
        return await send_receipt_email(self._service, invoice, recipient_email, pdf_url)

    async def send_simple(self, to_email: str, subject: str, body: str) -> bool:
        return await send_simple_email(self._service, to_email, subject, body)
