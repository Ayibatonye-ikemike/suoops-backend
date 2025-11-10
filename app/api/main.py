from fastapi import FastAPI
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware

from app.api.rate_limit import limiter, increment_rate_limit_exceeded, rate_limit_stats
from app.api.routes_auth import router as auth_router
from app.api.routes_expense import router as expense_router
from app.api.routes_health import router as health_router
from app.api.routes_invoice import router as invoice_router
from app.api.routes_invoice_public import router as invoice_public_router
from app.api.routes_metrics import router as metrics_router
from app.api.routes_admin import router as admin_router
from app.api.routes_oauth import router as oauth_router
from app.api.routes_ocr import router as ocr_router
from app.api.routes_subscription import router as subscription_router
from app.api.routes_tax_main import router as tax_router
from app.api.routes_user import router as user_router
from app.api.routes_user_logo import router as user_logo_router
from app.api.routes_user_phone import router as user_phone_router
from app.api.routes_user_bank import router as user_bank_router
from app.api.routes_webhooks import router as webhook_router
from app.api.routes_telemetry import router as telemetry_router
from app.core.config import settings
from app.core.logger import init_logging
from app.core.monitoring import init_monitoring
from app.core.errors import register_error_handlers
from app.core.csrf import CSRFMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send
import uuid
import logging


async def _rate_limit_handler(request, exc: RateLimitExceeded):
    increment_rate_limit_exceeded()
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
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, max_body: int = 12 * 1024 * 1024) -> None:
        super().__init__(app)
        self.max_body = max_body
        self.logger = logging.getLogger("app.request_size")

    async def dispatch(self, request, call_next):  # type: ignore[override]
        # Check Content-Length header early if provided
        length_header = request.headers.get("content-length")
        if length_header:
            try:
                if int(length_header) > self.max_body:
                    return JSONResponse(status_code=413, content={"detail": "Request body too large"})
            except ValueError:
                pass
        # For streamed bodies we rely on endpoint-level explicit size checks
        return await call_next(request)


def create_app() -> FastAPI:
    init_logging()
    init_monitoring()
    
    # Disable debug mode and interactive docs in production for security
    is_production = settings.ENV.lower() == "prod"
    app = FastAPI(
        title=settings.APP_NAME,
        debug=False,  # Always disable debug mode
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
    )
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
    
    # CSRF Protection - Add before CORS to validate tokens early
    # Only enabled in production for security
    app.add_middleware(CSRFMiddleware, enabled=is_production)
    
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
    app.add_middleware(RequestSizeLimitMiddleware)
    register_error_handlers(app)
    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(oauth_router, tags=["oauth"])
    app.include_router(webhook_router, prefix="/webhooks", tags=["webhooks"])
    app.include_router(invoice_public_router, prefix="/public/invoices", tags=["invoices-public"])
    app.include_router(invoice_router, prefix="/invoices", tags=["invoices"])
    app.include_router(expense_router, tags=["expenses"])
    app.include_router(ocr_router, tags=["ocr"])
    app.include_router(subscription_router, prefix="/subscriptions", tags=["subscriptions"])
    app.include_router(tax_router, tags=["tax"])
    # User routers split for maintainability
    app.include_router(user_router, prefix="/users", tags=["users"])
    app.include_router(user_logo_router, prefix="/users", tags=["users"])
    app.include_router(user_phone_router, prefix="/users", tags=["users"])
    app.include_router(user_bank_router, prefix="/users", tags=["users"])
    app.include_router(metrics_router, tags=["metrics"])
    app.include_router(telemetry_router, tags=["telemetry"])
    app.include_router(admin_router)
    app.include_router(health_router)
    
    # Register shutdown handler to close Redis pool
    @app.on_event("shutdown")
    async def shutdown_event():
        try:
            from app.db.redis_client import close_redis_pool
            close_redis_pool()
        except Exception:
            pass
    
    return app


app = create_app()
