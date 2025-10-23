from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import schemas
from app.services.invoice_service import build_invoice_service

router = APIRouter(tags=["invoices-public"])


def _public_invoice_payload(invoice, issuer) -> dict[str, object]:
    customer_name = getattr(invoice.customer, "name", None) if invoice.customer else None
    return {
        "invoice_id": invoice.invoice_id,
        "amount": invoice.amount,
        "status": invoice.status,
        "due_date": invoice.due_date,
        "customer_name": customer_name,
        "business_name": getattr(issuer, "business_name", None),
        "bank_name": getattr(issuer, "bank_name", None),
        "account_number": getattr(issuer, "account_number", None),
        "account_name": getattr(issuer, "account_name", None),
    }


@router.get("/{invoice_id}", response_model=schemas.InvoicePublicOut)
def get_invoice_public(invoice_id: str, db: Session = Depends(get_db)) -> schemas.InvoicePublicOut:
    svc = build_invoice_service(db)
    try:
        invoice, issuer = svc.get_public_invoice(invoice_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return schemas.InvoicePublicOut.model_validate(_public_invoice_payload(invoice, issuer))


@router.post("/{invoice_id}/confirm-transfer", response_model=schemas.InvoicePublicOut)
def confirm_transfer(invoice_id: str, db: Session = Depends(get_db)) -> schemas.InvoicePublicOut:
    svc = build_invoice_service(db)
    try:
        svc.confirm_transfer(invoice_id)
        invoice, issuer = svc.get_public_invoice(invoice_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return schemas.InvoicePublicOut.model_validate(_public_invoice_payload(invoice, issuer))