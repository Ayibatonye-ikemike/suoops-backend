"""Bank detail endpoints split from routes_user.py."""
import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.api.dependencies import AdminUserDep
from app.db.session import get_db
from app.models import models, schemas

logger = logging.getLogger(__name__)
router = APIRouter(tags=["users"])


@router.get("/me/bank-details", response_model=schemas.BankDetailsOut)
def get_bank_details(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    is_configured = bool(user.bank_name and user.account_number and user.account_name)
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
    current_user_id: AdminUserDep,
    db: Annotated[Session, Depends(get_db)],
):
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="At least one field must be provided")
    if data.business_name is not None:
        user.business_name = data.business_name
    if data.bank_name is not None:
        user.bank_name = data.bank_name
    if data.account_number is not None:
        user.account_number = data.account_number
    if data.account_name is not None:
        user.account_name = data.account_name
    db.commit(); db.refresh(user)
    is_configured = bool(user.bank_name and user.account_number and user.account_name)
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
    current_user_id: AdminUserDep,
    db: Annotated[Session, Depends(get_db)],
):
    return update_bank_details(data, current_user_id, db)


@router.delete("/me/bank-details", response_model=schemas.MessageOut)
def delete_bank_details(
    current_user_id: AdminUserDep,
    db: Annotated[Session, Depends(get_db)],
):
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.business_name = None
    user.bank_name = None
    user.account_number = None
    user.account_name = None
    db.commit()
    return schemas.MessageOut(detail="Bank details cleared successfully")
