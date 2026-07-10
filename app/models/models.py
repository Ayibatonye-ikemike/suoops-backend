from __future__ import annotations

import datetime as dt
import enum
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.inventory_models import (
        Product,
        ProductCategory,
        PurchaseOrder,
        StockMovement,
        Supplier,
    )
    from app.models.oauth_models import OAuthToken
    from app.models.payment_models import PaymentTransaction
    from app.models.referral_models import ReferralCode, ReferralReward
    from app.models.tax_models import FiscalInvoice, TaxProfile, VATReturn
else:
    # Import at runtime for SQLAlchemy relationship resolution
    from app.models import (
        inventory_models,  # noqa: F401
        oauth_models,  # noqa: F401
        payment_models,  # noqa: F401
        referral_models,  # noqa: F401
        tax_models,  # noqa: F401
    )
    FiscalInvoice = "FiscalInvoice"
    TaxProfile = "TaxProfile"
    VATReturn = "VATReturn"
    OAuthToken = "OAuthToken"
    Product = "Product"
    ProductCategory = "ProductCategory"
    StockMovement = "StockMovement"
    Supplier = "Supplier"
    PurchaseOrder = "PurchaseOrder"
    ReferralCode = "ReferralCode"
    ReferralReward = "ReferralReward"


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class SubscriptionPlan(str, enum.Enum):
    """Subscription tiers for feature access.
    
    BILLING MODEL (Small & Medium Business Focus):
    - Invoice Packs: 50 invoices for ₦1,250 (one-time, doesn't expire)
    - FREE: 2 free invoices to start, then buy invoice packs as needed
    - PRO: ₦2,000 Pro Pack (20 invoices + 30 days) for all premium features including voice/API
    
    Note: STARTER plan removed - FREE users get 2 free invoices and can buy
    packs without needing a plan change. Frontend shows "Starter" as UX label.
    Note: BUSINESS plan removed - we focus on businesses under ₦100M annual revenue.
    PRO now includes all features that were previously BUSINESS-only.
    """
    FREE = "free"
    PRO = "pro"
    # STARTER removed - no need for plan toggle, users just buy invoice packs
    # BUSINESS removed - all users migrated to PRO

    @property
    def monthly_price(self) -> int:
        """Pro features price in Naira (prepaid, not recurring).
        
        FREE has no fee - users just buy invoice packs.
        Pro is prepaid: ₦2,000 Pro Pack (20 invoices + 30 days of premium
        features) or ₦1,500 Pro Features pass (30 days, features only).
        """
        prices = {
            SubscriptionPlan.FREE: 0,
            SubscriptionPlan.PRO: 2000,  # Pro Pack: 20 invoices + 30 days Pro features
        }
        return prices.get(self, 0)
    
    @property
    def price(self) -> int:
        """Alias for monthly_price for backward compatibility."""
        return self.monthly_price
    
    @property
    def invoices_included(self) -> int:
        """Number of invoices included with monthly subscription.
        
        Pro plan includes 50 invoices per month.
        Free users get 2 free invoices to start, then buy packs.
        """
        if self == SubscriptionPlan.PRO:
            return 50
        return 0

    @property
    def has_monthly_subscription(self) -> bool:
        """Check if plan requires monthly subscription payment."""
        return self == SubscriptionPlan.PRO
    
    @property
    def has_premium_features(self) -> bool:
        """All features are free under the commission model (Pro removed)."""
        return True
    
    @property
    def features(self) -> dict:
        """
        Get feature access for this plan.
        
        BILLING MODEL (Small & Medium Business Focus):
        - FREE: 2 free invoices to start, buy packs as needed, basic features
        - PRO: ₦2,000 Pro Pack = 20 invoices + 30 days of ALL premium features (incl. tax)
        
        Note: STARTER removed - FREE users get 2 free invoices and buy packs.
        Note: BUSINESS plan removed - PRO now includes voice.
        Note: Tax reports & automation require PRO plan.
        """
        return {
            "invoice_pack_price": 1250,  # ₦1,250 per 50 invoices
            "invoice_pack_size": 50,  # 50 invoices per pack
            "whatsapp_bot": True,  # Available to all
            "email_notifications": True,  # Available to all
            "pdf_generation": True,  # Available to all
            "qr_verification": True,  # Available to all
            # Commission model (Pro removed): every feature is free for all users.
            "tax_automation": True,
            "tax_reports": True,
            "custom_branding": True,
            "inventory": True,
            "team_management": True,
            "priority_support": True,
            "voice_invoice": True,
            "voice_quota": 15,
            "cash_dashboard": True,
            "customer_insights": True,
            "professionalism_score": True,
            "margin_insights": True,
            "daily_summary": True,
        }


class Customer(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None]
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    # WhatsApp opt-in: True if customer has replied to our bot (can receive messages)
    whatsapp_opted_in: Mapped[bool] = mapped_column(default=False)
    invoices: Mapped[list[Invoice]] = relationship("Invoice", back_populates="customer")  # type: ignore


class Invoice(Base):
    __table_args__ = (
        Index("ix_invoice_issuer_wa_pending", "issuer_id", "whatsapp_delivery_pending"),
        Index("ix_invoice_customer_status", "customer_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    issuer_id: Mapped[int] = mapped_column(ForeignKey("user.id"))  # type: ignore
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"), index=True)  # type: ignore
    amount: Mapped[Decimal] = mapped_column(Numeric(scale=2))
    currency: Mapped[str] = mapped_column(String(3), default="NGN", server_default="NGN")  # NGN or USD
    # WhatsApp delivery pending: True if waiting for customer to opt-in before sending
    whatsapp_delivery_pending: Mapped[bool] = mapped_column(default=False, index=True)
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(scale=2), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    due_date: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
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
    invoice_type: Mapped[str] = mapped_column(
        String(20),
        default="revenue",
        index=True,
    )  # "revenue" or "expense"
    # For expenses: rent, utilities, etc.
    category: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
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
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoice.id"), index=True)  # type: ignore
    description: Mapped[str]
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(scale=2))
    # Link to inventory product for automatic stock tracking
    product_id: Mapped[int | None] = mapped_column(ForeignKey("product.id"), nullable=True, index=True)
    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="lines")  # type: ignore
    product: Mapped[Product | None] = relationship("Product", foreign_keys=[product_id])  # type: ignore


class User(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    # Encrypted email (Fernet) stored separately; plaintext email remains in `email` for now.
    # Future policy may remove plaintext after full migration & token flows updated.
    email_enc: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone_verified: Mapped[bool] = mapped_column(default=False, server_default="false")
    # OTP for phone verification (temporary, cleared after verification)
    phone_otp: Mapped[str | None] = mapped_column(String(6), nullable=True)
    last_login: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        index=True,
    )
    # Subscription plan with default FREE tier
    plan: Mapped[SubscriptionPlan] = mapped_column(
        Enum(SubscriptionPlan),
        default=SubscriptionPlan.FREE,
        server_default="free",
        nullable=False,
        index=True,
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
    # Invoice balance: purchased invoices available to use (100 invoices = ₦2,500 pack)
    # Decremented when creating revenue invoices. Users buy packs to replenish.
    invoice_balance: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    # Prepaid wallet balance in KOBO. Manual invoices deduct max(3% of amount,
    # ₦20) at creation; this is the active billing field. New signups start with
    # a ₦60 starter wallet (≨32 small invoices’ worth of goodwill). invoice_balance
    # above is legacy (its value was migrated into this wallet at ₦30/credit).
    wallet_balance_kobo: Mapped[int] = mapped_column(Integer, default=6000, server_default="6000")
    # Legacy field - kept for backward compatibility, will be deprecated
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
    
    # Referral payout bank account (separate from business bank for commission payouts)
    payout_bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payout_account_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    payout_account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Paystack subscription tracking (for auto-recurring billing)
    paystack_subscription_code: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    paystack_customer_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Paystack Transfer Recipient (RCP_...) for escrow payouts — created from the
    # business's payout/bank details; reused for every storefront-order release.
    paystack_recipient_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Escrow payouts are frozen until this time after a payout/bank-details change
    # (anti-account-takeover). NULL = not frozen.
    payout_frozen_until: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # When the business accepted the Terms & Conditions (incl. buyer-protection /
    # escrow policy) at signup. NULL = legacy account created before T&C gating.
    terms_accepted_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Paystack subaccount for online payments / marketplace splits. Created from
    # the business's bank details; each sale settles to their bank minus the
    # platform commission. `active` is True once the subaccount is verified.
    paystack_subaccount_code: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    paystack_subaccount_active: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)

    # Public storefront: a shareable catalog of the business's inventory.
    storefront_enabled: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)
    storefront_slug: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True, unique=True)
    # Short public description of what the shop sells (shown in the directory).
    storefront_description: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # Location — shown on the store page + powers "get directions".
    storefront_address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    storefront_city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    storefront_state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Weekly opening hours: {"0": {"open": "09:00", "close": "18:00"}, ...} (0=Mon).
    storefront_hours: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Single editable promo/announcement banner shown atop the store.
    storefront_announcement: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Discovery analytics — incremented on each public store view.
    storefront_views: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    # Precise business location (GPS-captured at storefront setup). Powers the
    # escrow same/different-state window and future delivery pickup point.
    storefront_lat: Mapped[float | None] = mapped_column(nullable=True)
    storefront_lng: Mapped[float | None] = mapped_column(nullable=True)

    # ── Storefront moderation (Trust & Safety) ──
    # Lifecycle of the public store as seen by admins/customers:
    #   active     — normal; store is discoverable & reachable.
    #   suspended  — temporarily hidden (policy warning / under review). Reversible.
    #   delisted   — removed from the marketplace for failing our criteria. Reversible
    #                by an admin but treated as a hard takedown for the customer.
    # Enforced on the public storefront + directory routes.
    store_status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active", nullable=False, index=True
    )
    store_status_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    store_status_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # AdminUser.id that last changed the store status (nullable; no hard FK to keep
    # the admin schema decoupled from the core user table).
    store_status_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Anti-fraud / duplicate-account signals (captured at signup) ──
    signup_ip: Mapped[str | None] = mapped_column(String(45), nullable=True, index=True)
    # Client-supplied device fingerprint (hashed on the client). Used to link
    # multiple accounts created from the same browser/device.
    signup_device_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    signup_user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    # Heuristic 0-100 risk score computed at signup (higher = riskier).
    risk_score: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    # List of triggered risk signal codes, e.g. ["ip_velocity", "device_reuse"].
    risk_signals: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # True when the account needs manual Trust & Safety review.
    flagged_for_review: Mapped[bool] = mapped_column(
        default=False, server_default="false", nullable=False, index=True
    )
    # Count of storefront-messaging attempts to move a deal off-platform (share
    # contact/account or push a direct transfer). Enough of them flags the seller.
    circumvention_attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    # Business branding
    logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Role-based access control (RBAC) role; defaults to 'user'.
    # Values: 'user', 'staff', 'admin'. Additional roles can be added via migration.
    role: Mapped[str] = mapped_column(String(20), default="user", server_default="user", index=True)
    
    # Admin-granted PRO feature access (without subscription or invoice packs).
    # When True, user.effective_plan returns PRO for feature gating purposes,
    # but the actual `plan` field and `invoice_balance` are unchanged.
    pro_override: Mapped[bool] = mapped_column(default=False, server_default="false")
    
    # Currency preference for WhatsApp bot + dashboard display: "NGN" or "USD"
    preferred_currency: Mapped[str] = mapped_column(
        String(3), default="NGN", server_default="NGN"
    )

    # Attribution: where the user came from (google_ads, instagram, whatsapp_ad,
    # social_media, referral, google_oauth, organic, etc.)
    signup_source: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )

    @property
    def effective_plan(self) -> SubscriptionPlan:
        """Return the plan used for feature gating.

        If pro_override is True, treat user as PRO regardless of actual plan.
        This does NOT affect invoice_balance or subscription billing.
        """
        if self.pro_override:
            return SubscriptionPlan.PRO
        return self.plan

    @property
    def online_payments_active(self) -> bool:
        """True when this business can be paid online via its Paystack subaccount.

        When active, invoices are online-only: the business's raw bank account is
        hidden from customers so payments flow through Paystack (commission).
        """
        return bool(self.paystack_subaccount_active and self.paystack_subaccount_code)

    @property
    def storefront_visible(self) -> bool:
        """True when the public storefront should be discoverable & reachable.

        A store must be opted-in AND not suspended/delisted by Trust & Safety.
        """
        return bool(self.storefront_enabled and self.store_status == "active")

    # Tax and compliance relationships
    tax_profile: Mapped[TaxProfile | None] = relationship(
        "TaxProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )  # type: ignore
    vat_returns: Mapped[list[VATReturn]] = relationship(
        "VATReturn",
        back_populates="user",
        cascade="all, delete-orphan",
    )  # type: ignore
    # Invoices issued by this user (as business)
    issued_invoices: Mapped[list[Invoice]] = relationship(
        "Invoice",
        back_populates="issuer",
        foreign_keys="Invoice.issuer_id",
        cascade="all, delete-orphan",
    )  # type: ignore
    # Note: Expenses are now tracked as invoices with invoice_type='expense'
    # The separate Expense table is deprecated but kept for backward compatibility
    
    # Payment transactions for subscription billing
    payment_transactions: Mapped[list[PaymentTransaction]] = relationship(
        "PaymentTransaction",
        back_populates="user",
        foreign_keys="[PaymentTransaction.user_id]",
        cascade="all, delete-orphan",
    )  # type: ignore
    
    # OAuth tokens for SSO authentication
    oauth_tokens: Mapped[list[OAuthToken]] = relationship(
        "OAuthToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )  # type: ignore
    
    # Inventory management relationships
    products: Mapped[list[Product]] = relationship(
        "Product",
        back_populates="user",
        cascade="all, delete-orphan",
    )  # type: ignore
    
    product_categories: Mapped[list[ProductCategory]] = relationship(
        "ProductCategory",
        back_populates="user",
        cascade="all, delete-orphan",
    )  # type: ignore
    
    stock_movements: Mapped[list[StockMovement]] = relationship(
        "StockMovement",
        back_populates="user",
        cascade="all, delete-orphan",
    )  # type: ignore
    
    suppliers: Mapped[list[Supplier]] = relationship(
        "Supplier",
        back_populates="user",
        cascade="all, delete-orphan",
    )  # type: ignore
    
    purchase_orders: Mapped[list[PurchaseOrder]] = relationship(
        "PurchaseOrder",
        back_populates="user",
        cascade="all, delete-orphan",
    )  # type: ignore
    
    # Referral system relationships
    referral_code: Mapped[ReferralCode | None] = relationship(
        "ReferralCode",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )  # type: ignore
    
    referral_rewards: Mapped[list[ReferralReward]] = relationship(
        "ReferralReward",
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


class UserEmailLog(Base):
    """Tracks lifecycle/drip emails sent to users to prevent duplicates."""

    __tablename__ = "user_email_log"
    __table_args__ = (
        UniqueConstraint("user_id", "email_type", name="uq_user_email_log_user_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    email_type: Mapped[str] = mapped_column(String(60), index=True)
    sent_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )


class EmailSuppression(Base):
    """Email addresses suppressed due to a hard bounce or spam complaint.

    Populated from SES/SNS bounce + complaint notifications. The send path
    checks this table and skips suppressed addresses to protect domain
    sending reputation. Keyed by lowercased email (covers both platform
    users and invoice-recipient customers).
    """

    __tablename__ = "email_suppression"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    reason: Mapped[str] = mapped_column(String(40))  # 'bounce' | 'complaint'
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(20), server_default="ses")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )


class InvoiceReminderLog(Base):
    """Tracks payment reminders sent per invoice to prevent duplicates.

    Each (invoice_id, reminder_type, channel) combination is unique so
    we never spam the same reminder twice.

    reminder_type values:
      - customer_pre_due      (3 days before due)
      - customer_due_today    (due date)
      - customer_overdue_1d   (1 day past due)
      - customer_overdue_7d   (7 days past due)
      - customer_overdue_14d  (14+ days past due)
      - owner_light           (1-3 days overdue — nudge)
      - owner_action          (4-7 days overdue — action required)
      - owner_urgent          (8-14 days overdue — escalation)
      - owner_critical        (14+ days overdue — final warning)
    """

    __tablename__ = "invoice_reminder_log"
    __table_args__ = (
        UniqueConstraint(
            "invoice_id",
            "reminder_type",
            "channel",
            name="uq_invoice_reminder_type_channel",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoice.id", ondelete="CASCADE"),
        index=True,
    )
    reminder_type: Mapped[str] = mapped_column(String(30))
    channel: Mapped[str] = mapped_column(String(20))  # whatsapp, email
    recipient: Mapped[str] = mapped_column(String(255))
    sent_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )


class Testimonial(Base):
    """User-submitted testimonial/feedback for the landing page.

    Workflow:
    1. Authenticated user submits via POST /testimonials
    2. Admin approves via PATCH /admin/testimonials/{id}
    3. Approved testimonials shown on public landing page via GET /public/testimonials
    """

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, default=5)  # 1-5 stars
    approved: Mapped[bool] = mapped_column(default=False, index=True)
    featured: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship("User")


class StorefrontStockNotification(Base):
    """A "notify me when back in stock" request from a storefront visitor."""

    __tablename__ = "storefront_stock_notification"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)  # store owner
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"), index=True)
    phone: Mapped[str] = mapped_column(String(20))
    notified: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )


class StorefrontReview(Base):
    """A customer review of a storefront, gated to buyers who actually paid."""

    __tablename__ = "storefront_review"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)  # store owner
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer.id"), nullable=True)
    rating: Mapped[int] = mapped_column(Integer)  # 1-5 stars
    text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewer_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved: Mapped[bool] = mapped_column(default=True, server_default="true", nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )


class StorefrontOrderEscrow(Base):
    """Buyer-protection hold for a storefront order (channel='storefront').

    The customer's payment is collected to the SuoOps Paystack balance and HELD.
    The seller is paid out (via Paystack Transfer, minus commission) only when
    the buyer confirms receipt OR the dispute window elapses with no report.
    On a valid non-delivery dispute the buyer is refunded and the seller is not
    paid. One row per storefront order (invoice).

    Window: 12h when customer & business are in the same state, else 3 days.
    """

    __tablename__ = "storefront_order_escrow"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The storefront order this hold belongs to (one-to-one with the invoice).
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoice.id", ondelete="CASCADE"), unique=True, index=True
    )
    seller_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)  # the business

    # held | released | refunded | disputed | canceled
    status: Mapped[str] = mapped_column(
        String(20), default="held", server_default="held", nullable=False, index=True
    )

    # ── Release window ──
    same_state: Mapped[bool | None] = mapped_column(nullable=True)
    # When the seller becomes eligible for auto-payout (paid_at + 12h/3d).
    release_due_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # Earliest time the payout may actually execute (T+1 settlement cadence) — the
    # daily settlement run after this pays the seller. Buyer protection ending or
    # an early confirmation clears the order, but the money still settles next day
    # from settled collections, never same-day float.
    settle_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # ── Amounts (kobo) ──
    gross_kobo: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    fee_kobo: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)  # SuoOps 3%
    payout_kobo: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)  # to seller

    # ── Location snapshots (drive the window + audit; server-derived state) ──
    business_state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    customer_state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    customer_lat: Mapped[float | None] = mapped_column(nullable=True)
    customer_lng: Mapped[float | None] = mapped_column(nullable=True)

    # ── Lifecycle timestamps ──
    confirmed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # buyer "received"
    released_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disputed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dispute_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Paystack payout / refund tracking ──
    transfer_recipient_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    transfer_reference: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    # Which payout rail the transfer_reference was sent on. A reference is only
    # valid on its own provider, so if the payout rail changes (e.g. an early
    # Paystack attempt that failed on balance, then routed to Flutterwave), the
    # old reference is void and a fresh transfer must be sent — never reconciled
    # against the wrong provider.
    transfer_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    refund_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # The original Paystack charge reference (INVPAY-…) — needed to refund the buyer.
    charge_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Delivery confirmation code shown ONLY to the buyer (never the seller) — an
    # early release requires it, so a hijacked store can't self-confirm delivery.
    confirmation_code: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    # Anti-fraud hold: collusion/anomaly-flagged orders never auto-release; they
    # wait for an admin decision in the disputes queue.
    held_for_review: Mapped[bool] = mapped_column(
        default=False, server_default="false", nullable=False
    )
    review_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # ── Seller-side delivery proof (defends against false "not delivered" claims) ──
    seller_marked_delivered_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivery_proof_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delivery_proof_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Seller-side DISPATCH proof (recorded at send-out, before delivery) ──
    # Symmetric to buyer protection: the seller logs when they sent the package,
    # the courier/waybill tracking code, and a photo of the packaged item. This
    # is an auditable handoff step (dispatch → delivery → release) and lets the
    # buyer see their order is on the way.
    seller_dispatched_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dispatch_tracking: Mapped[str | None] = mapped_column(String(120), nullable=True)
    dispatch_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dispatch_proof_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=utcnow, nullable=True
    )


class BuyerReputation(Base):
    """Global (cross-business) reputation for a storefront buyer, keyed by phone.

    Deters buyers who receive goods then falsely claim non-delivery: every
    dispute is counted, and disputes an admin rules against the buyer (releases
    to the seller) are counted as ``false_disputes``. A buyer over the abuse
    threshold is flagged so their future reports get extra scrutiny.
    """

    __tablename__ = "buyer_reputation"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    disputes: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    false_disputes: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    flagged: Mapped[bool] = mapped_column(
        default=False, server_default="false", nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=utcnow, nullable=True
    )


class OrderMessage(Base):
    """An order-scoped message between a storefront buyer and seller.

    Exists only for a real order (tied to its escrow) and only while the order is
    live (held). Every message is scanned before delivery: leak vectors
    (phone/account/email/links + the buyer-only delivery code) are masked into
    ``body_redacted`` (what the other party sees), the exact text is kept in
    ``body_raw`` for dispute evidence (admin-only), and clear off-platform pushes
    are ``blocked`` (stored, never delivered). ``flag_reasons`` feeds seller trust.
    """

    __tablename__ = "order_message"

    id: Mapped[int] = mapped_column(primary_key=True)
    escrow_id: Mapped[int] = mapped_column(
        ForeignKey("storefront_order_escrow.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # "buyer" | "seller" | "system".
    sender_role: Mapped[str] = mapped_column(String(10), nullable=False)
    # The seller's user id when sender_role == "seller"; None for buyer/system.
    sender_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"), nullable=True, index=True
    )
    body_raw: Mapped[str] = mapped_column(Text, nullable=False)  # admin-only
    body_redacted: Mapped[str] = mapped_column(Text, nullable=False)  # delivered
    flagged: Mapped[bool] = mapped_column(
        default=False, server_default="false", nullable=False, index=True
    )
    flag_reasons: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Blocked messages are stored for audit but NEVER delivered to the recipient.
    blocked: Mapped[bool] = mapped_column(
        default=False, server_default="false", nullable=False
    )
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), index=True
    )

