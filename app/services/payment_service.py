from __future__ import annotations

import logging
from decimal import Decimal

from app.core.config import settings
from app.services.payment_providers import PaymentRouter

logger = logging.getLogger(__name__)


class PaymentService:
    """Facade over payment providers via PaymentRouter."""

    def __init__(self):
        primary_provider = getattr(settings, "PRIMARY_PAYMENT_PROVIDER", "paystack")
        self.router = PaymentRouter(primary=primary_provider)

    def create_payment_link(self, reference: str, amount: Decimal) -> str:
        return self.router.create_payment_link(reference, amount)

    def verify_webhook(
        self,
        raw_body: bytes,
        signature: str | None,
        provider: str | None = None,
    ) -> bool:
        return self.router.verify_webhook(raw_body, signature, provider)

