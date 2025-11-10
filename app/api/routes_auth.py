from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.rate_limit import limiter, RATE_LIMITS
from app.core.config import settings
from app.core.security import TokenExpiredError, TokenValidationError, decode_token
from app.core.audit import log_audit_event, log_failure
from app.core.csrf import get_csrf_token, set_csrf_cookie
from app import metrics
from app.models import schemas
from app.services.auth_service import AuthService, TokenBundle, get_auth_service

router = APIRouter()

AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


# Allow more generous registration throughput outside prod to keep tests/dev smooth.
REGISTER_RATE_LIMIT = "5/minute" if settings.ENV.lower() == "prod" else "50/minute"


@router.post("/signup/request", response_model=schemas.MessageOut)
@limiter.limit(RATE_LIMITS["signup_request"])
def request_signup(request: Request, payload: schemas.SignupStart, svc: AuthServiceDep):
    """Request signup OTP via phone OR email."""
    try:
        svc.start_signup(payload)
        metrics.otp_signup_requested()
        
        # Determine delivery method for response message
        if payload.email:
            return schemas.MessageOut(detail="OTP sent to email")
        else:
            return schemas.MessageOut(detail="OTP sent to WhatsApp")
            
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _bundle_to_response(bundle: TokenBundle, request: Request | None = None, include_refresh_cookie: bool = True) -> JSONResponse:
    token_out = schemas.TokenOut(
        access_token=bundle.access_token,
        access_expires_at=bundle.access_expires_at,
        refresh_token=bundle.refresh_token,
    )
    response = JSONResponse(content=jsonable_encoder(token_out))
    if include_refresh_cookie:
        _set_refresh_cookie(response, bundle.refresh_token)
    
    # Set CSRF token on successful authentication
    if request:
        csrf_token = get_csrf_token(request)
        secure = settings.ENV.lower() in {"prod", "production"}
        set_csrf_cookie(response, csrf_token, secure=secure)
    
    return response


REFRESH_COOKIE_NAME = "whatsinvoice.refresh"


def _cookie_settings() -> dict[str, object]:
    secure = settings.ENV.lower() in {"prod", "production"}
    lifespan = timedelta(days=14)
    max_age = int(lifespan.total_seconds())
    expires = datetime.now(timezone.utc) + lifespan
    # Stricter SameSite policy in production to mitigate CSRF; keep lax elsewhere for local dev
    samesite = "strict" if secure else "lax"
    return {
        "httponly": True,
        "secure": secure,
        "samesite": samesite,
        "max_age": max_age,
        "expires": expires,
        "path": "/",
    }


def _set_refresh_cookie(response: JSONResponse, token: str) -> None:
    response.set_cookie(REFRESH_COOKIE_NAME, token, **_cookie_settings())


def _clear_refresh_cookie(response: JSONResponse) -> None:
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/")


@router.post("/signup/verify", response_model=schemas.TokenOut)
@limiter.limit(RATE_LIMITS["signup_verify"])
def verify_signup(request: Request, payload: schemas.SignupVerify, svc: AuthServiceDep):
    try:
        bundle = svc.complete_signup(payload)
        metrics.otp_signup_verified()
        log_audit_event("auth.signup.verify", user_id=bundle.user_id)
        return _bundle_to_response(bundle, request=request)
    except ValueError as exc:
        log_failure("auth.signup.verify", user_id=None, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login/request", response_model=schemas.MessageOut)
@limiter.limit(RATE_LIMITS["login_request"])
def request_login(request: Request, payload: schemas.OTPPhoneRequest | schemas.OTPEmailRequest, svc: AuthServiceDep):
    """Request login OTP via phone OR email."""
    try:
        svc.request_login(payload)
        metrics.otp_login_requested()
        log_audit_event("auth.login.request", user_id=None, method=("email" if hasattr(payload, 'email') else "phone"))
        
        # Determine delivery method for response
        if hasattr(payload, 'email'):
            return schemas.MessageOut(detail="OTP sent to email")
        else:
            return schemas.MessageOut(detail="OTP sent to WhatsApp")
            
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login/verify", response_model=schemas.TokenOut)
@limiter.limit(RATE_LIMITS["login_verify"])
def verify_login(request: Request, payload: schemas.LoginVerify, svc: AuthServiceDep):
    try:
        bundle = svc.verify_login(payload)
        metrics.otp_login_verified()
        log_audit_event("auth.login.verify", user_id=bundle.user_id)
        return _bundle_to_response(bundle, request=request)
    except ValueError as exc:
        log_failure("auth.login.verify", user_id=None, error=str(exc))
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/otp/resend", response_model=schemas.MessageOut)
@limiter.limit(RATE_LIMITS["otp_resend"])
def resend_otp(request: Request, payload: schemas.OTPResend, svc: AuthServiceDep):
    """Resend OTP for phone OR email."""
    try:
        metrics.otp_resend_attempt()
        svc.resend_otp(payload)
        log_audit_event("auth.otp.resend", user_id=None, method=("email" if payload.email else "phone"))
        
        # Determine delivery method for response
        if payload.email:
            return schemas.MessageOut(detail="OTP resent to email")
        else:
            return schemas.MessageOut(detail="OTP resent to WhatsApp")
            
    except ValueError as exc:
        # Cooldown or other resend restriction
        metrics.otp_resend_blocked()
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.post("/refresh", response_model=schemas.TokenOut)
@limiter.limit(RATE_LIMITS["refresh"])
def refresh_token(request: Request, svc: AuthServiceDep, payload: schemas.RefreshRequest | None = None):
    refresh_value = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_value and payload and payload.refresh_token:
        refresh_value = payload.refresh_token
    if not refresh_value:
        log_failure("auth.refresh", user_id=None, error="missing_refresh_token")
        raise HTTPException(status_code=401, detail="Missing refresh token")
    try:
        bundle = svc.refresh(refresh_value)
        # Extract user_id from the new access token
        from app.core.security import decode_token, TokenType
        token_payload = decode_token(bundle.access_token, expected_type=TokenType.ACCESS)
        user_id = int(token_payload["sub"])
        log_audit_event("auth.refresh", user_id=user_id)
        return _bundle_to_response(bundle, request=request)
    except ValueError as exc:
        log_failure("auth.refresh", user_id=None, error=str(exc))
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/logout", response_model=schemas.MessageOut)
def logout(request: Request):
    response = JSONResponse(status_code=200, content={"detail": "Logged out"})
    _clear_refresh_cookie(response)
    log_audit_event("auth.logout", user_id=None)
    return response


def get_current_user_id(authorization: str = Header(None)) -> int:
    if not authorization or not authorization.lower().startswith("bearer "):
        log_failure("auth.token.parse", user_id=None, error="missing_token")
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
        return int(payload["sub"])  # type: ignore
    except TokenExpiredError as exc:
        log_failure("auth.token.expired", user_id=None, error="expired")
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except TokenValidationError as exc:
        log_failure("auth.token.invalid", user_id=None, error="invalid")
        raise HTTPException(status_code=401, detail="Invalid token") from exc

# Legacy password-based endpoints removed (migrated fully to OTP flows).
