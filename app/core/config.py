from __future__ import annotations

import os
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseAppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "SuoPay"
    ENV: str = "dev"
    DATABASE_URL: str | None = None
    S3_ENDPOINT: str | None = None
    S3_ACCESS_KEY: str | None = None
    S3_SECRET_KEY: str | None = None
    S3_BUCKET: str = "whatsinvoice"
    S3_PRESIGN_TTL: int = 3600
    WHATSAPP_API_KEY: str | None = None
    PAYSTACK_SECRET: str | None = None
    FLUTTERWAVE_SECRET: str | None = None
    JWT_SECRET: str = "change_me"
    REDIS_URL: str = "redis://localhost:6379/0"
    HTML_PDF_ENABLED: bool = False
    PRIMARY_PAYMENT_PROVIDER: str = "paystack"
    CORS_ALLOW_ORIGINS: list[str] = ["*"]
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CONTENT_SECURITY_POLICY: str = "default-src 'self'"
    HSTS_SECONDS: int = 31_536_000
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "plain"

    @model_validator(mode="after")
    def _validate_required_fields(self) -> BaseAppSettings:
        # Convert Heroku's postgres:// URL to postgresql://
        if self.DATABASE_URL and self.DATABASE_URL.startswith("postgres://"):
            self.DATABASE_URL = self.DATABASE_URL.replace("postgres://", "postgresql://", 1)
        
        required_in_prod = (
            "DATABASE_URL",
            "WHATSAPP_API_KEY",
            "PAYSTACK_SECRET",
            "FLUTTERWAVE_SECRET",
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
    WHATSAPP_API_KEY: str = "dev-whatsapp-key"
    PAYSTACK_SECRET: str = "dev-paystack-secret"
    FLUTTERWAVE_SECRET: str = "dev-flutterwave-secret"


class TestSettings(BaseAppSettings):
    ENV: str = "test"
    DATABASE_URL: str = "sqlite+aiosqlite:///./storage/test.db"
    WHATSAPP_API_KEY: str = "test-whatsapp-key"
    PAYSTACK_SECRET: str = "test-paystack-secret"
    FLUTTERWAVE_SECRET: str = "test-flutterwave-secret"


class ProdSettings(BaseAppSettings):
    ENV: str = "prod"
    CORS_ALLOW_ORIGINS: list[str] = [
        "https://suopay.io",
        "https://www.suopay.io",
        "https://suopay.vercel.app"  # Add your Vercel domain here
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
    env = os.getenv("APP_ENV", "dev").lower()
    settings_cls = _ENV_TO_SETTINGS.get(env, DevSettings)
    return settings_cls()


settings = get_settings()
