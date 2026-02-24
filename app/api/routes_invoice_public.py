from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.rate_limit import limiter
from app.db.session import get_db
from app.models import schemas
from app.services.invoice_service import build_invoice_service

router = APIRouter(tags=["invoices-public"])


def _public_invoice_payload(invoice, issuer) -> dict[str, object]:
    customer_name = getattr(invoice.customer, "name", None) if invoice.customer else None
    lines_data = [
        {"description": ln.description, "quantity": ln.quantity, "unit_price": ln.unit_price}
        for ln in (invoice.lines or [])
    ]

    # Generate a fresh presigned URL for the business logo so it
    # doesn't break when the original presigned URL expires.
    logo_url: str | None = None
    stored_logo = getattr(issuer, "logo_url", None)
    if stored_logo:
        from app.storage.s3_client import s3_client
        logo_key = s3_client.extract_key_from_url(stored_logo)
        if logo_key:
            logo_url = s3_client.get_presigned_url(logo_key, expires_in=3600)
        if not logo_url:
            logo_url = stored_logo  # fallback to stored URL

    return {
        "invoice_id": invoice.invoice_id,
        "amount": invoice.amount,
        "currency": getattr(invoice, "currency", "NGN") or "NGN",
        "status": invoice.status,
        "due_date": invoice.due_date,
        "created_at": invoice.created_at,
        "paid_at": invoice.paid_at,
        "customer_name": customer_name,
        "business_name": getattr(issuer, "business_name", None),
        "business_logo_url": logo_url,
        "bank_name": getattr(issuer, "bank_name", None),
        "account_number": getattr(issuer, "account_number", None),
        "account_name": getattr(issuer, "account_name", None),
        "lines": lines_data,
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
@limiter.limit("3/minute")
def confirm_transfer(request: Request, invoice_id: str, db: Session = Depends(get_db)) -> schemas.InvoicePublicOut:
    svc = build_invoice_service(db)
    try:
        svc.confirm_transfer(invoice_id)
        invoice, issuer = svc.get_public_invoice(invoice_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return schemas.InvoicePublicOut.model_validate(_public_invoice_payload(invoice, issuer))