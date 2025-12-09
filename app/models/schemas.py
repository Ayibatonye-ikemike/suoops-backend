"""Backward compatibility redirect for schemas.

DEPRECATED: This module has been refactored into app/models/schemas/
for better SRP compliance and code organization.

All imports should continue to work via this redirect module.
New code should import from app.models.schemas directly.
"""
from app.models.schemas import (
    # Invoice
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
    ReceiptUploadOut,
    # Auth
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
    # Business
    BankDetailsUpdate,
    BankDetailsOut,
    OCRItemOut,
    OCRParseOut,
    OAuthProviderInfo,
    OAuthProvidersOut,
    OAuthCallbackOut,
    # Analytics
    RevenueMetrics,
    InvoiceMetrics,
    CustomerMetrics,
    AgingReport,
    MonthlyTrend,
    AnalyticsDashboard,
)

# Also export the format function for backward compat
from app.models.schemas.utils import format_amount as _format_amount

__all__ = [
    "InvoiceLineIn", "InvoiceCreate", "CustomerOut", "InvoiceOut",
    "InvoiceLineOut", "InvoiceOutDetailed", "InvoiceStatusUpdate",
    "InvoicePublicOut", "InvoiceVerificationOut", "InvoiceQuotaOut",
    "ReceiptUploadOut", "OTPPhoneRequest", "OTPEmailRequest",
    "SignupStart", "SignupVerify", "LoginVerify", "OTPResend",
    "UserOut", "TokenOut", "RefreshRequest", "MessageOut",
    "PhoneVerificationRequest", "PhoneVerificationVerify",
    "PhoneVerificationResponse", "BankDetailsUpdate", "BankDetailsOut",
    "OCRItemOut", "OCRParseOut", "OAuthProviderInfo", "OAuthProvidersOut",
    "OAuthCallbackOut", "RevenueMetrics", "InvoiceMetrics",
    "CustomerMetrics", "AgingReport", "MonthlyTrend", "AnalyticsDashboard",
    "_format_amount",
]
