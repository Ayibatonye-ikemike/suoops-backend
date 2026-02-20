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
    WHATSAPP_VERIFY_TOKEN: str = "suoops_verify_2025"
    WHATSAPP_APP_SECRET: str | None = None  # Meta app secret for webhook signature verification
    # WhatsApp Message Templates
    WHATSAPP_TEMPLATE_INVOICE: str | None = None  # Basic invoice notification
    WHATSAPP_TEMPLATE_INVOICE_PAYMENT: str | None = None  # Invoice with bank details
    WHATSAPP_TEMPLATE_PAYMENT_REMINDER: str | None = None  # Overdue reminder
    WHATSAPP_TEMPLATE_RECEIPT: str | None = None  # Payment receipt
    WHATSAPP_TEMPLATE_LANGUAGE: str = "en"
    
    @field_validator("WHATSAPP_PHONE_NUMBER_ID", mode="before")
    @classmethod
    def coerce_phone_number_id_to_str(cls, v):
        """Convert phone number ID to string if it's an integer."""
        if v is None:
            return v
        return str(v)
    PAYSTACK_SECRET: str | None = None
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
        "connect-src 'self'"
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

    # Feature flags / premium gating
    # When False, voice note invoice feature is available to all users regardless of plan.
    FEATURE_VOICE_REQUIRES_PAID: bool = True
    # Master switch for voice feature - when False, voice invoices are completely disabled
    FEATURE_VOICE_ENABLED: bool = False

    @model_validator(mode="after")
    def _validate_required_fields(self) -> BaseAppSettings:
        # Convert Heroku's postgres:// URL to postgresql://
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
            if self.OAUTH_STATE_SECRET == "change_me_oauth_state":
                default_violations.append("OAUTH_STATE_SECRET uses default placeholder")
            # WhatsApp verify token is non-critical (webhook handshake only) — warn, don't block.
            if self.WHATSAPP_VERIFY_TOKEN in ("suoops_verify_2025", "suoops_verify_token_2024"):
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "WHATSAPP_VERIFY_TOKEN uses a default placeholder — "
                    "set a unique value in production env vars."
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
        "https://suoops-frontend-ikemike.vercel.app",
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
