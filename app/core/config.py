from __future__ import annotations

import os
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseAppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "SuoOps"
    ENV: str = "dev"
    DATABASE_URL: str | None = None
    S3_ENDPOINT: str | None = None
    S3_ACCESS_KEY: str | None = None
    S3_SECRET_KEY: str | None = None
    S3_BUCKET: str = "whatsinvoice"
    S3_REGION: str = "us-east-1"  # AWS region for S3 bucket
    S3_PRESIGN_TTL: int = 3600
    
    # Email Configuration - Using Brevo
    EMAIL_PROVIDER: str = "brevo"  # We use Brevo for email
    FROM_EMAIL: str | None = None
    
    # SMTP Configuration (Generic - works with Brevo, SES, etc.)
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    
    # Brevo (Sendinblue) - For Email
    BREVO_API_KEY: str | None = None  # SMTP password for sending emails
    BREVO_CONTACTS_API_KEY: str | None = None  # Full API key (xkeysib-...) for Contacts API
    BREVO_SMTP_LOGIN: str | None = None  # Brevo SMTP login (e.g., "9a485d001@smtp-brevo.com")
    BREVO_SENDER_NAME: str = "SuoOps"  # Sender name for emails
    
    # WhatsApp Configuration (Meta/Facebook)
    WHATSAPP_API_KEY: str | None = None
    WHATSAPP_PHONE_NUMBER_ID: str | None = None
    WHATSAPP_VERIFY_TOKEN: str = ""  # REQUIRED: set a unique random value in env vars
    WHATSAPP_APP_SECRET: str | None = None  # Meta app secret for webhook signature verification
    # WhatsApp Message Templates (set via env vars — names must match Meta Business Manager)
    WHATSAPP_TEMPLATE_INVOICE: str | None = None  # Basic invoice notification
    # invoice_with_payment: the main template. Give it a DOCUMENT header (the
    # invoice PDF rides along, so first-time customers get it without replying)
    # and a short body with no bank number — customers pay via the link.
    WHATSAPP_TEMPLATE_INVOICE_PAYMENT: str | None = None
    WHATSAPP_TEMPLATE_PAYMENT_REMINDER: str | None = None  # Overdue reminder
    WHATSAPP_TEMPLATE_RECEIPT: str | None = None  # Payment receipt
    WHATSAPP_TEMPLATE_DAILY_SUMMARY: str | None = None  # Daily business summary
    # Lifecycle / engagement templates
    WHATSAPP_TEMPLATE_ACTIVATION_WELCOME: str | None = None  # New signup welcome
    WHATSAPP_TEMPLATE_FIRST_INVOICE: str | None = None  # After first invoice
    WHATSAPP_TEMPLATE_LOW_BALANCE: str | None = None  # Wallet balance running low
    WHATSAPP_TEMPLATE_INVOICE_PACK_PROMO: str | None = None  # Wallet empty — top up prompt
    WHATSAPP_TEMPLATE_PRO_UPGRADE: str | None = None  # Invoice milestone nudge (all features free at 3%)
    WHATSAPP_TEMPLATE_WIN_BACK: str | None = None  # Inactive user re-engagement
    WHATSAPP_TEMPLATE_LOW_STOCK_ALERT: str | None = None  # Low inventory alert
    WHATSAPP_TEMPLATE_OVERDUE_REPORT: str | None = None  # Owner overdue summary
    WHATSAPP_TEMPLATE_MARK_PAID_NUDGE: str | None = None  # Owner mark-as-paid nudge
    WHATSAPP_TEMPLATE_TAX_REPORT_READY: str | None = None  # Monthly tax report ready
    WHATSAPP_TEMPLATE_MORNING_TIP: str | None = None  # Daily morning business insight
    WHATSAPP_TEMPLATE_DORMANT_CUSTOMER: str | None = None  # Dormant customer "we miss you"
    WHATSAPP_TEMPLATE_REFERRAL_ASK: str | None = None  # Post-payment referral ask
    WHATSAPP_TEMPLATE_FEEDBACK: str | None = None  # Feedback/testimonial request
    WHATSAPP_TEMPLATE_UNPAID_ALERT: str | None = None  # Aggregate unpaid notification
    WHATSAPP_TEMPLATE_PAYMENT_UPSELL: str | None = None  # Payment-triggered growth nudge (3% model)
    WHATSAPP_TEMPLATE_FEATURE_ANNOUNCEMENT: str | None = None  # One-off product announcement (params: name, body)
    WHATSAPP_TEMPLATE_LANGUAGE: str = "en"
    
    @field_validator("WHATSAPP_PHONE_NUMBER_ID", mode="before")
    @classmethod
    def coerce_phone_number_id_to_str(cls, v):
        """Convert phone number ID to string if it's an integer."""
        if v is None:
            return v
        return str(v)
    PAYSTACK_SECRET: str | None = None
    # Paystack plan code for the recurring monthly Pro Features subscription
    # (₦1,500/mo). Create with scripts/create_pro_features_plan.py, then set here.
    PAYSTACK_PRO_FEATURES_PLAN_CODE: str | None = None
    # Platform commission (percent) retained by SuoOps on online invoice/marketplace
    # payments settled through a business's Paystack subaccount. The business
    # receives (100 - this) percent, settled directly to their bank by Paystack.
    PAYSTACK_PLATFORM_COMMISSION_PERCENT: float = 3.0
    # Mapbox token for server-side reverse-geocoding (lat/lng -> state) used by the
    # storefront escrow window. Public pk. token is fine; keep it as MAPBOX_TOKEN on
    # the backend (the frontend uses NEXT_PUBLIC_MAPBOX_TOKEN).
    MAPBOX_TOKEN: str | None = None
    # ── Storefront order escrow (buyer protection) ──
    ESCROW_ENABLED: bool = True  # master switch for the hold-&-release flow
    ESCROW_SAME_STATE_HOLD_HOURS: int = 12  # dispute window when buyer & seller share a state
    ESCROW_CROSS_STATE_HOLD_DAYS: int = 3  # base dispute window across nearby states (working days)
    ESCROW_MAX_CROSS_STATE_HOLD_DAYS: int = 7  # cap for far-apart states (e.g. Lagos↔Borno)
    # Sellers settle on a T+1 cadence (never same-day): once buyer protection ends,
    # the payout waits for the daily settlement run at this UTC hour, which fires
    # after Flutterwave's own T+1 settlement lands — so payouts come from settled
    # collections, not float. 7 UTC = 8am WAT.
    ESCROW_SETTLEMENT_HOUR_UTC: int = 7
    # Anti-brute-force on the buyer delivery code: cap total FAILED code attempts
    # per store within the window (IP-independent — stops distributed guessing via
    # rotated IPs). Legit buyers never hit this; a store that trips it has code
    # entry blocked until the window resets (ordering/payment stay open, and
    # auto-release never needs the code).
    ESCROW_CODE_MAX_FAILURES: int = 30
    ESCROW_CODE_FAILURE_WINDOW_SECONDS: int = 3600
    # Courier-delivery-aware release: for orders shipped by a booked courier, the
    # payout is NOT auto-released until the courier reports delivery, then the
    # buyer gets this many hours to inspect/dispute. If the courier hasn't
    # delivered within the SLA (working days), the order is flagged for admin
    # review instead of auto-releasing to the seller.
    ESCROW_POST_DELIVERY_INSPECTION_HOURS: int = 24
    ESCROW_MAX_DELIVERY_DAYS: int = 10

    # ── Shipbubble courier integration (buyer pays delivery at checkout) ──
    # Master switch: keep OFF until a Shipbubble account, API key and a funded
    # Naira shipping wallet exist. While off, delivery-quote endpoints return no
    # options and nothing is booked — the manual dispatch flow is unaffected.
    SHIPBUBBLE_ENABLED: bool = False
    SHIPBUBBLE_API_KEY: str | None = None  # "sb_sandbox_…" (test) or "sb_prod_…" (live)
    SHIPBUBBLE_BASE_URL: str = "https://api.shipbubble.com/v1"
    # Live-money switch, SEPARATE from SHIPBUBBLE_ENABLED: only when this is on do
    # storefront checkouts charge the buyer a delivery fee and auto-book the
    # courier. Keep OFF until a real test order has been verified end-to-end.
    SHIPBUBBLE_CHECKOUT_ENABLED: bool = False
    # Package category id — usually leave unset; the code auto-resolves one from
    # the account's Package Categories API (ids are account-specific).
    SHIPBUBBLE_DEFAULT_CATEGORY_ID: int | None = None
    # Anti-abuse for the public delivery-quote endpoint (each miss makes several
    # paid Shipbubble calls): cache identical quotes briefly + cap per store/day.
    SHIPBUBBLE_QUOTE_CACHE_SECONDS: int = 180
    SHIPBUBBLE_QUOTE_DAILY_CAP_PER_STORE: int = 500
    # Secret used to verify the `x-ship-signature` HMAC-SHA512 on Shipbubble
    # webhooks. If unset we fall back to the API key (Shipbubble signs with your
    # secret key). Webhook URL to register: https://api.suoops.com/webhooks/shipbubble
    SHIPBUBBLE_WEBHOOK_SECRET: str | None = None
    # Trusted sellers skip the hold (normal settlement). ALL must hold: not
    # flagged/suspended AND zero unresolved disputes AND the thresholds below.
    ESCROW_TRUST_MIN_PAID_INVOICES: int = 100
    ESCROW_TRUST_MIN_ACCOUNT_AGE_DAYS: int = 90
    # Anti self-dealing: trust also needs breadth (many DISTINCT paying customers)
    # and a track record of actually-completed storefront deliveries.
    ESCROW_TRUST_MIN_DISTINCT_CUSTOMERS: int = 20
    ESCROW_TRUST_MIN_DELIVERIES: int = 20  # released storefront orders
    # Exposure caps for UNTRUSTED sellers (blast-radius limits, in Naira).
    ESCROW_MAX_ORDER_NAIRA_UNTRUSTED: int = 200_000  # per-order ceiling
    ESCROW_MAX_INFLIGHT_NAIRA_UNTRUSTED: int = 500_000  # total held at once
    # Velocity guard: the in-flight cap resets when an order releases, so a bad
    # actor could launder small amounts across many days. These cap the ROLLING
    # settled payout volume and dispute rate — an untrusted seller who exceeds
    # either has NEW orders held for admin review (not auto-released).
    ESCROW_SELLER_VELOCITY_WINDOW_DAYS: int = 7
    ESCROW_SELLER_MAX_SETTLED_NAIRA_UNTRUSTED: int = 2_000_000  # released per window
    ESCROW_SELLER_DISPUTE_HOLD_AT: int = 3  # disputes/refunds in window → review
    # When a seller changes payout/bank details, freeze payouts this long so a
    # hijacked account can't instantly reroute money (owner is alerted).
    ESCROW_PAYOUT_FREEZE_HOURS_ON_BANK_CHANGE: int = 48
    # Flag a buyer after this many disputes an admin ruled against them (false
    # "not delivered" claims) so future reports get extra scrutiny.
    ESCROW_BUYER_ABUSE_FLAG_AT: int = 4
    # A buyer's abuse flag decays after this many days with no new false dispute —
    # so an honest buyer isn't punished forever for old losses.
    ESCROW_BUYER_ABUSE_DECAY_DAYS: int = 90
    # Flag a SELLER for review after this many order-messaging attempts to move a
    # deal off-platform (share contact/account or push a direct transfer).
    ESCROW_SELLER_CIRCUMVENTION_FLAG_AT: int = 3
    # Self-dealing GPS radius: a buyer pin within this many metres of the store is
    # flagged as "buyer at seller location" (held for review).
    ESCROW_COLLUSION_RADIUS_M: int = 50
    # Admin refund/release above this Naira amount requires a fresh step-up OTP
    # (defends against a stolen admin session moving large sums).
    ESCROW_ADMIN_STEPUP_NAIRA: int = 100_000
    # Card-fraud mitigation: a card that funded a refunded/charged-back order is
    # blocked from new orders for this long; and one card funding more than N
    # orders in 24h has new orders held for review.
    CARD_BLOCK_DAYS_ON_REFUND: int = 60
    CARD_MAX_ORDERS_PER_DAY: int = 6
    # Strongest card-fraud defense: collect HELD (buyer-protection) orders by BANK
    # TRANSFER ONLY. Nigerian NIP transfers are irreversible, so there are no
    # chargebacks to launder. Trusted sellers' normal (non-hold) orders are
    # unaffected. Set False to also allow cards on held orders.
    ESCROW_HOLD_BANK_TRANSFER_ONLY: bool = True
    # Which provider pays sellers out of the held balance: "paystack" (default)
    # or "flutterwave". Refunds always use the collector (Paystack). Switch this
    # to move payouts to another rail without touching the escrow logic.
    ESCROW_PAYOUT_PROVIDER: str = "paystack"
    # Which provider COLLECTS storefront/escrow payments (the held funds):
    # "paystack" (default, collects to the SuoOps Paystack balance) or
    # "flutterwave" (collects to the FW payout balance so funds can be held there).
    # Only the escrow-hold path is pluggable — regular invoice payments always
    # settle through the issuer's Paystack subaccount. Refunds follow the
    # provider that collected each order.
    ESCROW_COLLECTOR_PROVIDER: str = "paystack"
    # Flutterwave (alternative payout rail). Off unless the secret is set AND
    # ESCROW_PAYOUT_PROVIDER="flutterwave".
    FLUTTERWAVE_SECRET: str | None = None
    FLUTTERWAVE_BASE: str = "https://api.flutterwave.com"
    # Secret hash configured in the Flutterwave dashboard (Settings → Webhooks).
    # Flutterwave echoes it in the `verif-hash` header; we reject any webhook whose
    # header doesn't match. Required for the Flutterwave collection webhook.
    FLUTTERWAVE_WEBHOOK_HASH: str | None = None
    JWT_SECRET: str = "change_me"
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_SSL_CERT_REQS: str | None = "required"
    REDIS_SSL_CA_CERTS: str | None = None
    HTML_PDF_ENABLED: bool = False
    PDF_WATERMARK_ENABLED: bool = False
    PDF_WATERMARK_TEXT: str = "SUOOPS COMPLIANT"
    PRIMARY_PAYMENT_PROVIDER: str = "paystack"
    FRONTEND_URL: str = "https://suoops.com"
    BACKEND_URL: str = "https://api.suoops.com"  # Used for QR code verification URLs
    CORS_ALLOW_ORIGINS: list[str] = ["https://suoops.com", "https://www.suoops.com", "https://support.suoops.com", "http://localhost:3000"]
    CORS_ALLOW_METHODS: list[str] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    CORS_ALLOW_HEADERS: list[str] = [
        "Authorization", "Content-Type", "Accept", "Origin",
        "X-Requested-With", "X-CSRF-Token", "X-Telemetry-Key",
        "X-Client-Trace",
        "Sentry-Trace", "Baggage",
    ]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_ORIGIN_REGEX: str | None = None  # Starlette allow_origin_regex for preview deploys
    CSRF_COOKIE_DOMAIN: str | None = None  # Set to ".suoops.com" in prod so frontend JS can read it
    CONTENT_SECURITY_POLICY: str = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https://fastapi.tiangolo.com; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"
    )
    HSTS_SECONDS: int = 31_536_000
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "plain"
    SENTRY_DSN: str | None = None
    TELEMETRY_INGEST_KEY: str | None = None  # API key required for telemetry ingestion in prod
    
    # VAT / Tax
    VAT_RATE: float = 7.5  # Nigeria standard VAT rate (percent)

    # Fiscalization Integration (FIRS - provisional placeholders, external API pending)
    FIRS_API_URL: str | None = None
    FIRS_API_KEY: str | None = None
    FIRS_MERCHANT_ID: str | None = None
    # Accreditation / readiness flag: when False we never attempt external transmission
    FISCALIZATION_ACCREDITED: bool = False
    
    # OAuth 2.0 / SSO Configuration
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    OAUTH_STATE_SECRET: str = "change_me_oauth_state"  # For CSRF protection

    # External service keys
    OPENAI_API_KEY: str | None = None  # For OCR service (GPT-4 Vision)
    ENCRYPTION_KEY: str | None = None  # Fernet key for column encryption

    # Admin bootstrap
    DEFAULT_ADMIN_PASSWORD: str | None = None  # One-time admin bootstrap password

    # Admin access IP allowlist. Comma-separated IPv4/IPv6 addresses or CIDR
    # ranges (e.g. "203.0.113.4, 198.51.100.0/24"). When empty/unset, the admin
    # panel is reachable from any IP (no restriction). When set, only matching
    # client IPs may reach any /admin* route.
    ADMIN_IP_ALLOWLIST: str | None = None

    # Operational
    NGN_USD_RATE: str | None = None  # Naira/USD conversion rate (e.g. "1600")
    AUDIT_LOG_FILE: str = "storage/audit.log"  # Path to structured audit log

    # Feature flags / premium gating
    # When False, voice note invoice feature is available to all users regardless of plan.
    FEATURE_VOICE_REQUIRES_PAID: bool = True
    # Master switch for voice feature - when False, voice invoices are completely disabled
    FEATURE_VOICE_ENABLED: bool = False

    @model_validator(mode="after")
    def _validate_required_fields(self) -> BaseAppSettings:
        # Convert legacy postgres:// URLs to postgresql:// (some managed
        # Postgres providers still emit the old scheme)
        if self.DATABASE_URL and self.DATABASE_URL.startswith("postgres://"):
            self.DATABASE_URL = self.DATABASE_URL.replace("postgres://", "postgresql://", 1)
        
        required_in_prod = (
            "DATABASE_URL",
            "WHATSAPP_API_KEY",
            "WHATSAPP_APP_SECRET",  # Required for webhook signature verification
            "PAYSTACK_SECRET",
            "JWT_SECRET",
            "BREVO_API_KEY",  # Ensure email capability secrets present
            "OAUTH_STATE_SECRET",  # State secret must not use default in prod
            "TELEMETRY_INGEST_KEY",  # Require telemetry ingestion key to prevent spoofing
        )
        if self.ENV.lower() == "prod":
            missing = [name for name in required_in_prod if not getattr(self, name)]
            # Detect unchanged insecure defaults
            default_violations: list[str] = []
            if self.JWT_SECRET == "change_me":
                default_violations.append("JWT_SECRET uses default placeholder")
            elif len(self.JWT_SECRET) < 32:
                # HS256 signing keys should be at least 32 bytes (RFC 7518 §3.2).
                default_violations.append(
                    "JWT_SECRET is too short — use at least 32 characters of random entropy"
                )
            if self.OAUTH_STATE_SECRET == "change_me_oauth_state":
                default_violations.append("OAUTH_STATE_SECRET uses default placeholder")
            # WhatsApp verify token — block startup if empty or using old defaults.
            if not self.WHATSAPP_VERIFY_TOKEN or self.WHATSAPP_VERIFY_TOKEN in (
                "suoops_verify_2025",
                "suoops_verify_token_2024",
            ):
                default_violations.append(
                    "WHATSAPP_VERIFY_TOKEN is empty or uses a known default — "
                    "set a unique random value in production env vars"
                )
            if missing:
                raise ValueError(f"Missing required production settings: {', '.join(missing)}")
            if default_violations:
                raise ValueError("Insecure default secrets in production: " + ", ".join(default_violations))
        return self


class DevSettings(BaseAppSettings):
    ENV: str = "dev"
    DATABASE_URL: str = "sqlite+aiosqlite:///./storage/dev.db"
    BACKEND_URL: str = "http://localhost:8000"
    WHATSAPP_API_KEY: str = "dev-whatsapp-key"
    PAYSTACK_SECRET: str = "dev-paystack-secret"


class TestSettings(BaseAppSettings):
    ENV: str = "test"
    DATABASE_URL: str = "sqlite+aiosqlite:///./storage/test.db"
    WHATSAPP_API_KEY: str = "test-whatsapp-key"
    PAYSTACK_SECRET: str = "test-paystack-secret"


class ProdSettings(BaseAppSettings):
    ENV: str = "prod"
    CORS_ALLOW_ORIGINS: list[str] = [
        "https://suoops.com",
        "https://www.suoops.com",
        "https://support.suoops.com",
        "https://suoops-frontend.vercel.app",
        "https://suoops-support.vercel.app",
        # NOTE: localhost removed from production — use DevSettings for local dev
    ]
    CORS_ALLOW_CREDENTIALS: bool = True
    CSRF_COOKIE_DOMAIN: str | None = ".suoops.com"  # Share CSRF cookie between suoops.com and api.suoops.com
    # Allow Vercel preview deployments (e.g. suoops-frontend-abc123-ikemike.vercel.app)
    CORS_ALLOW_ORIGIN_REGEX: str | None = r"https://suoops-(frontend|support)(-[a-z0-9]+)?(-ikemike)?\.vercel\.app"
    LOG_FORMAT: str = "json"


_ENV_TO_SETTINGS: dict[str, type[BaseAppSettings]] = {
    "dev": DevSettings,
    "development": DevSettings,
    "test": TestSettings,
    "testing": TestSettings,
    "prod": ProdSettings,
    "production": ProdSettings,
}


@lru_cache
def get_settings() -> BaseAppSettings:
    env_name = os.getenv("APP_ENV") or os.getenv("ENV") or "dev"
    env = env_name.lower()
    settings_cls = _ENV_TO_SETTINGS.get(env, DevSettings)
    return settings_cls()


settings = get_settings()
