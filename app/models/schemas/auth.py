"""Authentication-related schemas."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OTPPhoneRequest(BaseModel):
    phone: str


class OTPEmailRequest(BaseModel):
    """Request OTP via email (temporary for pre-launch)."""
    email: str


class SignupStart(BaseModel):
    """Start signup with phone OR email."""
    phone: str | None = None
    email: str | None = None
    name: str
    business_name: str | None = None


class SignupVerify(BaseModel):
    """Verify signup OTP with phone OR email."""
    phone: str | None = None
    email: str | None = None
    otp: str = Field(..., min_length=6, max_length=6)


class LoginVerify(BaseModel):
    """Verify login OTP with phone OR email."""
    phone: str | None = None
    email: str | None = None
    otp: str = Field(..., min_length=6, max_length=6)


class OTPResend(BaseModel):
    """Resend OTP for phone OR email."""
    phone: str | None = None
    email: str | None = None
    purpose: Literal["signup", "login"]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str | None = None
    phone_verified: bool = False
    email: str | None = None
    name: str
    plan: str  # FREE, STARTER, PRO, BUSINESS
    invoices_this_month: int
    logo_url: str | None = None
    subscription_expires_at: dt.datetime | None = None
    subscription_started_at: dt.datetime | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    access_expires_at: dt.datetime
    refresh_token: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class MessageOut(BaseModel):
    detail: str


class PhoneVerificationRequest(BaseModel):
    """Request to add/verify phone number."""
    phone: str = Field(..., min_length=10, description="Phone number in E.164 format")


class PhoneVerificationVerify(BaseModel):
    """Verify phone number with OTP."""
    phone: str = Field(..., min_length=10)
    otp: str = Field(..., min_length=6, max_length=6)


class PhoneVerificationResponse(BaseModel):
    """Response after successful phone verification."""
    detail: str
    phone: str
