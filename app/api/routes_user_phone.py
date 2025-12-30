"""Phone verification related endpoints extracted from routes_user.py.

Allows users to link their WhatsApp phone number to their account.
Flow:
1. POST /users/me/phone/request - Set phone and send OTP via WhatsApp
2. POST /users/me/phone/verify - Verify OTP and mark phone as verified
3. DELETE /users/me/phone - Remove phone from account
"""
import logging
import random
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.db.session import get_db
from app.models import models, schemas
from app.core.config import settings
from app.bot.whatsapp_client import WhatsAppClient

logger = logging.getLogger(__name__)
router = APIRouter(tags=["users"])


def _normalize_phone(phone: str) -> str:
    """Normalize phone to E.164 format (+234...)."""
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("+"):
        return phone
    if phone.startswith("0"):
        return f"+234{phone[1:]}"
    if phone.startswith("234"):
        return f"+{phone}"
    return f"+{phone}"


@router.post("/me/phone/request", response_model=schemas.MessageOut)
def request_phone_otp(
    payload: schemas.PhoneVerificationRequest,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Set phone number and send OTP via WhatsApp.
    
    This endpoint:
    1. Saves the phone number to user (unverified)
    2. Generates a 6-digit OTP
    3. Sends OTP via WhatsApp
    """
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    normalized_phone = _normalize_phone(payload.phone)
    
    # Check if phone is already used by another user
    existing = db.query(models.User).filter(
        models.User.phone == normalized_phone,
        models.User.id != current_user_id,
        models.User.phone_verified == True,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Phone number already in use")
    
    # Generate OTP
    otp = f"{random.randint(100000, 999999)}"
    
    # Save phone and OTP
    user.phone = normalized_phone
    user.phone_otp = otp
    user.phone_verified = False
    db.commit()
    
    # Send OTP via WhatsApp using authentication template (bypasses 24-hour window)
    try:
        client = WhatsAppClient(settings.WHATSAPP_API_KEY)
        success = client.send_otp_template(
            to=normalized_phone,
            otp_code=otp,
            template_name="otp_verifications",
            language="en",
        )
        if success:
            logger.info("Sent phone verification OTP to %s via WhatsApp template", normalized_phone)
        else:
            logger.warning("Failed to send OTP template to %s", normalized_phone)
            raise HTTPException(
                status_code=500, 
                detail="Failed to send OTP via WhatsApp. Please try again."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to send OTP via WhatsApp to %s: %s", normalized_phone, e)
        raise HTTPException(status_code=500, detail="Failed to send OTP. Please try again.")
    
    return schemas.MessageOut(detail="OTP sent to WhatsApp")


# Legacy endpoint for backward compatibility
@router.post("/me/phone/send-otp", response_model=schemas.MessageOut, include_in_schema=False)
def send_phone_otp_legacy(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """Legacy endpoint - redirects to new flow."""
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user or not user.phone:
        raise HTTPException(status_code=400, detail="Use /me/phone/request to add phone number")
    
    # Re-send OTP to existing phone using authentication template
    otp = f"{random.randint(100000, 999999)}"
    user.phone_otp = otp
    db.commit()
    
    try:
        client = WhatsAppClient(settings.WHATSAPP_API_KEY)
        success = client.send_otp_template(
            to=user.phone,
            otp_code=otp,
            template_name="otp_verifications",
            language="en",
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to send OTP via WhatsApp")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to send OTP via WhatsApp to %s: %s", user.phone, e)
        raise HTTPException(status_code=500, detail="Failed to send OTP")
    
    return schemas.MessageOut(detail="OTP sent")


@router.post("/me/phone/verify", response_model=schemas.PhoneVerificationResponse)
def verify_phone(
    payload: schemas.PhoneVerificationVerify,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Verify phone number with OTP.
    
    After successful verification, the phone number is marked as verified
    and can be used for WhatsApp invoice creation.
    """
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.phone:
        raise HTTPException(status_code=400, detail="No phone number pending verification")
    if not user.phone_otp:
        raise HTTPException(status_code=400, detail="No OTP pending. Request a new one.")
    if payload.otp != user.phone_otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    
    # Verify the phone
    user.phone_verified = True
    user.phone_otp = None
    db.commit()
    
    logger.info("Phone verified for user %s: %s", current_user_id, user.phone)
    return schemas.PhoneVerificationResponse(
        detail="Phone verified successfully! You can now create invoices via WhatsApp.",
        phone=user.phone,
    )


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
