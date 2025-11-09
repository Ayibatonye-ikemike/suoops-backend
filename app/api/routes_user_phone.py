"""Phone verification related endpoints extracted from routes_user.py."""
import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.db.session import get_db
from app.models import models, schemas

# NotificationService import (supports legacy package path if introduced later)
try:
    from app.services.notification.notification_service import NotificationService  # type: ignore
except ModuleNotFoundError:  # Fallback to current single-file service location
    from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["users"])
notification_service = NotificationService()


@router.post("/me/phone/send-otp", response_model=schemas.MessageOut)
def send_phone_otp(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.phone:
        raise HTTPException(status_code=400, detail="No phone number on file")
    # Generate a simple numeric OTP (service may have dedicated util elsewhere)
    import random
    otp = f"{random.randint(100000, 999999)}"
    user.phone_otp = otp
    db.commit()
    try:
        notification_service.send_sms(user.phone, f"Your verification code is {otp}")
    except Exception as e:  # pragma: no cover
        logger.error("Failed to send OTP SMS to %s: %s", user.phone, e)
        raise HTTPException(status_code=500, detail="Failed to send OTP")
    return schemas.MessageOut(detail="OTP sent")


@router.post("/me/phone/verify", response_model=schemas.MessageOut)
def verify_phone(
    payload: schemas.PhoneVerificationVerify,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.phone_otp:
        raise HTTPException(status_code=400, detail="No OTP pending")
    if payload.otp != user.phone_otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    user.phone_verified = True
    user.phone_otp = None
    db.commit()
    return schemas.MessageOut(detail="Phone verified successfully")


@router.delete("/me/phone", response_model=schemas.MessageOut)
def remove_phone_number(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.phone:
        raise HTTPException(status_code=404, detail="No phone number configured")
    user.phone = None
    user.phone_verified = False
    db.commit()
    return schemas.MessageOut(detail="Phone number removed")
