"""User profile and settings management endpoints."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.db.session import get_db
from app.models import models, schemas

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
