from __future__ import annotations

import hashlib
import hmac
import logging
from decimal import Decimal

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


class PaystackProvider:
    name = "paystack"

    def __init__(self, secret: str):
        self.secret = secret
        self.base = "https://api.paystack.co"

    def create_payment_link(self, reference: str, amount: Decimal, email: str | None = None) -> str:
        payload = {
            "reference": reference,
            "amount": int(Decimal(amount) * 100),
            "email": email or "placeholder@example.com",
            "callback_url": f"{settings.FRONTEND_URL}/payments/confirm",
        }
        try:
            r = requests.post(
                f"{self.base}/transaction/initialize",
                headers={"Authorization": f"Bearer {self.secret}"},
                json=payload,
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            return data.get("data", {}).get("authorization_url", "https://paystack.com")
        except Exception as e:  # noqa: BLE001
            logger.warning("Paystack init failed: %s", e)
            return f"https://pay.example.com/{reference}"

    def verify_webhook(self, raw_body: bytes, signature: str | None) -> bool:
        if not signature:
            return False
        digest = hmac.new(self.secret.encode(), raw_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(digest, signature)


class PaymentRouter:
    """Single-provider router for Paystack integrations."""

    def __init__(self, paystack_secret_key: str):
        if not paystack_secret_key:
            raise ValueError("Paystack secret key is required")
        self.provider = PaystackProvider(paystack_secret_key)

    def create_payment_link(self, reference: str, amount: Decimal, email: str | None = None) -> str:
        return self.provider.create_payment_link(reference, amount, email)

    def verify_webhook(self, raw_body: bytes, signature: str | None) -> bool:
        return self.provider.verify_webhook(raw_body, signature)
