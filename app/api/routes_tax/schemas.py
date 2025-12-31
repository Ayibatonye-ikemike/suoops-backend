"""
Shared Pydantic schemas for tax-related routes.
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class TaxProfileUpdate(BaseModel):
    """Tax profile update request."""

    annual_turnover: Decimal | None = Field(
        None, ge=0, description="Annual turnover in Naira"
    )
    fixed_assets: Decimal | None = Field(
        None, ge=0, description="Fixed assets value in Naira"
    )
    tin: str | None = Field(None, max_length=20, description="Tax Identification Number")
    vat_registration_number: str | None = Field(
        None, max_length=20, description="VAT registration number"
    )
    vat_registered: bool | None = Field(None, description="VAT registration status")


class FiscalizationStatus(BaseModel):
    """Accreditation / fiscalization readiness status response."""

    accredited: bool
    generated_count: int
    pending_external_count: int
    timestamp: str


class DevelopmentLevyResponse(BaseModel):
    """Development levy computation response."""

    user_id: int
    business_size: str
    is_small_business: bool
    assessable_profit: float
    levy_rate_percent: float
    levy_applicable: bool
    levy_amount: float
    exemption_reason: str | None
    period: str | None = None
    source: str | None = None


class AlertEventOut(BaseModel):
    """Alert event output schema."""

    id: int
    category: str
    severity: str
    message: str
    created_at: str | None

    model_config = {"from_attributes": True}
