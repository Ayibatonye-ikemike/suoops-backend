"""Query/list helpers for invoices."""
from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.exceptions import InvoiceNotFoundError
from app.models import models

logger = logging.getLogger(__name__)


class InvoiceQueryMixin:
    db: Session

    def list_invoices(
        self,
        issuer_id: int,
        invoice_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[models.Invoice], int]:
        """Return a page of invoices and the total count matching the filters."""
        if self.cache and skip == 0 and limit >= 50:
            cached = self.cache.get_invoice_list(issuer_id)
            if cached is not None:
                logger.info("Cache hit for user %s invoice list", issuer_id)

        query = (
            self.db.query(models.Invoice)
            .filter(models.Invoice.issuer_id == issuer_id)
        )
        
        # Filter by invoice_type before limit for correct results
        if invoice_type:
            query = query.filter(models.Invoice.invoice_type == invoice_type)
        
        # Get total count before applying pagination
        total = query.count()
        
        invoices = (
            query
            .options(
                joinedload(models.Invoice.customer),
                selectinload(models.Invoice.lines),
                joinedload(models.Invoice.issuer),
                joinedload(models.Invoice.created_by),  # Load creator for name display
                joinedload(models.Invoice.status_updated_by),  # Load status updater for name display
            )
            .order_by(models.Invoice.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

        if self.cache and invoices:
            self.cache.set_invoice_list(issuer_id, invoices)
        return invoices, total

    def get_invoice(self, issuer_id: int, invoice_id: str) -> models.Invoice:
        if self.cache:
            cached = self.cache.get_invoice(invoice_id)
            if cached:
                logger.info("Cache hit for invoice %s", invoice_id)

        invoice = (
            self.db.query(models.Invoice)
            .options(
                selectinload(models.Invoice.lines),
                joinedload(models.Invoice.customer),
                joinedload(models.Invoice.issuer),
                joinedload(models.Invoice.created_by),  # Load creator for name display
                joinedload(models.Invoice.status_updated_by),  # Load status updater for name display
            )
            .filter(models.Invoice.invoice_id == invoice_id, models.Invoice.issuer_id == issuer_id)
            .one_or_none()
        )
        if not invoice:
            raise InvoiceNotFoundError(invoice_id)

        if self.cache:
            self.cache.set_invoice(invoice)
        if invoice.paid_at is not None and invoice.paid_at.tzinfo is None:
            invoice.paid_at = invoice.paid_at.replace(tzinfo=dt.timezone.utc)
        return invoice
