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
    
    # Email/SMS Configuration - Using Brevo
    EMAIL_PROVIDER: str = "brevo"  # We use Brevo for email and SMS
    FROM_EMAIL: str | None = None
    
    # SMTP Configuration (Generic - works with Brevo, SES, etc.)
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    
    # Brevo (Sendinblue) - For both Email and SMS
    BREVO_API_KEY: str | None = None  # Get from Brevo dashboard
    BREVO_SMTP_LOGIN: str | None = None  # Brevo SMTP login (e.g., "9a485d001@smtp-brevo.com")
    BREVO_SENDER_NAME: str = "SuoOps"  # Sender name for emails and SMS
    
    # SMS Configuration
    SMS_PROVIDER: str = "brevo"  # Options: brevo, termii, twilio
    
    # Termii - Alternative SMS provider (Nigerian)
    TERMII_API_KEY: str | None = None
    TERMII_SENDER_ID: str = "SuoOps"  # Max 11 characters for SMS
    TERMII_DEVICE_ID: str = "TID"  # Max 9 characters for WhatsApp (use "TID" for testing)
    
    # WhatsApp Configuration (Meta/Facebook)
    WHATSAPP_API_KEY: str | None = None
    WHATSAPP_PHONE_NUMBER_ID: str | None = None
    WHATSAPP_VERIFY_TOKEN: str = "suoops_verify_2025"
    WHATSAPP_TEMPLATE_INVOICE: str | None = None
    WHATSAPP_TEMPLATE_LANGUAGE: str = "en_US"
    
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
    CORS_ALLOW_ORIGINS: list[str] = ["*"]
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
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
        "http://localhost:3000",  # Local development
        "http://127.0.0.1:3000",  # Local development (alt)
    ]
    CORS_ALLOW_CREDENTIALS: bool = True
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
