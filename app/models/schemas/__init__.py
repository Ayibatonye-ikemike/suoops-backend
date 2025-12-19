"""Pydantic schemas for API requests and responses.

Refactored from monolithic schemas.py for SRP compliance.

Sub-modules:
- invoice: Invoice-related schemas
- auth: Authentication schemas
- business: Bank, OAuth, OCR schemas
- analytics: Analytics schemas
- utils: Common utility functions
"""
# Invoice schemas
from .invoice import (
    InvoiceLineIn,
    InvoiceCreate,
    CustomerOut,
    InvoiceOut,
    InvoiceLineOut,
    InvoiceOutDetailed,
    InvoiceStatusUpdate,
    InvoicePublicOut,
    InvoiceVerificationOut,
    InvoiceQuotaOut,
    InvoicePackPurchaseInitOut,
    ReceiptUploadOut,
)

# Auth schemas
from .auth import (
    OTPPhoneRequest,
    OTPEmailRequest,
    SignupStart,
    SignupVerify,
    LoginVerify,
    OTPResend,
    UserOut,
    TokenOut,
    RefreshRequest,
    MessageOut,
    PhoneVerificationRequest,
    PhoneVerificationVerify,
    PhoneVerificationResponse,
)

# Business schemas
from .business import (
    BankDetailsUpdate,
    BankDetailsOut,
    OCRItemOut,
    OCRParseOut,
    OAuthProviderInfo,
    OAuthProvidersOut,
    OAuthCallbackOut,
)

# Analytics schemas
from .analytics import (
    RevenueMetrics,
    InvoiceMetrics,
    CustomerMetrics,
    AgingReport,
    MonthlyTrend,
    AnalyticsDashboard,
)

__all__ = [
    # Invoice
    "InvoiceLineIn",
    "InvoiceCreate",
    "CustomerOut",
    "InvoiceOut",
    "InvoiceLineOut",
    "InvoiceOutDetailed",
    "InvoiceStatusUpdate",
    "InvoicePublicOut",
    "InvoiceVerificationOut",
    "InvoiceQuotaOut",
    "InvoicePackPurchaseInitOut",
    "ReceiptUploadOut",
    # Auth
    "OTPPhoneRequest",
    "OTPEmailRequest",
    "SignupStart",
    "SignupVerify",
    "LoginVerify",
    "OTPResend",
    "UserOut",
    "TokenOut",
    "RefreshRequest",
    "MessageOut",
    "PhoneVerificationRequest",
    "PhoneVerificationVerify",
    "PhoneVerificationResponse",
    # Business
    "BankDetailsUpdate",
    "BankDetailsOut",
    "OCRItemOut",
    "OCRParseOut",
    "OAuthProviderInfo",
    "OAuthProvidersOut",
    "OAuthCallbackOut",
    # Analytics
    "RevenueMetrics",
    "InvoiceMetrics",
    "CustomerMetrics",
    "AgingReport",
    "MonthlyTrend",
    "AnalyticsDashboard",
]
