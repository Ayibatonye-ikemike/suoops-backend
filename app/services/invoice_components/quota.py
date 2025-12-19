"""Quota/plan helpers extracted from InvoiceService.

NEW BILLING MODEL:
- Invoice balance based (not monthly limits)
- 100 invoices = ₦2,500 per pack
- All plans can purchase packs
- Balance is decremented on revenue invoice creation
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import TYPE_CHECKING

from app.core.exceptions import InvoiceBalanceExhaustedError, UserNotFoundError
from app.models import models
from app.utils.feature_gate import INVOICE_PACK_PRICE, INVOICE_PACK_SIZE

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class InvoiceQuotaMixin:
    """Provides invoice balance utilities for invoice flows."""

    db: "Session"

    def check_invoice_quota(self, issuer_id: int) -> dict[str, object]:
        """Check user's invoice balance and return quota info."""
        user = self.db.query(models.User).filter(models.User.id == issuer_id).one_or_none()
        if not user:
            raise UserNotFoundError()

        balance = user.invoice_balance

        if balance <= 0:
            return {
                "can_create": False,
                "plan": user.plan.value,
                "invoice_balance": 0,
                "pack_price": INVOICE_PACK_PRICE,
                "pack_size": INVOICE_PACK_SIZE,
                "message": f"No invoices remaining. Purchase a pack (₦{INVOICE_PACK_PRICE:,} for {INVOICE_PACK_SIZE} invoices).",
            }

        message = f"{balance} invoices remaining"
        if balance <= 10:
            message = f"⚠️ Only {balance} invoices left! Purchase a pack to top up."

        return {
            "can_create": True,
            "plan": user.plan.value,
            "invoice_balance": balance,
            "pack_price": INVOICE_PACK_PRICE,
            "pack_size": INVOICE_PACK_SIZE,
            "message": message,
        }

    def enforce_quota(self, issuer_id: int, invoice_type: str) -> None:
        """Raise if the issuer has no invoice balance (revenue invoices only)."""
        if invoice_type != "revenue":
            return  # Expense invoices don't consume balance
        
        quota = self.check_invoice_quota(issuer_id)
        if not quota["can_create"]:
            raise InvoiceBalanceExhaustedError(
                balance=quota["invoice_balance"],
                pack_price=INVOICE_PACK_PRICE,
                pack_size=INVOICE_PACK_SIZE,
            )
    
    def deduct_invoice_balance(self, issuer_id: int) -> None:
        """Deduct one invoice from user's balance after creating revenue invoice."""
        user = self.db.query(models.User).filter(models.User.id == issuer_id).one_or_none()
        if user and user.invoice_balance > 0:
            user.invoice_balance -= 1
            self.db.commit()
            logger.info(
                "Deducted 1 invoice from user %s balance (remaining: %d)",
                issuer_id, user.invoice_balance
            )
