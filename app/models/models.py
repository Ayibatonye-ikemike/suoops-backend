from __future__ import annotations

import datetime as dt
import enum
from decimal import Decimal

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class SubscriptionPlan(str, enum.Enum):
    """Subscription tiers with invoice limits."""
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"

    @property
    def invoice_limit(self) -> int | None:
        """Monthly invoice limit for each plan. None = unlimited."""
        limits = {
            SubscriptionPlan.FREE: 5,
            SubscriptionPlan.STARTER: 100,
            SubscriptionPlan.PRO: 1000,
            SubscriptionPlan.BUSINESS: 3000,
            SubscriptionPlan.ENTERPRISE: None,  # Unlimited
        }
        return limits[self]

    @property
    def price(self) -> int:
        """Monthly price in Naira."""
        prices = {
            SubscriptionPlan.FREE: 0,
            SubscriptionPlan.STARTER: 2500,
            SubscriptionPlan.PRO: 7500,
            SubscriptionPlan.BUSINESS: 15000,
            SubscriptionPlan.ENTERPRISE: 50000,
        }
        return prices[self]
    
    @property
    def has_premium_features(self) -> bool:
        """Check if plan has access to premium features (OCR, voice, etc)."""
        return self != SubscriptionPlan.FREE
    
    @property
    def features(self) -> dict:
        """Get feature access for this plan."""
        is_paid = self != SubscriptionPlan.FREE
        return {
            "invoices_per_month": self.invoice_limit,
            "photo_invoice_ocr": is_paid,
            "voice_invoice": is_paid,
            "whatsapp_bot": True,  # Available to all
            "email_notifications": True,  # Available to all
            "pdf_generation": True,  # Available to all
            "custom_branding": is_paid,
            "priority_support": is_paid,
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
    issuer_id: Mapped[int]
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"))  # type: ignore
    amount: Mapped[Decimal] = mapped_column(Numeric(scale=2))
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(scale=2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    due_date: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )
    pdf_url: Mapped[str | None]
    customer: Mapped[Customer] = relationship("Customer", back_populates="invoices")  # type: ignore
    lines: Mapped[list[InvoiceLine]] = relationship(
        "InvoiceLine",
        back_populates="invoice",
        cascade="all, delete-orphan",
    )  # type: ignore


class InvoiceLine(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoice.id"))  # type: ignore
    description: Mapped[str]
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(scale=2))
    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="lines")  # type: ignore


class User(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
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
    # Track monthly invoice usage (resets on 1st of each month)
    invoices_this_month: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Track when usage was last reset (for monthly cycle)
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
