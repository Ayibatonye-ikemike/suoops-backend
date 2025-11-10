"""
Tax and Fiscalization Models (Pre-Fiscalization Integration).

Models for:
- Business tax profiles and classification
- VAT tracking and returns
- Invoice fiscalization data

Note: Field names formerly referencing NRS have been updated to FIRS terminology to
reflect Federal Inland Revenue Service. External API integration is pending; current
fields store provisional registration metadata only.
"""
from enum import Enum
from datetime import datetime, timezone
from typing import Dict
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, JSON, ForeignKey, Numeric, Date
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class BusinessSize(str, Enum):
    """Business size classification based on draft 2026 FIRS thresholds (subject to change)"""
    SMALL = "small"      # Turnover ≤ ₦100M, Assets ≤ ₦250M (Tax exempt)
    MEDIUM = "medium"    # Above small but below large
    LARGE = "large"      # Major corporations


class VATCategory(str, Enum):
    """VAT categories for goods and services (current Nigeria VAT rules; future FIRS enhancements pending)"""
    STANDARD = "standard"        # 7.5% VAT
    ZERO_RATED = "zero_rated"   # 0% VAT (medical, education, basic food)
    EXEMPT = "exempt"            # No VAT (financial services)
    EXPORT = "export"            # 0% for exports


class TaxProfile(Base):
    """
    Business tax profile and compliance tracking.
    
    Tracks:
    - Business classification (small/medium/large)
    - Tax registration numbers (TIN, VAT)
    - Provisional FIRS fiscalization placeholders
    - Compliance status
    """
    __tablename__ = "tax_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), unique=True, nullable=False)
    
    # Business classification (auto-calculated)
    business_size = Column(String(20), default=BusinessSize.SMALL)
    annual_turnover = Column(Numeric(15, 2), default=0)
    fixed_assets = Column(Numeric(15, 2), default=0)
    
    # Tax registration details
    tin = Column(String(20), nullable=True, index=True)
    tin_verified = Column(Boolean, default=False)
    vat_verified = Column(Boolean, default=False)
    verification_status = Column(String(20), default="pending")  # pending, verified, failed
    verification_attempts = Column(Integer, default=0)
    last_verification_at = Column(DateTime, nullable=True)
    vat_registered = Column(Boolean, default=False)
    vat_registration_number = Column(String(20), nullable=True)
    
    # Compliance tracking
    last_vat_return = Column(DateTime, nullable=True)
    last_compliance_check = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Fiscalization / FIRS integration (pending external API availability)
    firs_registered = Column(Boolean, default=False)
    firs_merchant_id = Column(String(50), nullable=True)
    firs_api_key = Column(String(100), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("User", back_populates="tax_profile")
    
    @property
    def is_small_business(self) -> bool:
        """Check if qualifies as small business (≤ ₦100M turnover and ≤ ₦250M assets)"""
        return (
            float(self.annual_turnover or 0) <= 100_000_000 and 
            float(self.fixed_assets or 0) <= 250_000_000
        )
    
    @property
    def tax_rates(self) -> Dict[str, float]:
        """Get applicable tax rates based on business size (provisional 2026 adjustments)"""
        if self.is_small_business:
            return {
                "CIT": 0,           # Company Income Tax - EXEMPT
                "CGT": 0,           # Capital Gains Tax - EXEMPT
                "DEV_LEVY": 0,      # Development Levy - EXEMPT
                "VAT": 7.5          # VAT still applicable
            }
        else:
            return {
                "CIT": 25,          # Company Income Tax
                "CGT": 30,          # Capital Gains Tax (increased 2026)
                "DEV_LEVY": 4,      # New 4% Development Levy
                "VAT": 7.5          # Standard VAT rate
            }

    def mark_verified(self, tin: bool = False, vat: bool = False) -> None:
        """Helper to update verified flags consistently."""
        if tin:
            self.tin_verified = True
        if vat:
            self.vat_verified = True
        if self.tin_verified or self.vat_verified:
            self.verification_status = "verified"


class FiscalInvoice(Base):
    """
    Fiscalized invoice data (provisional FIRS compliance readiness).
    
    Stores:
    - Fiscal codes and signatures
    - QR codes for validation
    - VAT breakdown
    - External transmission metadata (pending accreditation)
    """
    __tablename__ = "fiscal_invoices"
    
    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoice.id"), unique=True, nullable=False)
    
    # Fiscal identifiers
    fiscal_code = Column(String(100), unique=True, nullable=False, index=True)
    fiscal_signature = Column(String(500), nullable=False)
    qr_code_data = Column(String(5000), nullable=False)  # Base64 encoded QR image
    
    # VAT breakdown
    subtotal = Column(Numeric(15, 2), nullable=False)
    vat_rate = Column(Float, default=7.5)
    vat_amount = Column(Numeric(15, 2), nullable=False)
    total_amount = Column(Numeric(15, 2), nullable=False)
    
    # Zero-rated tracking
    zero_rated_amount = Column(Numeric(15, 2), default=0)
    zero_rated_items = Column(JSON, nullable=True)
    
    # Fiscalization transmission tracking (FIRS pending)
    transmitted_at = Column(DateTime, nullable=True)
    firs_response = Column(JSON, nullable=True)
    firs_validation_status = Column(String(20), default="pending")
    firs_transaction_id = Column(String(100), nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    invoice = relationship("Invoice", back_populates="fiscal_data")


class VATReturn(Base):
    """
    Monthly VAT returns (internal aggregation; external submission pipeline pending).
    
    Aggregates:
    - Output VAT (collected from customers)
    - Input VAT (paid to suppliers)
    - Net VAT payable
    - Zero-rated and exempt sales
    """
    __tablename__ = "vat_returns"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    
    # Tax period
    tax_period = Column(String(7), nullable=False, index=True)  # Format: YYYY-MM
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    
    # VAT calculations
    output_vat = Column(Numeric(15, 2), default=0)
    input_vat = Column(Numeric(15, 2), default=0)
    net_vat = Column(Numeric(15, 2), default=0)
    
    # Special categories
    zero_rated_sales = Column(Numeric(15, 2), default=0)
    exempt_sales = Column(Numeric(15, 2), default=0)
    
    # Invoice statistics
    total_invoices = Column(Integer, default=0)
    fiscalized_invoices = Column(Integer, default=0)
    
    # Submission tracking
    status = Column(String(20), default="draft")  # draft, submitted, accepted, rejected
    submitted_at = Column(DateTime, nullable=True)
    firs_submission_id = Column(String(100), nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("User", back_populates="vat_returns")


class MonthlyTaxReport(Base):
    """Tax compliance report metadata supporting multiple time aggregations.

    Stores:
    - Assessable profit & development levy
    - VAT breakdown (taxable, zero-rated, exempt)
    - Generated PDF URL
    - Period type: day, week, month, year
    - Date range: start_date to end_date
    
    Backward compatible with monthly reports (year + month).
    """
    __tablename__ = "monthly_tax_reports"
    __table_args__ = ({},)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    
    # Period type and date range (new fields)
    period_type = Column(String(10), nullable=False, default="month", server_default="month")
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    
    # Legacy fields for backward compatibility (nullable for non-monthly reports)
    year = Column(Integer, nullable=True)
    month = Column(Integer, nullable=True)
    
    # Financial data
    assessable_profit = Column(Numeric(15, 2), default=0)
    levy_amount = Column(Numeric(15, 2), default=0)
    vat_collected = Column(Numeric(15, 2), default=0)
    taxable_sales = Column(Numeric(15, 2), default=0)
    zero_rated_sales = Column(Numeric(15, 2), default=0)
    exempt_sales = Column(Numeric(15, 2), default=0)
    pdf_url = Column(String(500), nullable=True)
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

