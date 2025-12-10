"""Invoice-related schemas."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from .utils import format_amount


class InvoiceLineIn(BaseModel):
    description: str
    quantity: int = 1
    unit_price: Decimal
    product_id: int | None = None  # Link to inventory product for automatic stock tracking


class InvoiceCreate(BaseModel):
    # Common fields for both revenue and expense invoices
    amount: Decimal
    due_date: dt.datetime | None = None
    lines: list[InvoiceLineIn] | None = None
    discount_amount: Decimal | None = None
    
    # Invoice type
    invoice_type: Literal["revenue", "expense"] = "revenue"
    
    # Revenue invoice fields (when invoice_type="revenue")
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_email: str | None = None
    
    # Expense invoice fields (when invoice_type="expense")
    vendor_name: str | None = None
    category: str | None = None  # rent, utilities, supplies, etc.
    merchant: str | None = None
    description: str | None = None
    receipt_url: str | None = None
    receipt_text: str | None = None
    input_method: str | None = None  # voice, text, photo, manual
    channel: str | None = None  # whatsapp, email, dashboard
    verified: bool = False
    notes: str | None = None


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
    receipt_pdf_url: str | None = None
    paid_at: dt.datetime | None = None
    created_at: dt.datetime | None = None
    due_date: dt.datetime | None = None
    
    # Unified invoice/expense fields
    invoice_type: str = "revenue"
    category: str | None = None
    vendor_name: str | None = None
    merchant: str | None = None
    verified: bool | None = None
    notes: str | None = None
    
    # Creator tracking for team scenarios
    created_by_user_id: int | None = None
    created_by_name: str | None = None
    
    @model_validator(mode="before")
    @classmethod
    def populate_created_by_name(cls, data: Any) -> Any:
        """Extract created_by_name from the created_by relationship."""
        if hasattr(data, "created_by") and data.created_by is not None:
            # SQLAlchemy model with relationship
            return {
                **{k: getattr(data, k, None) for k in cls.model_fields.keys() if k != "created_by_name"},
                "created_by_name": data.created_by.name,
            }
        return data


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
    # Added "refunded" to support post-payment refund handling
    status: Literal["pending", "awaiting_confirmation", "paid", "failed", "refunded"]


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
    paid_at: dt.datetime | None = None

    @field_serializer("amount")
    def _serialize_amount(self, value: Decimal) -> str:
        return format_amount(value) or "0"


class InvoiceVerificationOut(BaseModel):
    """Public invoice verification response (for QR code scanning)."""
    invoice_id: str
    status: str
    amount: Decimal
    customer_name: str  # Masked for privacy
    business_name: str
    created_at: dt.datetime
    verified_at: dt.datetime
    authentic: bool = True

    @field_serializer("amount")
    def _serialize_amount(self, value: Decimal) -> str:
        return format_amount(value) or "0"


class InvoiceQuotaOut(BaseModel):
    """Invoice quota information for the authenticated user."""
    current_count: int = Field(description="Number of invoices created this month")
    limit: int | None = Field(description="Monthly invoice limit (None means unlimited)")
    current_plan: str = Field(description="Current subscription plan code")
    can_create: bool = Field(description="Whether user can still create invoices this month")
    upgrade_url: str | None = Field(default=None, description="URL to upgrade subscription plan")


class ReceiptUploadOut(BaseModel):
    """Response after successfully uploading an expense receipt."""
    receipt_url: str = Field(description="S3 URL of the uploaded receipt")
    filename: str = Field(description="Original filename of the uploaded receipt")
