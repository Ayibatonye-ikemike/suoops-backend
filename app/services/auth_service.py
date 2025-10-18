from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.db.session import get_db
from app.models import models, schemas


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str
    access_expires_at: datetime


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def register(self, payload: schemas.UserCreate) -> models.User:
        existing = (
            self.db.query(models.User)
            .filter(models.User.phone == payload.phone)
            .one_or_none()
        )
        if existing:
            raise ValueError("User already exists")
        validate_password_strength(payload.password)
        user = models.User(
            phone=payload.phone,
            name=payload.name,
            hashed_password=hash_password(payload.password),
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def login(self, payload: schemas.UserLogin) -> TokenBundle:
        user = self.db.query(models.User).filter(models.User.phone == payload.phone).one_or_none()
        if not user or not verify_password(payload.password, user.hashed_password):
            raise ValueError("Invalid credentials")
        access = create_access_token(str(user.id))
        refresh = create_refresh_token(str(user.id))
        expires_at = self._extract_expiry(access, TokenType.ACCESS)
        return TokenBundle(access, refresh, expires_at)

    def get_user(self, user_id: int) -> models.User | None:
        return self.db.query(models.User).filter(models.User.id == user_id).one_or_none()

    def refresh(self, refresh_token: str) -> TokenBundle:
        payload = decode_token(refresh_token, expected_type=TokenType.REFRESH)
        user_id = int(payload["sub"])  # type: ignore
        user = self.get_user(user_id)
        if not user:
            raise ValueError("User no longer exists")
        access = create_access_token(str(user.id))
        new_refresh = create_refresh_token(str(user.id))
        expires_at = self._extract_expiry(access, TokenType.ACCESS)
        return TokenBundle(access, new_refresh, expires_at)

    @staticmethod
    def _extract_expiry(token: str, token_type: TokenType) -> datetime:
        payload = decode_token(token, expected_type=token_type)
        raw_exp = payload["exp"]
        if isinstance(raw_exp, (int, float)):
            return datetime.fromtimestamp(raw_exp, tz=timezone.utc)
        if isinstance(raw_exp, str):
            try:
                return datetime.fromisoformat(raw_exp)
            except ValueError:
                pass
        raise ValueError("Unable to determine token expiry")


def get_auth_service(db: Annotated[Session, Depends(get_db)]) -> AuthService:
    return AuthService(db)
