from __future__ import annotations

import datetime as dt
import enum
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.tax_models import FiscalInvoice, TaxProfile, VATReturn
    from app.models.oauth_models import OAuthToken
    from app.models.payment_models import PaymentTransaction
    from app.models.inventory_models import Product, ProductCategory, StockMovement, Supplier, PurchaseOrder
else:
    # Import at runtime for SQLAlchemy relationship resolution
    from app.models import tax_models  # noqa: F401
    from app.models import oauth_models  # noqa: F401
    from app.models import payment_models  # noqa: F401
    from app.models import inventory_models  # noqa: F401
    FiscalInvoice = "FiscalInvoice"
    TaxProfile = "TaxProfile"
    VATReturn = "VATReturn"
    OAuthToken = "OAuthToken"
    Product = "Product"
    ProductCategory = "ProductCategory"
    StockMovement = "StockMovement"
    Supplier = "Supplier"
    PurchaseOrder = "PurchaseOrder"


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class SubscriptionPlan(str, enum.Enum):
    """Subscription tiers with invoice limits."""
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    BUSINESS = "business"

    @property
    def invoice_limit(self) -> int:
        """Monthly invoice limit for each plan."""
        limits = {
            SubscriptionPlan.FREE: 5,
            SubscriptionPlan.STARTER: 100,
            SubscriptionPlan.PRO: 200,
            SubscriptionPlan.BUSINESS: 300,
        }
        return limits[self]

    @property
    def price(self) -> int:
        """Monthly price in Naira."""
        prices = {
            SubscriptionPlan.FREE: 0,
            SubscriptionPlan.STARTER: 4500,
            SubscriptionPlan.PRO: 8000,
            SubscriptionPlan.BUSINESS: 16000,
        }
        return prices[self]
    
    @property
    def has_premium_features(self) -> bool:
        """Check if plan has access to premium features (OCR, voice, etc)."""
        return self != SubscriptionPlan.FREE
    
    @property
    def features(self) -> dict:
        """
        Get feature access for this plan.
        
        Feature gates:
        - FREE: Manual invoices only (5/month)
        - STARTER: + Tax reports & automation
        - PRO: + Custom logo branding + Priority support + Inventory + Team Management
        - BUSINESS: + Voice invoices (15/mo) + Photo OCR (15/mo) + API access
        """
        return {
            "invoices_per_month": self.invoice_limit,
            "whatsapp_bot": True,  # Available to all
            "email_notifications": True,  # Available to all
            "pdf_generation": True,  # Available to all
            "qr_verification": True,  # Available to all
            # Tax features: Starter+
            "tax_automation": self in (SubscriptionPlan.STARTER, SubscriptionPlan.PRO, SubscriptionPlan.BUSINESS),
            "tax_reports": self in (SubscriptionPlan.STARTER, SubscriptionPlan.PRO, SubscriptionPlan.BUSINESS),
            # Custom branding: Pro+
            "custom_branding": self in (SubscriptionPlan.PRO, SubscriptionPlan.BUSINESS),
            # Inventory management: Pro+
            "inventory": self in (SubscriptionPlan.PRO, SubscriptionPlan.BUSINESS),
            # Team management: Pro+ (invite up to 3 team members)
            "team_management": self in (SubscriptionPlan.PRO, SubscriptionPlan.BUSINESS),
            # Priority support: Pro+
            "priority_support": self in (SubscriptionPlan.PRO, SubscriptionPlan.BUSINESS),
            # Voice & OCR: Business only (15/mo quota)
            "voice_invoice": self == SubscriptionPlan.BUSINESS,
            "photo_invoice_ocr": self == SubscriptionPlan.BUSINESS,
            "voice_ocr_quota": 15 if self == SubscriptionPlan.BUSINESS else 0,
            # API access: Business only
            "api_access": self == SubscriptionPlan.BUSINESS,
        }


class Customer(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None]
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    invoices: Mapped[list[Invoice]] = relationship("Invoice", back_populates="customer")  # type: ignore


class Invoice(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    issuer_id: Mapped[int] = mapped_column(ForeignKey("user.id"))  # type: ignore
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"))  # type: ignore
    amount: Mapped[Decimal] = mapped_column(Numeric(scale=2))
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(scale=2), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    due_date: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )
    pdf_url: Mapped[str | None]
    # When customer payment is confirmed and invoice marked paid
    paid_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Separate receipt PDF (with PAID watermark)
    receipt_pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    # VAT and fiscalization fields (NRS 2026 compliance)
    vat_rate: Mapped[float | None] = mapped_column(default=7.5)
    vat_amount: Mapped[Decimal | None] = mapped_column(Numeric(scale=2), default=0)
    vat_category: Mapped[str | None] = mapped_column(String(20), default="standard")
    is_fiscalized: Mapped[bool] = mapped_column(default=False)
    fiscal_code: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True, index=True)
    
    # Unified Invoice/Expense fields (revenue or expense tracking)
    invoice_type: Mapped[str] = mapped_column(String(20), default="revenue", index=True)  # "revenue" or "expense"
    category: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)  # For expenses: rent, utilities, etc.
    vendor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)  # For expenses: supplier name
    merchant: Mapped[str | None] = mapped_column(String(200), nullable=True)  # Merchant/vendor alternative field
    receipt_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Receipt image/PDF URL
    receipt_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # OCR extracted text
    input_method: Mapped[str | None] = mapped_column(String(20), nullable=True)  # voice, text, photo, manual
    channel: Mapped[str | None] = mapped_column(String(20), nullable=True)  # whatsapp, email, dashboard
    verified: Mapped[bool | None] = mapped_column(default=False, nullable=True)  # For expense verification
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # Additional notes
    
    # Track which user actually created the invoice (for team scenarios - allows confirmation only by creator)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True, index=True)
    
    # Track which user last updated the invoice status (paid/cancelled)
    status_updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True, index=True)
    status_updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    customer: Mapped[Customer] = relationship("Customer", back_populates="invoices")  # type: ignore
    issuer: Mapped[User] = relationship("User", back_populates="issued_invoices", foreign_keys=[issuer_id])  # type: ignore
    created_by: Mapped[User | None] = relationship("User", foreign_keys=[created_by_user_id])  # type: ignore
    status_updated_by: Mapped[User | None] = relationship("User", foreign_keys=[status_updated_by_user_id])  # type: ignore
    lines: Mapped[list[InvoiceLine]] = relationship(
        "InvoiceLine",
        back_populates="invoice",
        cascade="all, delete-orphan",
    )  # type: ignore
    fiscal_data: Mapped[FiscalInvoice | None] = relationship(
        "FiscalInvoice",
        back_populates="invoice",
        uselist=False,
    )  # type: ignore


class InvoiceLine(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoice.id"))  # type: ignore
    description: Mapped[str]
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(scale=2))
    # Link to inventory product for automatic stock tracking
    product_id: Mapped[int | None] = mapped_column(ForeignKey("product.id"), nullable=True, index=True)
    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="lines")  # type: ignore
    product: Mapped["Product | None"] = relationship("Product", foreign_keys=[product_id])  # type: ignore


class User(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    # Encrypted email (Fernet) stored separately; plaintext email remains in `email` for now.
    # Future policy may remove plaintext after full migration & token flows updated.
    email_enc: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone_verified: Mapped[bool] = mapped_column(default=False, server_default="false")
    last_login: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )
    # Subscription plan with default FREE tier
    plan: Mapped[SubscriptionPlan] = mapped_column(
        Enum(SubscriptionPlan),
        default=SubscriptionPlan.FREE,
        server_default="free",
        nullable=False,
    )
    # When the current paid subscription expires (NULL for free tier)
    subscription_expires_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    # When the current paid subscription started (for billing cycle calculations)
    subscription_started_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # Track monthly invoice usage (resets based on subscription start, not calendar month)
    invoices_this_month: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Track when usage was last reset (for billing cycle)
    usage_reset_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )
    # Business bank account details (shown on invoices for customer payments)
    business_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    account_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Business branding
    logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Role-based access control (RBAC) role; defaults to 'user'.
    # Values: 'user', 'staff', 'admin'. Additional roles can be added via migration.
    role: Mapped[str] = mapped_column(String(20), default="user", server_default="user", index=True)
    
    # Tax and compliance relationships
    tax_profile: Mapped[TaxProfile | None] = relationship(
        "TaxProfile",
        back_populates="user",
        uselist=False,
    )  # type: ignore
    vat_returns: Mapped[list[VATReturn]] = relationship(
        "VATReturn",
        back_populates="user",
    )  # type: ignore
    # Invoices issued by this user (as business)
    issued_invoices: Mapped[list[Invoice]] = relationship(
        "Invoice",
        back_populates="issuer",
        foreign_keys="Invoice.issuer_id",
    )  # type: ignore
    # Note: Expenses are now tracked as invoices with invoice_type='expense'
    # The separate Expense table is deprecated but kept for backward compatibility
    
    # Payment transactions for subscription billing
    payment_transactions: Mapped[list["PaymentTransaction"]] = relationship(
        "PaymentTransaction",
        back_populates="user",
        foreign_keys="[PaymentTransaction.user_id]",
        cascade="all, delete-orphan",
    )  # type: ignore
    
    # OAuth tokens for SSO authentication
    oauth_tokens: Mapped[list["OAuthToken"]] = relationship(
        "OAuthToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )  # type: ignore
    
    # Inventory management relationships
    products: Mapped[list["Product"]] = relationship(
        "Product",
        back_populates="user",
        cascade="all, delete-orphan",
    )  # type: ignore
    
    product_categories: Mapped[list["ProductCategory"]] = relationship(
        "ProductCategory",
        back_populates="user",
        cascade="all, delete-orphan",
    )  # type: ignore
    
    stock_movements: Mapped[list["StockMovement"]] = relationship(
        "StockMovement",
        back_populates="user",
        cascade="all, delete-orphan",
    )  # type: ignore
    
    suppliers: Mapped[list["Supplier"]] = relationship(
        "Supplier",
        back_populates="user",
        cascade="all, delete-orphan",
    )  # type: ignore
    
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(
        "PurchaseOrder",
        back_populates="user",
        cascade="all, delete-orphan",
    )  # type: ignore


class WebhookEvent(Base):
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_webhookevent_provider_external_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    external_id: Mapped[str] = mapped_column(String(120))
    signature: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )
