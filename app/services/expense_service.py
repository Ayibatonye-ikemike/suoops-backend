"""Unified expense recording.

Expenses are stored as `Invoice` rows with ``invoice_type="expense"`` — the SAME
model the dashboard reads. This module is the single place every channel
(dashboard, WhatsApp bot, receipt OCR) uses to record an expense, so an expense
captured anywhere shows up everywhere. The legacy ``Expense`` table is no longer
written to.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import models


def record_expense_invoice(
    db: Session,
    *,
    user_id: int,
    amount,
    category: str | None = None,
    description: str | None = None,
    merchant: str | None = None,
    expense_date: dt.date | dt.datetime | None = None,
    input_method: str = "manual",
    channel: str = "dashboard",
    verified: bool = False,
    receipt_url: str | None = None,
    receipt_text: str | None = None,
    notes: str | None = None,
    created_by_user_id: int | None = None,
) -> models.Invoice:
    """Record a business expense as a paid expense-invoice and return it.

    Raises ``ValueError`` if the amount is not positive.
    """
    amt = Decimal(str(amount or 0))
    if amt <= 0:
        raise ValueError("Expense amount must be greater than 0")

    # The expense list + stats filter on coalesce(due_date, created_at), so we
    # store the expense date as due_date to keep it in the right period.
    if expense_date is None:
        due = dt.datetime.now(dt.timezone.utc)
    elif isinstance(expense_date, dt.datetime):
        due = expense_date
    else:  # date
        due = dt.datetime.combine(expense_date, dt.time.min, tzinfo=dt.timezone.utc)

    desc = (description or category or "Expense").strip() or "Expense"

    data: dict[str, object] = {
        "invoice_type": "expense",
        "amount": amt,
        "due_date": due,
        "category": category or "other",
        "vendor_name": merchant,
        "merchant": merchant,
        "description": desc,
        "receipt_url": receipt_url,
        "receipt_text": receipt_text,
        "input_method": input_method,
        "channel": channel,
        "verified": verified,
        "notes": notes,
        "lines": [{"description": desc, "quantity": 1, "unit_price": amt}],
    }

    from app.services.invoice_service import build_invoice_service

    svc = build_invoice_service(db, user_id=user_id)
    # Expense invoices never consume the wallet (enforce_quota skips them), but be
    # explicit so a future quota change can't accidentally charge for expenses.
    return svc.create_invoice(
        user_id,
        data,
        created_by_user_id=created_by_user_id,
        consume_balance=False,
    )


def expense_invoice_to_out(inv: models.Invoice) -> dict:
    """Map an expense `Invoice` to the legacy ExpenseOut response shape."""
    line_desc = None
    try:
        if inv.lines:
            line_desc = inv.lines[0].description
    except Exception:  # noqa: BLE001 — lines may be lazy/detached
        line_desc = None
    when = inv.due_date or inv.created_at
    return {
        "id": inv.id,
        "user_id": inv.issuer_id,
        "amount": inv.amount,
        "expense_date": when.date() if when else dt.date.today(),
        "category": inv.category or "other",
        "description": line_desc or inv.notes,
        "merchant": inv.merchant or inv.vendor_name,
        "input_method": inv.input_method,
        "channel": inv.channel,
        "receipt_url": inv.receipt_url,
        "verified": bool(inv.verified),
        "notes": inv.notes,
        "created_at": inv.created_at,
        "updated_at": inv.status_updated_at,
    }
