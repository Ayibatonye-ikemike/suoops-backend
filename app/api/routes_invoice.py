from typing import Annotated, TypeAlias
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.routes_auth import get_current_user_id
from app.models import schemas
from app.services.invoice_service import InvoiceService, get_invoice_service

router = APIRouter()

CurrentUserDep: TypeAlias = Annotated[int, Depends(get_current_user_id)]
InvoiceServiceDep: TypeAlias = Annotated[InvoiceService, Depends(get_invoice_service)]


@router.post("/", response_model=schemas.InvoiceOut)
def create_invoice(
    payload: schemas.InvoiceCreate,
    current_user_id: CurrentUserDep,
    svc: InvoiceServiceDep,
):
    try:
        return svc.create_invoice(issuer_id=current_user_id, data=payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/", response_model=list[schemas.InvoiceOut])
def list_invoices(current_user_id: CurrentUserDep, svc: InvoiceServiceDep):
    return svc.list_invoices(current_user_id)


@router.get("/{invoice_id}", response_model=schemas.InvoiceOutDetailed)
def get_invoice(invoice_id: str, current_user_id: CurrentUserDep, svc: InvoiceServiceDep):
    try:
        return svc.get_invoice(current_user_id, invoice_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{invoice_id}", response_model=schemas.InvoiceOutDetailed)
def update_invoice_status(
    invoice_id: str,
    payload: schemas.InvoiceStatusUpdate,
    current_user_id: CurrentUserDep,
    svc: InvoiceServiceDep,
):
    try:
        return svc.update_status(current_user_id, invoice_id, payload.status)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail == "Invoice not found" else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/{invoice_id}/events", response_model=list[schemas.WebhookEventOut])
def list_invoice_events(invoice_id: str, current_user_id: CurrentUserDep, svc: InvoiceServiceDep):
    try:
        svc.get_invoice(current_user_id, invoice_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return svc.list_events(invoice_id)


@router.post("/payments/webhook")
def payment_webhook(event: dict, svc: InvoiceServiceDep):
    svc.handle_payment_webhook(event)
    return {"ok": True}


@router.get("/{invoice_id}/pdf")
def download_invoice_pdf(invoice_id: str, current_user_id: CurrentUserDep, svc: InvoiceServiceDep):
    """Download PDF for an invoice. Serves local files when S3 is not configured."""
    try:
        invoice = svc.get_invoice(current_user_id, invoice_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    
    if not invoice.pdf_url:
        raise HTTPException(status_code=404, detail="PDF not generated for this invoice")
    
    # If it's a file:// URL, serve from local filesystem
    if invoice.pdf_url.startswith("file://"):
        file_path = invoice.pdf_url.replace("file://", "")
        path = Path(file_path)
        
        if not path.exists():
            raise HTTPException(status_code=404, detail="PDF file not found on disk")
        
        return FileResponse(
            path=str(path),
            media_type="application/pdf",
            filename=f"{invoice_id}.pdf",
        )
    
    # If it's an HTTP URL (S3 presigned URL), redirect to it
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=invoice.pdf_url)
