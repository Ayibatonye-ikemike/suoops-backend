from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.encryption import encrypt_value
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.db.session import get_db
from app.models import models, schemas
from app.services.otp_service import OTPService

logger = logging.getLogger(__name__)


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    user_id: int


class AuthService:
    def __init__(self, db: Session, otp_service: OTPService):
        self.db = db
        self.otp = otp_service

    # ----------------------------- Signup -----------------------------

    def start_signup(
        self,
        payload: schemas.SignupStart,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Start signup with WhatsApp phone number.

        Phone is required — OTP is always sent via WhatsApp.
        Email is stored as optional profile data but never used for OTP.

        Captures anti-fraud context (IP, user-agent, device fingerprint) and
        hard-blocks clearly abusive signups before an OTP is ever sent.
        """
        from app.services.fraud_service import evaluate_signup, is_disposable_email

        identifier = self._normalize_phone(payload.phone)
        # Check if phone already registered
        existing = (
            self.db.query(models.User)
            .filter(models.User.phone == identifier)
            .one_or_none()
        )
        if existing:
            raise ValueError("An account with this identifier already exists")

        # ── Anti-fraud gate ──
        # Disposable email is an unambiguous fake-account signal → reject early
        # with an actionable message (legitimate SMEs never use these domains).
        if is_disposable_email(payload.email):
            raise ValueError(
                "Please sign up with a real email address (temporary/disposable "
                "email providers are not allowed)."
            )
        # Extreme velocity from one IP/device → refuse without tipping off the
        # abuser about which control fired.
        assessment = evaluate_signup(
            self.db,
            ip=ip,
            device_id=payload.device_fingerprint,
            email=payload.email,
            user_agent=user_agent,
        )
        if assessment.block:
            logger.warning(
                "Blocked signup attempt phone=%s ip=%s reason=%s signals=%s",
                identifier, ip, assessment.block_reason, assessment.signals,
            )
            raise ValueError(
                "We couldn't complete your signup right now. If you believe this "
                "is a mistake, please contact support@suoops.com."
            )

        data = payload.model_dump()
        logger.info(f"start_signup: payload data keys={list(data.keys())}, referral_code={data.get('referral_code')}")
        data["phone"] = identifier
        # Store email too if provided (but phone is the OTP identifier)
        if payload.email:
            data["email"] = payload.email.lower().strip()
        # Stash anti-fraud context so it survives until OTP verification.
        data["_signup_ip"] = ip
        data["_signup_user_agent"] = user_agent

        self.otp.request_signup(identifier, data)

    def complete_signup(self, payload: schemas.SignupVerify) -> TokenBundle:
        """Complete signup with WhatsApp OTP verification."""
        
        identifier = self._normalize_phone(payload.phone)
        
        stored_data = self.otp.complete_signup(identifier, payload.otp)

        # Guard against race-condition: if user already created after OTP issuance
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

        # Create new user — signup is always phone-based (WhatsApp)
        
        # Determine signup source: explicit from payload, or infer from context
        raw_source = stored_data.get("signup_source")
        if not raw_source and stored_data.get("referral_code"):
            raw_source = "referral"
        if not raw_source:
            raw_source = "organic"

        user_data = {
            "name": stored_data.get("name", identifier),
            "business_name": stored_data.get("business_name"),
            "phone": stored_data.get("phone") or identifier,
            "phone_verified": True,
            "signup_source": raw_source,
            "bank_name": payload.bank_name,
            "account_number": payload.account_number,
            "account_name": payload.account_name,
        }

        # ── Anti-fraud: persist signals captured at signup start ──
        signup_ip = stored_data.get("_signup_ip")
        signup_ua = stored_data.get("_signup_user_agent")
        device_id = stored_data.get("device_fingerprint")
        try:
            from app.services.fraud_service import evaluate_signup

            assessment = evaluate_signup(
                self.db,
                ip=signup_ip,
                device_id=device_id,
                email=stored_data.get("email"),
                user_agent=signup_ua,
            )
            user_data["signup_ip"] = signup_ip
            user_data["signup_device_id"] = device_id
            user_data["signup_user_agent"] = (signup_ua or "")[:400] or None
            user_data["risk_score"] = assessment.score
            user_data["risk_signals"] = assessment.signals or None
            user_data["flagged_for_review"] = assessment.flagged
            if assessment.flagged:
                logger.warning(
                    "Signup flagged for review phone=%s score=%d signals=%s",
                    identifier, assessment.score, assessment.signals,
                )
        except Exception as e:  # noqa: BLE001 — risk scoring must never block signup
            logger.warning("Risk evaluation failed for %s: %s", identifier, e)

        # Store email if provided (optional profile data)
        email_value = stored_data.get("email")
        if email_value:
            plaintext_email = email_value.lower().strip()
            encrypted_email = encrypt_value(plaintext_email)
            user_data["email"] = plaintext_email
            user_data["email_enc"] = encrypted_email
            
        user = models.User(**user_data)
        user.last_login = datetime.now(timezone.utc)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        # Credit bonus invoices if signed up through an influencer code
        referral_code_str = stored_data.get("referral_code")
        if referral_code_str:
            try:
                from app.services.referral_service import ReferralService
                ref_svc = ReferralService(self.db)
                code_obj = ref_svc.get_code_by_string(referral_code_str)
                if code_obj and code_obj.bonus_invoices > 0:
                    # Credit the influencer signup bonus to the wallet at ₦30 per
                    # bonus invoice (matching the migration rate) — commission model.
                    bonus_kobo = code_obj.bonus_invoices * 3000
                    user.wallet_balance_kobo += bonus_kobo
                    self.db.commit()
                    logger.info(
                        "Credited ₦%d bonus wallet to user %s via code %s",
                        bonus_kobo // 100, user.id, referral_code_str,
                    )
            except Exception as e:
                logger.warning("Failed to credit bonus invoices: %s", e)
        
        # Sync new user to Brevo (real-time)
        try:
            from app.services.brevo_service import sync_user_to_brevo_sync
            sync_user_to_brevo_sync(user)
        except Exception as e:
            logger.warning(f"Failed to sync user to Brevo: {e}")

        # Fire instant welcome message (async — doesn't block API response)
        try:
            from app.workers.tasks.welcome_tasks import send_instant_welcome
            send_instant_welcome.delay(user.id)
            logger.info("Queued instant welcome for user %s", user.id)
        except Exception as e:
            logger.warning(f"Failed to queue instant welcome: {e}")

        return self._issue_tokens(user)

    # ----------------------------- Login -----------------------------

    def request_login(self, payload: schemas.OTPPhoneRequest) -> None:
        """Request login OTP via phone OR email."""
        
        # Support both phone and email for login
        if hasattr(payload, 'email') and payload.email:
            identifier = payload.email.lower().strip()
            enc_identifier = encrypt_value(identifier)
            user = (
                self.db.query(models.User)
                .filter(
                    (models.User.email == identifier) |
                    (models.User.email_enc == enc_identifier)
                )
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
            raise ValueError("Invalid credentials")
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
            
        # Verify OTP (do NOT log the OTP code itself)
        otp_valid = self.otp.verify_otp(identifier, payload.otp, "login")
        logger.info(
            "OTP verification | identifier=%s... purpose=login valid=%s",
            identifier[:10],
            otp_valid,
        )
        if not otp_valid:
            raise ValueError("Invalid or expired OTP")
            
        if lookup_field == "email":
            enc_identifier = encrypt_value(identifier)
            user = (
                self.db.query(models.User)
                .filter(
                    (models.User.email == identifier) |
                    (models.User.email_enc == enc_identifier)
                )
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
        return TokenBundle(access, new_refresh, expires_at, user.id)

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
        access = create_access_token(str(user.id), user_plan=user.plan.value)
        refresh = create_refresh_token(str(user.id))
        expires_at = self._extract_expiry(access, TokenType.ACCESS)
        return TokenBundle(access, refresh, expires_at, user.id)

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
        from app.utils.phone import normalize_phone

        sanitized = phone.strip().replace(" ", "")
        if not sanitized:
            raise ValueError("Phone number is required")
        return normalize_phone(sanitized)


def get_auth_service(db: Annotated[Session, Depends(get_db)]) -> AuthService:
    otp_service = OTPService()
    return AuthService(db, otp_service)
