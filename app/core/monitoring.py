import logging
from app.core.config import settings

_initialized = False

def init_monitoring() -> None:
    global _initialized
    if _initialized:
        return
    dsn = getattr(settings, "SENTRY_DSN", None)
    if dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            sentry_sdk.init(
                dsn=dsn,
                integrations=[FastApiIntegration()],
                traces_sample_rate=0.1,
                profiles_sample_rate=0.0,
                environment=settings.ENV,
                release=f"suoops-backend@{settings.ENV}",
            )
            logging.getLogger(__name__).info("Sentry initialized")
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).warning("Failed to init Sentry: %s", exc)
    _initialized = True