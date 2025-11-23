from typing import Annotated, TypeAlias
from pathlib import Path
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.db.session import get_db
from app.models import schemas
from app.services.invoice_service import build_invoice_service, InvoiceService
from app.utils.feature_gate import check_invoice_limit, FeatureGate
from app.storage.s3_client import S3Client
from datetime import datetime, timezone

router = APIRouter()
logger = logging.getLogger(__name__)

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
    async_pdf: bool = True,  # Default to async PDF generation for better performance
):
    """Create a new invoice with optional async PDF generation.
    
    Args:
        data: Invoice creation data
        current_user_id: Authenticated user ID
        db: Database session
        async_pdf: If True, PDF is generated in background (faster API response).
                  If False, PDF is generated immediately (slower but PDF URL available in response).
                  Defaults to True for better user experience.
    """
    # Check invoice creation limit based on subscription plan
    check_invoice_limit(db, current_user_id)
    
    svc = get_invoice_service_for_user(current_user_id, db)
    try:
        invoice = svc.create_invoice(
            issuer_id=current_user_id,
            data=data.model_dump(),
            async_pdf=async_pdf,
        )
        
        # Send notifications via all available channels (Email, WhatsApp, SMS) - ONLY for revenue invoices
        # Note: If async_pdf=True, pdf_url may be None initially but we still send notifications without attachment
        if invoice.invoice_type == "revenue" and (data.customer_email or data.customer_phone):
            from app.services.notification_service import NotificationService
            notification_service = NotificationService()

            results = await notification_service.send_invoice_notification(
                invoice=invoice,
                customer_email=data.customer_email,
                customer_phone=data.customer_phone,
                pdf_url=invoice.pdf_url,
            )

            if async_pdf and not invoice.pdf_url:
                logger.info(
                    "Invoice %s notifications sent without PDF attachment (async PDF generation in progress)",
                    invoice.invoice_id,
                )

            logger.info(
                "Invoice %s notifications - Email: %s, WhatsApp: %s, SMS: %s",
                invoice.invoice_id,
                results["email"],
                results["whatsapp"],
                results["sms"],
            )
        
        return invoice
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/upload-receipt", response_model=schemas.ReceiptUploadOut)
async def upload_expense_receipt(
    current_user_id: CurrentUserDep,
    file: UploadFile = File(...),
):
    """Upload expense receipt image and return S3 URL for use in invoice creation.
    
    This endpoint allows users to upload proof of purchase (receipt photo/PDF)
    before creating an expense invoice. The returned receipt_url can then be
    included in the invoice creation request.
    """
    # Validate file type
    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp", "image/bmp", "application/pdf"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: JPEG, PNG, WebP, BMP, PDF. Got: {file.content_type}"
        )
    
    # Validate file size (max 10MB)
    max_size = 10 * 1024 * 1024  # 10MB
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB.")
    
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty.")
    
    try:
        # Upload to S3
        s3_client = S3Client()
        
        # Determine file extension
        ext = "jpg"
        if file.content_type == "application/pdf":
            ext = "pdf"
        elif file.content_type == "image/png":
            ext = "png"
        elif file.content_type == "image/webp":
            ext = "webp"
        
        # Create unique filename
        filename = f"receipts/user_{current_user_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.{ext}"
        
        receipt_url = await s3_client.upload_file(
            content,
            filename,
            content_type=file.content_type
        )
        
        logger.info(f"Uploaded expense receipt for user {current_user_id}: {receipt_url}")
        
        return schemas.ReceiptUploadOut(
            receipt_url=receipt_url,
            filename=file.filename or filename,
        )
    
    except Exception as e:
        logger.error(f"Failed to upload receipt: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to upload receipt. Please try again.")


@router.get("/quota", response_model=schemas.InvoiceQuotaOut)
def get_invoice_quota(current_user_id: CurrentUserDep, db: DbDep):
    """Return current monthly invoice usage and limit for the authenticated user.

    Enables frontend preflight checks to disable creation when limit reached.
    """
    gate = FeatureGate(db, current_user_id)
    current_count = gate.get_monthly_invoice_count()
    plan = gate.user.plan
    limit = plan.invoice_limit  # None means unlimited
    can_create, _ = gate.can_create_invoice()
    upgrade_url = "/subscription/initialize" if not can_create else None
    return schemas.InvoiceQuotaOut(
        current_count=current_count,
        limit=limit,
        current_plan=plan.value,
        can_create=can_create,
        upgrade_url=upgrade_url,
    )


@router.get("/", response_model=list[schemas.InvoiceOut])
def list_invoices(
    current_user_id: CurrentUserDep, 
    db: DbDep,
    invoice_type: str | None = None,  # Optional filter: "revenue", "expense", or None for all
):
    svc = get_invoice_service_for_user(current_user_id, db)
    invoices = svc.list_invoices(current_user_id)
    
    # Filter by invoice_type if specified
    if invoice_type:
        invoices = [inv for inv in invoices if inv.invoice_type == invoice_type]
    
    return invoices


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


@router.get("/{invoice_id}/verify", response_model=schemas.InvoiceVerificationOut)
def verify_invoice(invoice_id: str, db: DbDep):
    """Public endpoint to verify invoice authenticity via QR code scan.
    
    This endpoint does NOT require authentication - it's meant to be scanned
    by customers to verify the invoice is legitimate.
    
    Returns masked customer information for privacy while proving authenticity.
    """
    from app.models.models import Invoice
    from datetime import datetime
    
    invoice = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    # Mask customer name for privacy (show first letter + asterisks)
    customer_name = invoice.customer.name
    if len(customer_name) > 2:
        masked_name = customer_name[0] + "*" * (len(customer_name) - 2) + customer_name[-1]
    else:
        masked_name = customer_name[0] + "*"
    
    # Resolve issuer (business) name via relationship (added FK issuer_id -> user.id)
    if getattr(invoice, "issuer", None):
        business_name = invoice.issuer.business_name or invoice.issuer.name
    else:
        business_name = "Business"
    
    return schemas.InvoiceVerificationOut(
        invoice_id=invoice_id,
        status=invoice.status,
        amount=invoice.amount,
        customer_name=masked_name,
        business_name=business_name,
        created_at=invoice.created_at,
        verified_at=datetime.now(timezone.utc),
        authentic=True,
    )
