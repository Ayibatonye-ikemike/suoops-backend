from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.rate_limit import limiter
from app.core.config import settings
from app.core.security import TokenExpiredError, TokenValidationError, decode_token
from app.models import schemas
from app.services.auth_service import AuthService, TokenBundle, get_auth_service

router = APIRouter()

AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


# Allow more generous registration throughput outside prod to keep tests/dev smooth.
REGISTER_RATE_LIMIT = "5/minute" if settings.ENV.lower() == "prod" else "50/minute"


@router.post("/signup/request", response_model=schemas.MessageOut)
@limiter.limit(REGISTER_RATE_LIMIT)
def request_signup(request: Request, payload: schemas.SignupStart, svc: AuthServiceDep):
    """Request signup OTP via phone OR email."""
    try:
        svc.start_signup(payload)
        
        # Determine delivery method for response message
        if payload.email:
            return schemas.MessageOut(detail="OTP sent to email")
        else:
            return schemas.MessageOut(detail="OTP sent to WhatsApp")
            
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _bundle_to_response(bundle: TokenBundle, include_refresh_cookie: bool = True) -> JSONResponse:
    token_out = schemas.TokenOut(
        access_token=bundle.access_token,
        access_expires_at=bundle.access_expires_at,
        refresh_token=bundle.refresh_token,
    )
    response = JSONResponse(content=jsonable_encoder(token_out))
    if include_refresh_cookie:
        _set_refresh_cookie(response, bundle.refresh_token)
    return response


REFRESH_COOKIE_NAME = "whatsinvoice.refresh"


def _cookie_settings() -> dict[str, object]:
    secure = settings.ENV.lower() in {"prod", "production"}
    lifespan = timedelta(days=14)
    max_age = int(lifespan.total_seconds())
    expires = datetime.now(timezone.utc) + lifespan
    return {
        "httponly": True,
        "secure": secure,
        "samesite": "lax",
        "max_age": max_age,
        "expires": expires,
        "path": "/",
    }


def _set_refresh_cookie(response: JSONResponse, token: str) -> None:
    response.set_cookie(REFRESH_COOKIE_NAME, token, **_cookie_settings())


def _clear_refresh_cookie(response: JSONResponse) -> None:
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/")


@router.post("/signup/verify", response_model=schemas.TokenOut)
@limiter.limit("10/minute")
def verify_signup(request: Request, payload: schemas.SignupVerify, svc: AuthServiceDep):
    try:
        bundle = svc.complete_signup(payload)
        return _bundle_to_response(bundle)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login/request", response_model=schemas.MessageOut)
@limiter.limit("10/minute")
def request_login(request: Request, payload: schemas.OTPPhoneRequest | schemas.OTPEmailRequest, svc: AuthServiceDep):
    """Request login OTP via phone OR email."""
    try:
        svc.request_login(payload)
        
        # Determine delivery method for response
        if hasattr(payload, 'email'):
            return schemas.MessageOut(detail="OTP sent to email")
        else:
            return schemas.MessageOut(detail="OTP sent to WhatsApp")
            
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login/verify", response_model=schemas.TokenOut)
@limiter.limit("10/minute")
def verify_login(request: Request, payload: schemas.LoginVerify, svc: AuthServiceDep):
    try:
        bundle = svc.verify_login(payload)
        return _bundle_to_response(bundle)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/otp/resend", response_model=schemas.MessageOut)
@limiter.limit("10/minute")
def resend_otp(request: Request, payload: schemas.OTPResend, svc: AuthServiceDep):
    """Resend OTP for phone OR email."""
    try:
        svc.resend_otp(payload)
        
        # Determine delivery method for response
        if payload.email:
            return schemas.MessageOut(detail="OTP resent to email")
        else:
            return schemas.MessageOut(detail="OTP resent to WhatsApp")
            
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.post("/refresh", response_model=schemas.TokenOut)
@limiter.limit("20/minute")
def refresh_token(request: Request, svc: AuthServiceDep, payload: schemas.RefreshRequest | None = None):
    refresh_value = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_value and payload and payload.refresh_token:
        refresh_value = payload.refresh_token
    if not refresh_value:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    try:
        bundle = svc.refresh(refresh_value)
        return _bundle_to_response(bundle)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/logout", response_model=schemas.MessageOut)
def logout(request: Request):
    response = JSONResponse(status_code=200, content={"detail": "Logged out"})
    _clear_refresh_cookie(response)
    return response


def get_current_user_id(authorization: str = Header(None)) -> int:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
        return int(payload["sub"])  # type: ignore
    except TokenExpiredError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except TokenValidationError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
