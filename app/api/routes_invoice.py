from typing import Annotated, TypeAlias
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.db.session import get_db
from app.models import schemas
from app.services.invoice_service import build_invoice_service, InvoiceService

router = APIRouter()

CurrentUserDep: TypeAlias = Annotated[int, Depends(get_current_user_id)]
DbDep: TypeAlias = Annotated[Session, Depends(get_db)]


def get_invoice_service_for_user(current_user_id: CurrentUserDep, db: DbDep) -> InvoiceService:
    """Get InvoiceService for the requesting business."""
    return build_invoice_service(db, user_id=current_user_id)


@router.post("/", response_model=schemas.InvoiceOut)
async def create_invoice(
    data: schemas.InvoiceCreate,
    current_user_id: CurrentUserDep,
    db: DbDep,
):
    svc = get_invoice_service_for_user(current_user_id, db)
    try:
        invoice = svc.create_invoice(issuer_id=current_user_id, data=data.model_dump())
        
        # Send email if customer email provided
        if data.customer_email:
            from app.services.notification_service import NotificationService
            notification_service = NotificationService()
            email_sent = await notification_service.send_invoice_email(
                invoice=invoice,
                recipient_email=data.customer_email,
                pdf_url=invoice.pdf_url,
                subject="New Invoice"
            )
            if email_sent:
                import logging
                logger = logging.getLogger(__name__)
                logger.info("Invoice email sent to %s", data.customer_email)
        
        return invoice
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/", response_model=list[schemas.InvoiceOut])
def list_invoices(current_user_id: CurrentUserDep, db: DbDep):
    svc = get_invoice_service_for_user(current_user_id, db)
    return svc.list_invoices(current_user_id)


@router.get("/{invoice_id}", response_model=schemas.InvoiceOutDetailed)
def get_invoice(invoice_id: str, current_user_id: CurrentUserDep, db: DbDep):
    svc = get_invoice_service_for_user(current_user_id, db)
    try:
        return svc.get_invoice(current_user_id, invoice_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{invoice_id}", response_model=schemas.InvoiceOutDetailed)
def update_invoice_status(
    invoice_id: str,
    payload: schemas.InvoiceStatusUpdate,
    current_user_id: CurrentUserDep,
    db: DbDep,
):
    svc = get_invoice_service_for_user(current_user_id, db)
    try:
        return svc.update_status(current_user_id, invoice_id, payload.status)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail == "Invoice not found" else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/{invoice_id}/pdf")
def download_invoice_pdf(invoice_id: str, current_user_id: CurrentUserDep, db: DbDep):
    """Download PDF for an invoice. Serves local files when S3 is not configured."""
    svc = get_invoice_service_for_user(current_user_id, db)
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
