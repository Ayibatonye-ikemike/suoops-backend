from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    status: Literal["pending", "paid", "failed"]


class WebhookEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    external_id: str
    created_at: dt.datetime


class WorkerCreate(BaseModel):
    name: str
    daily_rate: Decimal


class WorkerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    daily_rate: Decimal


class PayrollRunCreate(BaseModel):
    period_label: str
    # simplistic: list of worker_id -> days
    days: dict[int, int] = Field(default_factory=dict)


class PayrollRecordOut(BaseModel):
    worker_id: int
    gross_pay: Decimal
    net_pay: Decimal


class PayrollRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    period_label: str
    total_gross: Decimal
    records: list[PayrollRecordOut]


# ----------------- Auth -----------------

class UserCreate(BaseModel):
    phone: str
    name: str
    password: str


class UserLogin(BaseModel):
    phone: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    name: str
    plan: str  # FREE, STARTER, PRO, BUSINESS, ENTERPRISE
    invoices_this_month: int
    logo_url: str | None = None


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
