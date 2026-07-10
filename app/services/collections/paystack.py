"""Paystack collector — the default rail (collects to the SuoOps balance)."""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings
from app.services.payouts.paystack import paystack_refund

from .base import ChargeInit, ChargeStatus, CollectionError, CollectionProvider

logger = logging.getLogger(__name__)

_PAYSTACK_BASE = "https://api.paystack.co"


def _headers() -> dict[str, str]:
    if not settings.PAYSTACK_SECRET:
        raise CollectionError("PAYSTACK_SECRET is not configured")
    return {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET}",
        "Content-Type": "application/json",
    }


def _normalize_status(raw_status: str | None) -> str:
    s = (raw_status or "").strip().lower()
    if s == "success":
        return "successful"
    if s in {"failed", "reversed", "abandoned"}:
        return "failed"
    if s in {"pending", "ongoing", "processing", "queued"}:
        return "pending"
    return "unknown"


class PaystackCollectionProvider(CollectionProvider):
    """Collects the held amount to the SuoOps Paystack balance (no subaccount)."""

    name = "paystack"

    def initialize_hold_charge(
        self,
        *,
        amount_kobo: int,
        reference: str,
        customer_email: str,
        customer_phone: str | None,
        customer_name: str | None,
        callback_url: str,
        narration: str,
        metadata: dict,
    ) -> ChargeInit:
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(
                    f"{_PAYSTACK_BASE}/transaction/initialize",
                    headers=_headers(),
                    json={
                        "email": customer_email,
                        "amount": int(amount_kobo),  # kobo
                        "reference": reference,
                        "callback_url": callback_url,
                        "metadata": metadata,
                    },
                )
            data = resp.json()
        except Exception as exc:  # noqa: BLE001 — network/timeout
            raise CollectionError(f"Charge init failed: {exc}") from exc
        if not data.get("status"):
            raise CollectionError(data.get("message", "Charge initialization failed"))
        url = (data.get("data") or {}).get("authorization_url")
        if not url:
            raise CollectionError("Paystack did not return an authorization_url")
        return ChargeInit(authorization_url=url, reference=reference, provider=self.name, raw=data)

    def verify_charge(self, reference: str) -> ChargeStatus:
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(
                    f"{_PAYSTACK_BASE}/transaction/verify/{reference}", headers=_headers()
                )
            data = resp.json()
        except Exception:  # noqa: BLE001 — transport error → indeterminate
            return ChargeStatus(status="unknown")
        if not data.get("status"):
            return ChargeStatus(status="unknown", raw=data)
        d = data.get("data") or {}
        return ChargeStatus(
            status=_normalize_status(d.get("status")),
            amount_kobo=d.get("amount"),
            currency=d.get("currency"),
            provider_tx_id=str(d.get("id")) if d.get("id") is not None else None,
            raw=data,
        )

    def refund(self, *, reference: str, amount_kobo: int, note: str) -> dict:
        try:
            return paystack_refund(
                charge_reference=reference, amount_kobo=amount_kobo, note=note
            )
        except Exception as exc:  # noqa: BLE001 — surface as CollectionError
            raise CollectionError(str(exc)) from exc
