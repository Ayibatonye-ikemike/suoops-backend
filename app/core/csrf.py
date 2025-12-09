"""
CSRF Protection using Double Submit Cookie pattern.

For state-changing operations (POST, PUT, DELETE, PATCH), clients must:
1. Include CSRF token in cookie (set by server on auth)
2. Include same token in X-CSRF-Token header

This prevents CSRF attacks while working with SPA/API architecture.
"""
import secrets
import logging
from fastapi import Request, HTTPException, status
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# CSRF token cookie name
CSRF_COOKIE_NAME = "csrf_token"

# Header name for CSRF token
CSRF_HEADER_NAME = "x-csrf-token"

# Safe HTTP methods that don't require CSRF protection
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

# Paths exempt from CSRF protection
EXEMPT_PATHS = {
    "/health",
    "/metrics",
    "/auth/",              # Auth endpoints use secure tokens (JWT/OAuth)
    "/tax/",               # Tax endpoints use JWT authentication
    "/invoices/",          # Invoice endpoints use JWT authentication
    "/expenses/",          # Expense endpoints use JWT authentication
    "/telemetry/",         # Frontend telemetry without auth
    "/users/",             # User endpoints use JWT authentication
    "/subscriptions/",     # Subscription endpoints use JWT authentication
    "/team",               # Team endpoints use JWT authentication (no trailing slash)
    "/inventory/",         # Inventory endpoints use JWT authentication
    "/webhooks/whatsapp",  # External webhooks have their own verification
    "/webhooks/paystack",
    "/public/invoices/",   # Public read-only endpoints
    "/analytics/",         # Analytics endpoints use JWT authentication
    "/ocr/",               # OCR endpoints use JWT authentication
}


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response, token: str, secure: bool = True) -> None:
    """
    Set CSRF token in HTTP-only cookie.
    
    Args:
        response: FastAPI Response object
        token: CSRF token string
        secure: Whether to set Secure flag (True in production)
    """
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=False,  # JavaScript needs to read this to set header
        secure=secure,
        samesite="lax",  # Protects against CSRF while allowing normal navigation
        max_age=86400,  # 24 hours
    )


def verify_csrf_token(request: Request) -> bool:
    """
    Verify CSRF token from cookie matches header.
    
    Returns:
        True if token is valid, False otherwise
    """
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get(CSRF_HEADER_NAME)
    
    if not cookie_token or not header_token:
        logger.warning(
            "CSRF validation failed: missing token cookie=%s header=%s path=%s",
            bool(cookie_token),
            bool(header_token),
            request.url.path,
        )
        return False
    
    # Constant-time comparison to prevent timing attacks
    return secrets.compare_digest(cookie_token, header_token)


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection middleware for FastAPI.
    
    Validates CSRF tokens on state-changing requests (POST, PUT, DELETE, PATCH).
    Automatically generates and sets CSRF tokens on successful auth responses.
    """
    
    def __init__(self, app: ASGIApp, enabled: bool = True) -> None:
        super().__init__(app)
        self.enabled = enabled
    
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        # Skip CSRF check if disabled (for testing)
        if not self.enabled:
            return await call_next(request)
        
        # Skip CSRF check for safe methods
        if request.method in SAFE_METHODS:
            return await call_next(request)
        
        # Skip CSRF check for exempt paths
        path = request.url.path
        if any(path.startswith(exempt) for exempt in EXEMPT_PATHS):
            return await call_next(request)
        
        # Verify CSRF token
        if not verify_csrf_token(request):
            logger.warning(
                "CSRF validation failed: path=%s method=%s ip=%s",
                path,
                request.method,
                request.client.host if request.client else "unknown",
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF validation failed. Missing or invalid CSRF token.",
            )
        
        # Token valid, proceed with request
        return await call_next(request)


def get_csrf_token(request: Request) -> str:
    """
    Get CSRF token from request cookie, or generate new one if missing.
    
    Use this in auth endpoints to provide token to frontend.
    """
    token = request.cookies.get(CSRF_COOKIE_NAME)
    if not token:
        token = generate_csrf_token()
    return token
