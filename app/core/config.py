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
    
    # Email/SMTP Configuration
    EMAIL_PROVIDER: str = "gmail"  # Options: gmail, ses, brevo, mailgun
    
    # Gmail SMTP (default, 500 emails/day)
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    FROM_EMAIL: str | None = None
    
    # Amazon SES SMTP (for high volume, no daily limit)
    SES_SMTP_HOST: str = "email-smtp.eu-north-1.amazonaws.com"
    SES_SMTP_PORT: int = 587
    SES_SMTP_USER: str | None = None
    SES_SMTP_PASSWORD: str | None = None
    SES_REGION: str = "eu-north-1"  # Same region as S3
    
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
    
    # NRS Integration (Nigeria Revenue Service - Tax compliance)
    NRS_API_URL: str | None = None
    NRS_API_KEY: str | None = None
    NRS_MERCHANT_ID: str | None = None
    
    # OAuth 2.0 / SSO Configuration
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    OAUTH_STATE_SECRET: str = "change_me_oauth_state"  # For CSRF protection

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
        )
        if self.ENV.lower() == "prod":
            missing = [name for name in required_in_prod if not getattr(self, name)]
            if missing:
                raise ValueError(f"Missing required production settings: {', '.join(missing)}")
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
        "https://suoops-frontend.vercel.app",
        "https://suoops-frontend-ikemike.vercel.app",
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
