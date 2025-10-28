"""User profile and settings management endpoints."""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.db.session import get_db
from app.models import models, schemas
from app.storage.s3_client import s3_client

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/me/bank-details", response_model=schemas.BankDetailsOut)
def get_bank_details(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Get current user's bank account details.
    
    Returns bank details configured for receiving customer payments.
    """
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if all required fields are configured
    is_configured = bool(
        user.bank_name 
        and user.account_number 
        and user.account_name
    )
    
    return schemas.BankDetailsOut(
        business_name=user.business_name,
        bank_name=user.bank_name,
        account_number=user.account_number,
        account_name=user.account_name,
        is_configured=is_configured,
    )


@router.patch("/me/bank-details", response_model=schemas.BankDetailsOut)
def update_bank_details(
    data: schemas.BankDetailsUpdate,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Update current user's bank account details.
    
    Only provided fields will be updated. At least one field must be provided.
    
    **Account Number Validation:**
    - Must be exactly 10 digits
    - Nigerian bank account numbers are standardized at 10 digits
    
    **Bank Name Examples:**
    - Access Bank
    - GTBank (Guaranty Trust Bank)
    - First Bank of Nigeria
    - Zenith Bank
    - UBA (United Bank for Africa)
    """
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if at least one field is being updated
    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=400, 
            detail="At least one field must be provided"
        )
    
    # Update only provided fields
    if data.business_name is not None:
        user.business_name = data.business_name
    if data.bank_name is not None:
        user.bank_name = data.bank_name
    if data.account_number is not None:
        user.account_number = data.account_number
    if data.account_name is not None:
        user.account_name = data.account_name
    
    db.commit()
    db.refresh(user)
    
    # Check if configuration is complete
    is_configured = bool(
        user.bank_name 
        and user.account_number 
        and user.account_name
    )
    
    return schemas.BankDetailsOut(
        business_name=user.business_name,
        bank_name=user.bank_name,
        account_number=user.account_number,
        account_name=user.account_name,
        is_configured=is_configured,
    )


@router.post("/me/bank-details", response_model=schemas.BankDetailsOut)
def create_bank_details(
    data: schemas.BankDetailsUpdate,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Set bank account details (alias for PATCH for convenience).
    
    This endpoint does the same thing as PATCH /me/bank-details.
    Use whichever HTTP method you prefer - both update the same fields.
    """
    return update_bank_details(data, current_user_id, db)


@router.delete("/me/bank-details", response_model=schemas.MessageOut)
def delete_bank_details(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Clear all bank account details.
    
    ⚠️ Warning: After clearing, invoices won't show payment instructions to customers.
    You'll need to reconfigure bank details before creating new invoices.
    """
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Clear all bank-related fields
    user.business_name = None
    user.bank_name = None
    user.account_number = None
    user.account_name = None
    
    db.commit()
    
    return schemas.MessageOut(detail="Bank details cleared successfully")


@router.post("/me/logo", response_model=schemas.MessageOut)
async def upload_logo(
    file: UploadFile = File(...),
    current_user_id: Annotated[int, Depends(get_current_user_id)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """
    Upload business logo for invoices.
    
    **Accepted formats:** PNG, JPG, JPEG, SVG
    **Max size:** 5MB
    **Recommended:** Square logo, minimum 200x200px for best quality
    
    The logo will appear on all invoices and receipts.
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="File must be an image (PNG, JPG, JPEG, or SVG)"
        )
    
    allowed_types = ["image/png", "image/jpeg", "image/jpg", "image/svg+xml"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type. Allowed: PNG, JPG, JPEG, SVG"
        )
    
    # Read file content
    content = await file.read()
    
    # Validate file size (5MB max)
    max_size = 5 * 1024 * 1024  # 5MB
    if len(content) > max_size:
        raise HTTPException(
            status_code=400,
            detail="File size exceeds 5MB limit"
        )
    
    # Get user
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    try:
        # Generate unique filename
        file_extension = file.filename.split(".")[-1] if file.filename else "png"
        object_key = f"logos/user_{current_user_id}.{file_extension}"
        
        # Upload to S3
        logo_url = await s3_client.upload_file(
            content,
            object_key,
            content_type=file.content_type
        )
        
        # Update user logo_url
        user.logo_url = logo_url
        db.commit()
        
        logger.info(f"Logo uploaded for user {current_user_id}: {logo_url}")
        return schemas.MessageOut(detail="Logo uploaded successfully")
        
    except Exception as e:
        logger.error(f"Failed to upload logo for user {current_user_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to upload logo. Please try again."
        )


@router.delete("/me/logo", response_model=schemas.MessageOut)
def delete_logo(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Remove business logo.
    
    ⚠️ Invoices will no longer show your logo after removal.
    """
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not user.logo_url:
        raise HTTPException(status_code=404, detail="No logo configured")
    
    # Clear logo URL (we don't delete from S3 to preserve history)
    user.logo_url = None
    db.commit()
    
    return schemas.MessageOut(detail="Logo removed successfully")


@router.get("/me", response_model=schemas.UserOut)
def get_profile(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """Return current user's core profile and subscription details."""
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return schemas.UserOut(
        id=user.id,
        phone=user.phone,
        name=user.name,
        plan=user.plan.value,
        invoices_this_month=user.invoices_this_month,
        logo_url=user.logo_url,
        business_name=user.business_name,
        phone_verified=user.phone_verified,
    )

