from typing import Annotated, TypeAlias
from pathlib import Path
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.api.dependencies import get_data_owner_id
from app.db.session import get_db
from app.models import schemas
from app.services.invoice_service import build_invoice_service, InvoiceService
from app.utils.feature_gate import check_invoice_limit, FeatureGate
from app.storage.s3_client import S3Client
from datetime import datetime, timezone

router = APIRouter()
logger = logging.getLogger(__name__)

CurrentUserDep: TypeAlias = Annotated[int, Depends(get_current_user_id)]
DataOwnerDep: TypeAlias = Annotated[int, Depends(get_data_owner_id)]
DbDep: TypeAlias = Annotated[Session, Depends(get_db)]


def get_invoice_service_for_user(data_owner_id: DataOwnerDep, db: DbDep) -> InvoiceService:
    """Get InvoiceService for the data owner (team admin for members, self for solo/admin)."""
    return build_invoice_service(db, user_id=data_owner_id)


@router.post("/", response_model=schemas.InvoiceOut)
async def create_invoice(
    data: schemas.InvoiceCreate,
    current_user_id: CurrentUserDep,
    data_owner_id: DataOwnerDep,
    db: DbDep,
    async_pdf: bool = True,  # Default to async PDF generation for better performance
):
    """Create a new invoice with optional async PDF generation.
    
    Args:
        data: Invoice creation data
        current_user_id: Authenticated user ID
        data_owner_id: The user ID whose data we're accessing (team admin for members)
        db: Database session
        async_pdf: If True, PDF is generated in background (faster API response).
              If False, PDF is generated immediately (slower but PDF URL available in response).
              Defaults to True for better user experience. When an invoice email is requested,
              the system automatically forces synchronous generation so the attachment is present.
    """
    # Check invoice creation limit based on data owner's subscription plan
    check_invoice_limit(db, data_owner_id)
    
    svc = get_invoice_service_for_user(data_owner_id, db)

    # Ensure PDF exists before sending email so attachment is present
    effective_async = async_pdf
    if async_pdf and data.customer_email:
        effective_async = False
        logger.info(
            "Forcing synchronous PDF generation for invoice email attachment | user=%s data_owner=%s",
            current_user_id,
            data_owner_id,
        )
    try:
        invoice = svc.create_invoice(
            issuer_id=data_owner_id,
            data=data.model_dump(),
            async_pdf=effective_async,
            created_by_user_id=current_user_id,  # Track actual creator for confirmation permissions
        )
        
        # Send notifications via available channels (Email, WhatsApp) - ONLY for revenue invoices
        # Note: WhatsApp uses centralized opt-in logic - new customers get template, opted-in get full invoice
        if invoice.invoice_type == "revenue" and (data.customer_email or data.customer_phone):
            from app.services.notification_service import NotificationService
            notification_service = NotificationService()

            results = await notification_service.send_invoice_notification(
                invoice=invoice,
                customer_email=data.customer_email,
                customer_phone=data.customer_phone,
                pdf_url=invoice.pdf_url,
            )
            
            # Commit any changes made during notification (e.g., whatsapp_delivery_pending flag)
            db.commit()

            if async_pdf and not invoice.pdf_url:
                logger.info(
                    "Invoice %s notifications sent without PDF attachment (async PDF generation in progress)",
                    invoice.invoice_id,
                )

            logger.info(
                "Invoice %s notifications - Email: %s, WhatsApp: %s",
                invoice.invoice_id,
                results["email"],
                results["whatsapp"],
            )
        
        return invoice
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/upload-receipt", response_model=schemas.ReceiptUploadOut)
async def upload_expense_receipt(
    current_user_id: CurrentUserDep,
    data_owner_id: DataOwnerDep,
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
        
        # Create unique filename (use data_owner_id for team context)
        filename = f"receipts/user_{data_owner_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.{ext}"
        
        receipt_url = await s3_client.upload_file(
            content,
            filename,
            content_type=file.content_type
        )
        
        logger.info(f"Uploaded expense receipt for data_owner {data_owner_id} by user {current_user_id}: {receipt_url}")
        
        return schemas.ReceiptUploadOut(
            receipt_url=receipt_url,
            filename=file.filename or filename,
        )
    
    except Exception as e:
        logger.error(f"Failed to upload receipt: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to upload receipt. Please try again.")


@router.get("/quota", response_model=schemas.InvoiceQuotaOut)
def get_invoice_quota(current_user_id: CurrentUserDep, data_owner_id: DataOwnerDep, db: DbDep):
    """Return current invoice balance for the data owner.

    NEW MODEL: Returns invoice_balance (purchased invoices remaining) instead of monthly limits.
    For team members, this returns the team admin's quota.
    """
    from app.utils.feature_gate import INVOICE_PACK_PRICE, INVOICE_PACK_SIZE
    
    gate = FeatureGate(db, data_owner_id)
    plan = gate.user.plan
    invoice_balance = gate.get_invoice_balance()  # Safe access
    can_create, _ = gate.can_create_invoice()
    purchase_url = "/invoices/purchase-pack" if not can_create else None
    
    return schemas.InvoiceQuotaOut(
        invoice_balance=invoice_balance,
        current_plan=plan.value,
        can_create=can_create,
        pack_price=INVOICE_PACK_PRICE,
        pack_size=INVOICE_PACK_SIZE,
        purchase_url=purchase_url,
    )


@router.get("/", response_model=list[schemas.InvoiceOut])
def list_invoices(
    current_user_id: CurrentUserDep,
    data_owner_id: DataOwnerDep, 
    db: DbDep,
    invoice_type: str | None = None,  # Optional filter: "revenue", "expense", or None for all
    start_date: str | None = None,  # Optional date filter (YYYY-MM-DD)
    end_date: str | None = None,  # Optional date filter (YYYY-MM-DD)
):
    from datetime import datetime as dt, date
    
    svc = get_invoice_service_for_user(data_owner_id, db)
    invoices = svc.list_invoices(data_owner_id)
    
    # Filter by invoice_type if specified
    if invoice_type:
        invoices = [inv for inv in invoices if inv.invoice_type == invoice_type]
    
    # Filter by date range if specified
    if start_date or end_date:
        def get_invoice_date(inv) -> date | None:
            """Extract date from invoice, handling various formats."""
            d = inv.due_date or inv.created_at
            if d is None:
                return None
            if isinstance(d, date):
                return d if not hasattr(d, 'date') else d.date()
            if isinstance(d, str):
                try:
                    return dt.strptime(d[:10], "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    return None
            return None
        
        if start_date:
            try:
                start = dt.strptime(start_date, "%Y-%m-%d").date()
                invoices = [inv for inv in invoices if (d := get_invoice_date(inv)) and d >= start]
            except ValueError:
                pass  # Invalid date format, skip filter
        
        if end_date:
            try:
                end = dt.strptime(end_date, "%Y-%m-%d").date()
                invoices = [inv for inv in invoices if (d := get_invoice_date(inv)) and d <= end]
            except ValueError:
                pass  # Invalid date format, skip filter
    
    return invoices


@router.get("/{invoice_id}", response_model=schemas.InvoiceOutDetailed)
def get_invoice(invoice_id: str, current_user_id: CurrentUserDep, data_owner_id: DataOwnerDep, db: DbDep):
    svc = get_invoice_service_for_user(data_owner_id, db)
    try:
        return svc.get_invoice(data_owner_id, invoice_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{invoice_id}", response_model=schemas.InvoiceOutDetailed)
def update_invoice_status(
    invoice_id: str,
    payload: schemas.InvoiceStatusUpdate,
    current_user_id: CurrentUserDep,
    data_owner_id: DataOwnerDep,
    db: DbDep,
):
    """Update invoice status. Only the creator or admin (issuer) can update it."""
    from app.models.models import Invoice
    
    # Check if user is allowed to update this invoice
    invoice = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    # Allow update if:
    # 1. User is the creator (created_by_user_id)
    # 2. User is the admin/issuer (issuer_id) - business owner always has access
    # For old invoices without created_by_user_id, issuer_id is the owner
    is_creator = invoice.created_by_user_id == current_user_id
    is_admin = invoice.issuer_id == current_user_id
    
    if not is_creator and not is_admin:
        raise HTTPException(
            status_code=403, 
            detail="Only the invoice creator or business admin can update the status"
        )
    
    svc = get_invoice_service_for_user(data_owner_id, db)
    try:
        return svc.update_status(data_owner_id, invoice_id, payload.status, updated_by_user_id=current_user_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail == "Invoice not found" else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/{invoice_id}/pdf")
def download_invoice_pdf(invoice_id: str, current_user_id: CurrentUserDep, data_owner_id: DataOwnerDep, db: DbDep):
    """Download PDF for an invoice. Serves local files when S3 is not configured."""
    svc = get_invoice_service_for_user(data_owner_id, db)
    try:
        invoice = svc.get_invoice(data_owner_id, invoice_id)
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


@router.post("/purchase-pack", response_model=schemas.InvoicePackPurchaseInitOut)
async def initialize_invoice_pack_purchase(
    current_user_id: CurrentUserDep,
    db: DbDep,
    quantity: int = 1,
):
    """
    Initialize Paystack payment for invoice pack purchase.
    
    NEW BILLING MODEL:
    - 100 invoices = ₦2,500 per pack
    - Available to all plans (FREE, STARTER, PRO, BUSINESS)
    - Invoice balance never expires
    
    **Parameters:**
    - quantity: Number of packs to purchase (default 1)
    
    **Returns:**
    - authorization_url: Paystack checkout URL
    - reference: Payment reference for tracking
    - amount: Amount in kobo (₦ x 100)
    - invoices_to_add: Number of invoices that will be added
    """
    import httpx
    import uuid
    from app.core.config import settings
    from app.models.payment_models import PaymentTransaction, PaymentStatus, PaymentProvider
    from app.utils.feature_gate import INVOICE_PACK_PRICE, INVOICE_PACK_SIZE
    from app import metrics
    
    if quantity < 1 or quantity > 10:
        raise HTTPException(status_code=400, detail="Quantity must be between 1 and 10 packs")
    
    user = db.query(models.User).filter(models.User.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Calculate total
    total_amount = INVOICE_PACK_PRICE * quantity
    invoices_to_add = INVOICE_PACK_SIZE * quantity
    
    # Generate unique reference
    reference = f"INVPACK-{current_user_id}-{uuid.uuid4().hex[:8].upper()}"
    
    # Record transaction (invoice pack - plan stays the same)
    current_plan = user.plan.value if user.plan else "free"
    transaction = PaymentTransaction(
        user_id=current_user_id,
        reference=reference,
        amount=total_amount * 100,  # Store in kobo like other transactions
        currency="NGN",
        provider=PaymentProvider.PAYSTACK,
        status=PaymentStatus.PENDING,
        plan_before=current_plan,
        plan_after=current_plan,  # Invoice pack doesn't change plan
        customer_email=user.email or f"{user.phone}@suoops.com",
        customer_phone=user.phone,
        payment_metadata={
            "payment_type": "invoice_pack",
            "quantity": quantity,
            "invoices_to_add": invoices_to_add,
        },
    )
    db.add(transaction)
    db.commit()
    
    # Initialize Paystack payment
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.paystack.co/transaction/initialize",
                headers={
                    "Authorization": f"Bearer {settings.PAYSTACK_SECRET}",
                    "Content-Type": "application/json",
                },
                json={
                    "email": user.email or f"{user.phone}@suoops.com",
                    "amount": total_amount * 100,  # Paystack expects kobo
                    "reference": reference,
                    "callback_url": f"{settings.FRONTEND_URL}/dashboard/billing/success?reference={reference}",
                    "metadata": {
                        "payment_type": "invoice_pack",
                        "user_id": current_user_id,
                        "quantity": quantity,
                        "invoices_to_add": invoices_to_add,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        logger.error(f"Paystack API error: {e}")
        transaction.status = PaymentStatus.FAILED
        db.commit()
        raise HTTPException(status_code=502, detail="Payment gateway error. Please try again.")
    
    if not data.get("status"):
        transaction.status = PaymentStatus.FAILED
        db.commit()
        raise HTTPException(status_code=502, detail=data.get("message", "Payment initialization failed"))
    
    auth_url = data["data"]["authorization_url"]
    
    logger.info(
        "Invoice pack payment initialized | user=%s quantity=%d invoices=%d amount=%d ref=%s",
        current_user_id, quantity, invoices_to_add, total_amount, reference
    )
    
    return schemas.InvoicePackPurchaseInitOut(
        authorization_url=auth_url,
        reference=reference,
        amount=total_amount,
        invoices_to_add=invoices_to_add,
    )


# Import models at module level for the new endpoint
from app.models import models
