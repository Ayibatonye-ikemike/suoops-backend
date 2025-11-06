from fastapi import FastAPI
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware

from app.api.rate_limit import limiter
from app.api.routes_auth import router as auth_router
from app.api.routes_health import router as health_router
from app.api.routes_invoice import router as invoice_router
from app.api.routes_invoice_public import router as invoice_public_router
from app.api.routes_metrics import router as metrics_router
from app.api.routes_oauth import router as oauth_router
from app.api.routes_ocr import router as ocr_router
from app.api.routes_subscription import router as subscription_router
from app.api.routes_tax import router as tax_router
from app.api.routes_user import router as user_router
from app.api.routes_webhooks import router as webhook_router
from app.core.config import settings
from app.core.logger import init_logging


async def _rate_limit_handler(request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Too many requests"})


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):  # type: ignore[override]
        response = await call_next(request)
        response.headers.setdefault(
            "Strict-Transport-Security",
            f"max-age={settings.HSTS_SECONDS}; includeSubDomains; preload",
        )
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Content-Security-Policy", settings.CONTENT_SECURITY_POLICY)
        return response


def create_app() -> FastAPI:
    init_logging()
    app = FastAPI(title=settings.APP_NAME)
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOW_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )
    if settings.ENV.lower() == "prod":
        app.add_middleware(HTTPSRedirectMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(oauth_router, prefix="/auth/oauth", tags=["oauth"])
    app.include_router(webhook_router, prefix="/webhooks", tags=["webhooks"])
    app.include_router(invoice_public_router, prefix="/public/invoices", tags=["invoices-public"])
    app.include_router(invoice_router, prefix="/invoices", tags=["invoices"])
    app.include_router(ocr_router, tags=["ocr"])
    app.include_router(subscription_router, prefix="/subscriptions", tags=["subscriptions"])
    app.include_router(tax_router, tags=["tax"])
    app.include_router(user_router, prefix="/users", tags=["users"])
    app.include_router(metrics_router, tags=["metrics"])
    app.include_router(health_router)
    return app


app = create_app()
