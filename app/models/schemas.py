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
        return _format_amount(value) or "0"

# ----------------- Auth -----------------

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


class ReceiptUploadOut(BaseModel):
    """Response after successfully uploading an expense receipt."""
    receipt_url: str = Field(description="S3 URL of the uploaded receipt")
    filename: str = Field(description="Original filename of the uploaded receipt")


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


# ----------------- Phone Verification -----------------

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


# ----------------- Invoice Verification -----------------

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
        return _format_amount(value) or "0"

# ----------------- Quota / Feature Gating -----------------

class InvoiceQuotaOut(BaseModel):
    """Invoice quota information for the authenticated user."""
    current_count: int = Field(description="Number of invoices created this month")
    limit: int | None = Field(description="Monthly invoice limit (None means unlimited)")
    current_plan: str = Field(description="Current subscription plan code")
    can_create: bool = Field(description="Whether user can still create invoices this month")
    upgrade_url: str | None = Field(default=None, description="URL to upgrade subscription plan")


# ----------------- OCR -----------------

class OCRItemOut(BaseModel):
    """Single line item extracted from receipt image."""
    description: str
    quantity: int
    unit_price: str


class OCRParseOut(BaseModel):
    """
    Response from OCR parsing of receipt image.
    
    User should review this data before creating invoice.
    """
    success: bool
    customer_name: str
    business_name: str
    amount: str
    currency: str
    items: list[OCRItemOut]
    date: str | None = None
    confidence: Literal["high", "medium", "low"]
    raw_text: str
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "customer_name": "Jane Doe",
                "business_name": "Beauty Palace",
                "amount": "50000",
                "currency": "NGN",
                "items": [
                    {
                        "description": "Hair braiding",
                        "quantity": 1,
                        "unit_price": "50000"
                    }
                ],
                "date": "2025-10-30",
                "confidence": "high",
                "raw_text": "BEAUTY PALACE\nCustomer: Jane Doe\nHair braiding: ₦50,000\nTotal: ₦50,000"
            }
        }
    )



# OAuth / SSO Schemas

class OAuthProviderInfo(BaseModel):
    """Information about an OAuth provider."""
    name: str
    display_name: str
    enabled: bool
    supports_refresh: bool
    icon_url: str | None = None


class OAuthProvidersOut(BaseModel):
    """List of available OAuth providers."""
    providers: list[OAuthProviderInfo]


class OAuthCallbackOut(BaseModel):
    """Response from OAuth callback with JWT tokens."""
    access_token: str
    refresh_token: str
    access_expires_at: dt.datetime
    token_type: str = "bearer"
    redirect_uri: str


# Analytics Schemas

class RevenueMetrics(BaseModel):
    """Revenue breakdown and growth metrics."""
    total_revenue: float
    paid_revenue: float
    pending_revenue: float
    overdue_revenue: float
    growth_rate: float  # Percentage change from previous period
    average_invoice_value: float


class InvoiceMetrics(BaseModel):
    """Invoice counts and conversion metrics."""
    total_invoices: int
    paid_invoices: int
    pending_invoices: int
    awaiting_confirmation: int
    failed_invoices: int
    conversion_rate: float  # Percentage of paid invoices


class CustomerMetrics(BaseModel):
    """Customer engagement metrics."""
    total_customers: int
    active_customers: int  # Customers with invoices in period
    new_customers: int
    repeat_customer_rate: float  # Percentage with multiple invoices


class AgingReport(BaseModel):
    """Accounts receivable aging buckets."""
    current: float  # 0-30 days
    days_31_60: float
    days_61_90: float
    over_90_days: float
    total_outstanding: float


class MonthlyTrend(BaseModel):
    """Monthly revenue, expenses, and profit trend."""
    month: str  # "Jan 2025"
    revenue: float
    expenses: float
    profit: float
    invoice_count: int


class AnalyticsDashboard(BaseModel):
    """Complete analytics dashboard data."""
    period: str
    currency: str
    start_date: dt.date
    end_date: dt.date
    revenue: RevenueMetrics
    invoices: InvoiceMetrics
    customers: CustomerMetrics
    aging: AgingReport
    monthly_trends: list[MonthlyTrend]

