from __future__ import annotations

import hashlib
import hmac
import logging
from decimal import Decimal
from typing import Protocol

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


class PaymentProvider(Protocol):
    name: str

    def create_payment_link(
        self,
        reference: str,
        amount: Decimal,
        email: str | None = None,
    ) -> str: ...  # noqa: D401,E701

    def verify_webhook(
        self,
        raw_body: bytes,
        signature: str | None,
    ) -> bool: ...  # noqa: D401,E701


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


class FlutterwaveProvider:
    name = "flutterwave"

    def __init__(self, secret: str):
        self.secret = secret
        self.base = "https://api.flutterwave.com/v3"

    def create_payment_link(self, reference: str, amount: Decimal, email: str | None = None) -> str:
        payload = {
            "tx_ref": reference,
            "amount": str(amount),
            "currency": "NGN",  # could be configurable
            "redirect_url": f"{settings.FRONTEND_URL}/payments/confirm",
            "customer": {"email": email or "placeholder@example.com"},
            "customizations": {"title": "Invoice Payment", "description": reference},
        }
        try:
            r = requests.post(
                f"{self.base}/payments",
                headers={"Authorization": f"Bearer {self.secret}"},
                json=payload,
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            link = data.get("data", {}).get("link")
            if link:
                return link
        except Exception as e:  # noqa: BLE001
            logger.warning("Flutterwave init failed: %s", e)
        return f"https://flutterwave.example/{reference}"

    def verify_webhook(self, raw_body: bytes, signature: str | None) -> bool:
        # Flutterwave webhooks send hash in 'verif-hash' header that should equal secret key
        if not signature:
            return False
        return hmac.compare_digest(signature, self.secret)


class PaymentRouter:
    """
    Routes payments to appropriate provider using business's own credentials.
    
    Important: Each business uses their own Paystack/Flutterwave account.
    Money flows directly to business's bank account, not through SuoPay.
    """
    
    def __init__(self, primary: str, paystack_secret_key: str | None = None, flutterwave_secret_key: str | None = None):
        """
        Initialize payment router.
        
        Args:
            primary: Primary provider ('paystack' or 'flutterwave')
            paystack_secret_key: Business's Paystack secret key (optional, uses platform default if None)
            flutterwave_secret_key: Business's Flutterwave secret key (optional)
        """
        # Use business's keys if provided, otherwise fall back to platform keys (for testing)
        paystack_key = paystack_secret_key or settings.PAYSTACK_SECRET
        flutterwave_key = flutterwave_secret_key or settings.FLUTTERWAVE_SECRET
        
        self.providers: dict[str, PaymentProvider] = {
            "paystack": PaystackProvider(paystack_key),
            "flutterwave": FlutterwaveProvider(flutterwave_key),
        }
        self.primary = primary if primary in self.providers else "paystack"

    def _get_provider(self, provider: str | None = None) -> PaymentProvider:
        if provider is None:
            return self.providers[self.primary]
        if provider not in self.providers:
            raise ValueError(f"Unsupported payment provider '{provider}'")
        return self.providers[provider]

    def create_payment_link(self, reference: str, amount: Decimal, email: str | None = None) -> str:
        return self._get_provider().create_payment_link(reference, amount, email)

    def verify_webhook(
        self,
        raw_body: bytes,
        signature: str | None,
        provider: str | None = None,
    ) -> bool:
        return self._get_provider(provider).verify_webhook(raw_body, signature)
