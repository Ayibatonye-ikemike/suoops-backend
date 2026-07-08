"""Select the active payout provider from configuration."""
from __future__ import annotations

from app.core.config import settings

from .base import PayoutProvider


def get_payout_provider() -> PayoutProvider:
    """Return the configured payout provider (default: Paystack)."""
    name = (settings.ESCROW_PAYOUT_PROVIDER or "paystack").strip().lower()
    if name == "flutterwave":
        from .flutterwave import FlutterwavePayoutProvider

        return FlutterwavePayoutProvider()
    # Default / fallback — Paystack.
    from .paystack import PaystackPayoutProvider

    return PaystackPayoutProvider()
