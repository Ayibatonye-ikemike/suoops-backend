"""Services for generating, sending, and verifying WhatsApp OTP codes."""

from __future__ import annotations

import json
import logging
import random
import string
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
import ssl

import redis

from app.bot.whatsapp_client import WhatsAppClient
from app.core.config import settings

logger = logging.getLogger(__name__)


class OTPDeliveryClient(Protocol):
    """Protocol describing the interface required for sending OTP messages."""

    def send_text(self, to: str, body: str) -> None:  # pragma: no cover - protocol stub
        ...


@dataclass
class OTPRecord:
    """Represents an OTP stored for a phone number and purpose."""

    code: str
    attempts: int
    created_at: float

    def serialize(self) -> str:
        return json.dumps({"code": self.code, "attempts": self.attempts, "created_at": self.created_at})

    @classmethod
    def deserialize(cls, payload: str) -> "OTPRecord":
        data = json.loads(payload)
        return cls(code=data["code"], attempts=int(data.get("attempts", 0)), created_at=float(data["created_at"]))


class BaseKeyValueStore(Protocol):
    """Minimal key-value interface used by the OTP service."""

    def set(self, key: str, value: str, ttl_seconds: int) -> None:  # pragma: no cover - protocol stub
        ...

    def get(self, key: str) -> str | None:  # pragma: no cover - protocol stub
        ...

    def delete(self, key: str) -> None:  # pragma: no cover - protocol stub
        ...


class RedisStore(BaseKeyValueStore):
    """Redis-backed store for OTP codes and signup sessions."""

    def __init__(self, url: str) -> None:
        options: dict[str, Any] = {"decode_responses": True}

        ssl_mode = getattr(settings, "REDIS_SSL_CERT_REQS", None)
        if ssl_mode:
            ssl_map = {
                "required": ssl.CERT_REQUIRED,
                "optional": ssl.CERT_OPTIONAL,
                "none": ssl.CERT_NONE,
            }
            chosen = ssl_map.get(str(ssl_mode).lower())
            if chosen is not None:
                options["ssl_cert_reqs"] = chosen
        if getattr(settings, "REDIS_SSL_CA_CERTS", None):
            options["ssl_ca_certs"] = settings.REDIS_SSL_CA_CERTS

        self._client = redis.Redis.from_url(url, **options)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._client.setex(key, ttl_seconds, value)

    def get(self, key: str) -> str | None:
        return self._client.get(key)

    def delete(self, key: str) -> None:
        self._client.delete(key)


class InMemoryStore(BaseKeyValueStore):
    """Fallback in-memory store used for tests or when Redis is unavailable."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float]] = {}

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        expires_at = time.time() + ttl_seconds
        self._data[key] = (value, expires_at)

    def get(self, key: str) -> str | None:
        entry = self._data.get(key)
        if not entry:
            return None
        value, expires_at = entry
        if time.time() > expires_at:
            self._data.pop(key, None)
            return None
        return value

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


_SHARED_STORE: BaseKeyValueStore | None = None


def _build_store() -> BaseKeyValueStore:
    global _SHARED_STORE
    if _SHARED_STORE is not None:
        return _SHARED_STORE
    redis_url = getattr(settings, "REDIS_URL", "")
    if redis_url:
        try:
            store = RedisStore(redis_url)
            store.set("__otp_healthcheck__", "ok", ttl_seconds=5)
            store.delete("__otp_healthcheck__")
            _SHARED_STORE = store
            return store
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falling back to in-memory OTP store: %s", exc)
    _SHARED_STORE = InMemoryStore()
    return _SHARED_STORE


class OTPService:
    """Generate, send, and validate OTP codes for signup and login flows."""

    DEFAULT_DIGITS = 6
    OTP_TTL = 10 * 60  # 10 minutes
    SIGNUP_SESSION_TTL = 30 * 60  # 30 minutes
    RESEND_COOLDOWN = 60  # 1 minute between resend attempts
    MAX_ATTEMPTS = 3

    def __init__(
        self,
        store: BaseKeyValueStore | None = None,
        delivery: OTPDeliveryClient | None = None,
        otp_length: int = DEFAULT_DIGITS,
    ) -> None:
        self._store = store or _build_store()
        self._delivery = delivery or WhatsAppClient(settings.WHATSAPP_API_KEY)
        self._otp_length = otp_length

    @staticmethod
    def _otp_key(phone: str, purpose: str) -> str:
        return f"otp:{purpose}:{phone}"

    @staticmethod
    def _signup_key(phone: str) -> str:
        return f"signup-data:{phone}"

    def request_signup(self, phone: str, payload: dict[str, Any]) -> None:
        """Start signup by persisting user-provided data and sending OTP."""
        self._store.set(self._signup_key(phone), json.dumps(payload), self.SIGNUP_SESSION_TTL)
        self._send_otp(phone, purpose="signup")

    def complete_signup(self, phone: str, otp: str) -> dict[str, Any]:
        """Validate OTP and return stored signup data."""
        if not self.verify_otp(phone, otp, purpose="signup"):
            raise ValueError("Invalid or expired OTP")
        raw_payload = self._store.get(self._signup_key(phone))
        if not raw_payload:
            raise ValueError("Signup session expired")
        self._store.delete(self._signup_key(phone))
        return json.loads(raw_payload)

    def request_login(self, phone: str) -> None:
        """Send OTP for login."""
        self._send_otp(phone, purpose="login")

    def verify_otp(self, phone: str, otp: str, purpose: str) -> bool:
        key = self._otp_key(phone, purpose)
        raw_record = self._store.get(key)
        if not raw_record:
            return False
        record = OTPRecord.deserialize(raw_record)
        if record.attempts >= self.MAX_ATTEMPTS:
            self._store.delete(key)
            return False
        if record.code != otp:
            record.attempts += 1
            self._store.set(key, record.serialize(), int(self.OTP_TTL))
            return False
        self._store.delete(key)
        return True

    def resend_otp(self, phone: str, purpose: str) -> None:
        key = self._otp_key(phone, purpose)
        raw_record = self._store.get(key)
        if raw_record:
            record = OTPRecord.deserialize(raw_record)
            elapsed = datetime.now(timezone.utc).timestamp() - record.created_at
            if elapsed < self.RESEND_COOLDOWN:
                raise ValueError("Please wait before requesting another code")
        self._send_otp(phone, purpose)

    def _send_otp(self, phone: str, purpose: str) -> None:
        code = self._generate_code()
        now_ts = datetime.now(timezone.utc).timestamp()
        record = OTPRecord(code=code, attempts=0, created_at=now_ts)
        self._store.set(self._otp_key(phone, purpose), record.serialize(), self.OTP_TTL)
        message = self._format_message(code, purpose)
        self._delivery.send_text(phone, message)

    def _generate_code(self) -> str:
        return "".join(random.choices(string.digits, k=self._otp_length))

    def _format_message(self, otp: str, purpose: str) -> str:
        action = "complete your signup" if purpose == "signup" else "login securely"
        return (
            "SuoPay Verification Code\n\n"
            f"Your OTP is {otp}.\n\n"
            f"Enter this code to {action}.\n"
            "This code expires in 10 minutes.\n\n"
            "If you did not request this code, please ignore this message."
        )
