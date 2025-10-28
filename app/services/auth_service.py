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
)
from app.db.session import get_db
from app.models import models, schemas
from app.services.otp_service import OTPService


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str
    access_expires_at: datetime


class AuthService:
    def __init__(self, db: Session, otp_service: OTPService):
        self.db = db
        self.otp = otp_service

    # ----------------------------- Signup -----------------------------

    def start_signup(self, payload: schemas.SignupStart) -> None:
        phone = self._normalize_phone(payload.phone)
        existing = (
            self.db.query(models.User)
            .filter(models.User.phone == phone)
            .one_or_none()
        )
        if existing:
            raise ValueError("Phone number already registered")
        data = payload.model_dump()
        data["phone"] = phone
        self.otp.request_signup(phone, data)

    def complete_signup(self, payload: schemas.SignupVerify) -> TokenBundle:
        phone = self._normalize_phone(payload.phone)
        stored_data = self.otp.complete_signup(phone, payload.otp)

        # Guard against race-condition: if user already created after OTP issuance
        existing = (
            self.db.query(models.User)
            .filter(models.User.phone == phone)
            .one_or_none()
        )
        if existing:
            if not existing.phone_verified:
                existing.phone_verified = True
                self.db.commit()
            return self._issue_tokens(existing)

        user = models.User(
            phone=stored_data["phone"],
            name=stored_data.get("name", stored_data["phone"]),
            business_name=stored_data.get("business_name"),
            phone_verified=True,
        )
        user.last_login = datetime.now(timezone.utc)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return self._issue_tokens(user)

    # ----------------------------- Login -----------------------------

    def request_login(self, payload: schemas.OTPPhoneRequest) -> None:
        phone = self._normalize_phone(payload.phone)
        user = (
            self.db.query(models.User)
            .filter(models.User.phone == phone)
            .one_or_none()
        )
        if not user:
            raise ValueError("Phone number not registered")
        self.otp.request_login(phone)

    def verify_login(self, payload: schemas.LoginVerify) -> TokenBundle:
        phone = self._normalize_phone(payload.phone)
        if not self.otp.verify_otp(phone, payload.otp, "login"):
            raise ValueError("Invalid or expired OTP")
        user = (
            self.db.query(models.User)
            .filter(models.User.phone == phone)
            .one_or_none()
        )
        if not user:
            raise ValueError("User not found")
        user.last_login = datetime.now(timezone.utc)
        self.db.commit()
        return self._issue_tokens(user)

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

    def resend_otp(self, payload: schemas.OTPPhoneRequest, purpose: str) -> None:
        if purpose not in {"signup", "login"}:
            raise ValueError("Invalid OTP purpose")
        try:
            phone = self._normalize_phone(payload.phone)
            self.otp.resend_otp(phone, purpose)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    def _issue_tokens(self, user: models.User) -> TokenBundle:
        access = create_access_token(str(user.id))
        refresh = create_refresh_token(str(user.id))
        expires_at = self._extract_expiry(access, TokenType.ACCESS)
        return TokenBundle(access, refresh, expires_at)

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

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        sanitized = phone.strip().replace(" ", "")
        if not sanitized:
            raise ValueError("Phone number is required")
        if sanitized.startswith("+"):
            return sanitized
        digits = sanitized.lstrip("+")
        if digits.startswith("234"):
            return f"+{digits}"
        if digits.startswith("0"):
            return f"+234{digits[1:]}"
        return f"+{digits}"


def get_auth_service(db: Annotated[Session, Depends(get_db)]) -> AuthService:
    otp_service = OTPService()
    return AuthService(db, otp_service)
