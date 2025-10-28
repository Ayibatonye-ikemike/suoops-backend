from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


def _format_amount(value: Decimal | None) -> str | None:
    """Format Decimal values without trailing zeros for API responses."""
    if value is None:
        return None

    normalized = value.normalize()
    if normalized == normalized.to_integral():
        normalized = normalized.quantize(Decimal("1"))

    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


class InvoiceLineIn(BaseModel):
    description: str
    quantity: int = 1
    unit_price: Decimal


class InvoiceCreate(BaseModel):
    customer_name: str
    customer_phone: str | None = None
    customer_email: str | None = None
    amount: Decimal
    due_date: dt.datetime | None = None
    lines: list[InvoiceLineIn] | None = None
    discount_amount: Decimal | None = None


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    phone: str | None = None
    email: str | None = None


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invoice_id: str
    amount: Decimal
    status: str
    pdf_url: str | None
    created_at: dt.datetime | None = None
    due_date: dt.datetime | None = None


class InvoiceLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    description: str
    quantity: int
    unit_price: Decimal


class InvoiceOutDetailed(InvoiceOut):
    model_config = ConfigDict(from_attributes=True)

    discount_amount: Decimal | None = None
    customer: CustomerOut | None = None
    lines: list[InvoiceLineOut] = Field(default_factory=list)


class InvoiceStatusUpdate(BaseModel):
    status: Literal["pending", "awaiting_confirmation", "paid", "failed"]


class InvoicePublicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invoice_id: str
    amount: Decimal
    status: str
    due_date: dt.datetime | None = None
    customer_name: str | None = None
    business_name: str | None = None
    bank_name: str | None = None
    account_number: str | None = None
    account_name: str | None = None

    @field_serializer("amount")
    def _serialize_amount(self, value: Decimal) -> str:
        return _format_amount(value) or "0"

# ----------------- Auth -----------------

class OTPPhoneRequest(BaseModel):
    phone: str


class SignupStart(BaseModel):
    phone: str
    name: str
    business_name: str | None = None


class SignupVerify(BaseModel):
    phone: str
    otp: str = Field(..., min_length=6, max_length=6)


class LoginVerify(BaseModel):
    phone: str
    otp: str = Field(..., min_length=6, max_length=6)


class OTPResend(BaseModel):
    phone: str
    purpose: Literal["signup", "login"]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    name: str
    plan: str  # FREE, STARTER, PRO, BUSINESS, ENTERPRISE
    invoices_this_month: int
    logo_url: str | None = None
    business_name: str | None = None
    phone_verified: bool = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    access_expires_at: dt.datetime
    refresh_token: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class MessageOut(BaseModel):
    detail: str


# ----------------- Bank Details -----------------

class BankDetailsUpdate(BaseModel):
    """Schema for updating business bank account details."""
    business_name: str | None = Field(None, min_length=1, max_length=255, description="Business display name")
    bank_name: str | None = Field(None, min_length=1, max_length=100, description="Bank name (e.g., GTBank, Access Bank)")
    account_number: str | None = Field(None, min_length=10, max_length=10, pattern=r'^\d{10}$', description="10-digit account number")
    account_name: str | None = Field(None, min_length=1, max_length=255, description="Account holder name")


class BankDetailsOut(BaseModel):
    """Schema for returning bank account details."""
    model_config = ConfigDict(from_attributes=True)
    
    business_name: str | None = None
    bank_name: str | None = None
    account_number: str | None = None
    account_name: str | None = None
    is_configured: bool = Field(description="Whether bank details are fully configured")
