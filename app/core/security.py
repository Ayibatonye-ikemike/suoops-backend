from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import jwt
from jwt import ExpiredSignatureError
from jwt import InvalidTokenError as PyJWTInvalidTokenError
from passlib.context import CryptContext

from app.core.config import settings


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__truncate_error=True,
)

ALGORITHM = "HS256"


class TokenValidationError(Exception):
    """Raised when a token cannot be validated."""


class TokenExpiredError(TokenValidationError):
    """Raised when a token is expired."""


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_access_token(subject: str, expires_minutes: int = 60 * 24) -> str:
    return _create_token(subject, timedelta(minutes=expires_minutes), TokenType.ACCESS)


def create_refresh_token(subject: str, expires_days: int = 14) -> str:
    return _create_token(subject, timedelta(days=expires_days), TokenType.REFRESH)


def decode_token(token: str, expected_type: TokenType = TokenType.ACCESS) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    except ExpiredSignatureError as exc:
        raise TokenExpiredError("Token has expired") from exc
    except PyJWTInvalidTokenError as exc:
        raise TokenValidationError("Token is invalid") from exc
    token_type = payload.get("type", TokenType.ACCESS.value)
    if token_type != expected_type.value:
        raise TokenValidationError("Token type mismatch")
    return payload


def validate_password_strength(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if password.isdigit() or password.isalpha():
        raise ValueError("Password must include both letters and numbers")
    if password.lower() == password or password.upper() == password:
        raise ValueError("Password must include mixed case characters")


def _create_token(subject: str, delta: timedelta, token_type: TokenType) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + delta,
        "type": token_type.value,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)
