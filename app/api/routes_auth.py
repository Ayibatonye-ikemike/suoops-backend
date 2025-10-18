from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.rate_limit import limiter
from app.core.config import settings
from app.core.security import TokenExpiredError, TokenValidationError, decode_token
from app.models import schemas
from app.services.auth_service import AuthService, get_auth_service

router = APIRouter()

AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


# Allow more generous registration throughput outside prod to keep tests/dev smooth.
REGISTER_RATE_LIMIT = "5/minute" if settings.ENV.lower() == "prod" else "50/minute"


@router.post("/register", response_model=schemas.UserOut)
@limiter.limit(REGISTER_RATE_LIMIT)
def register(request: Request, payload: schemas.UserCreate, svc: AuthServiceDep):
    try:
        return svc.register(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@router.post("/login", response_model=schemas.TokenOut)
@limiter.limit("10/minute")
def login(request: Request, payload: schemas.UserLogin, svc: AuthServiceDep):
    try:
        bundle = svc.login(payload)
        token_out = schemas.TokenOut(
            access_token=bundle.access_token,
            access_expires_at=bundle.access_expires_at,
        )
        response = JSONResponse(content=jsonable_encoder(token_out))
        _set_refresh_cookie(response, bundle.refresh_token)
        return response
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid credentials") from exc


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
        token_out = schemas.TokenOut(
            access_token=bundle.access_token,
            access_expires_at=bundle.access_expires_at,
        )
        response = JSONResponse(content=jsonable_encoder(token_out))
        _set_refresh_cookie(response, bundle.refresh_token)
        return response
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
