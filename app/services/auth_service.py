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
        """Start signup with phone OR email (temporary email support for pre-launch)."""
        
        # Validate that either phone or email is provided
        if not payload.phone and not payload.email:
            raise ValueError("Either phone or email is required")
        
        # For now, prioritize email if both are provided (pre-launch mode)
        if payload.email:
            identifier = payload.email.lower().strip()
            # Check if email already registered
            existing = (
                self.db.query(models.User)
                .filter(models.User.email == identifier)
                .one_or_none()
            )
            if existing:
                raise ValueError("Email already registered")
        else:
            identifier = self._normalize_phone(payload.phone)
            # Check if phone already registered
            existing = (
                self.db.query(models.User)
                .filter(models.User.phone == identifier)
                .one_or_none()
            )
            if existing:
                raise ValueError("Phone number already registered")
        
        data = payload.model_dump()
        if payload.email:
            data["email"] = identifier
        else:
            data["phone"] = identifier
            
        self.otp.request_signup(identifier, data)

    def complete_signup(self, payload: schemas.SignupVerify) -> TokenBundle:
        """Complete signup with phone OR email OTP verification."""
        
        # Determine identifier (email or phone)
        if payload.email:
            identifier = payload.email.lower().strip()
            lookup_field = "email"
        elif payload.phone:
            identifier = self._normalize_phone(payload.phone)
            lookup_field = "phone"
        else:
            raise ValueError("Either phone or email is required")
        
        stored_data = self.otp.complete_signup(identifier, payload.otp)

        # Guard against race-condition: if user already created after OTP issuance
        if lookup_field == "email":
            existing = (
                self.db.query(models.User)
                .filter(models.User.email == identifier)
                .one_or_none()
            )
        else:
            existing = (
                self.db.query(models.User)
                .filter(models.User.phone == identifier)
                .one_or_none()
            )
            
        if existing:
            if not existing.phone_verified:
                existing.phone_verified = True
                self.db.commit()
            return self._issue_tokens(existing)

        # Create new user with email or phone
        user_data = {
            "name": stored_data.get("name", identifier),
            "business_name": stored_data.get("business_name"),
            "phone_verified": True,
        }
        
        if "email" in stored_data:
            user_data["email"] = stored_data["email"]
            # For email signups, use email as phone temporarily (or make phone nullable)
            user_data["phone"] = stored_data["email"]  # Temporary
        else:
            # Some edge cases observed in tests where stored_data['phone'] persisted as None.
            # Always fall back to normalized identifier to satisfy NOT NULL constraint.
            user_data["phone"] = stored_data.get("phone") or identifier

        # Final safety: ensure phone is never None (model constraint) even if upstream data was missing.
        if not user_data.get("phone"):
            user_data["phone"] = identifier
            
        user = models.User(**user_data)
        user.last_login = datetime.now(timezone.utc)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return self._issue_tokens(user)

    # ----------------------------- Login -----------------------------

    def request_login(self, payload: schemas.OTPPhoneRequest) -> None:
        """Request login OTP via phone OR email."""
        
        # Support both phone and email for login
        if hasattr(payload, 'email') and payload.email:
            identifier = payload.email.lower().strip()
            user = (
                self.db.query(models.User)
                .filter(models.User.email == identifier)
                .one_or_none()
            )
        else:
            identifier = self._normalize_phone(payload.phone)
            user = (
                self.db.query(models.User)
                .filter(models.User.phone == identifier)
                .one_or_none()
            )
            
        if not user:
            raise ValueError("User not registered")
        self.otp.request_login(identifier)

    def verify_login(self, payload: schemas.LoginVerify) -> TokenBundle:
        """Verify login OTP for phone OR email."""
        
        # Determine identifier (email or phone)
        if payload.email:
            identifier = payload.email.lower().strip()
            lookup_field = "email"
        elif payload.phone:
            identifier = self._normalize_phone(payload.phone)
            lookup_field = "phone"
        else:
            raise ValueError("Either phone or email is required")
            
        if not self.otp.verify_otp(identifier, payload.otp, "login"):
            raise ValueError("Invalid or expired OTP")
            
        if lookup_field == "email":
            user = (
                self.db.query(models.User)
                .filter(models.User.email == identifier)
                .one_or_none()
            )
        else:
            user = (
                self.db.query(models.User)
                .filter(models.User.phone == identifier)
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

    def resend_otp(self, payload: schemas.OTPResend) -> None:
        """Resend OTP for phone OR email."""
        purpose = payload.purpose
        if purpose not in {"signup", "login"}:
            raise ValueError("Invalid OTP purpose")
        try:
            # Support both phone and email
            if payload.email:
                identifier = payload.email.lower().strip()
            elif payload.phone:
                identifier = self._normalize_phone(payload.phone)
            else:
                raise ValueError("Either phone or email is required")
                
            self.otp.resend_otp(identifier, purpose)
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
