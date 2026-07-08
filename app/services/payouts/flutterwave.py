"""Flutterwave payout provider (alternative rail).

Off unless ``settings.ESCROW_PAYOUT_PROVIDER == "flutterwave"`` and
``FLUTTERWAVE_SECRET`` is set. Flutterwave has no persistent "recipient" — each
transfer carries the destination bank + account directly. Amounts are in the
major unit (Naira), so we convert from kobo.

NOTE: needs a live sandbox run before enabling in production — behaviour is
built from Flutterwave's public v3 Transfers docs but not exercised against a
real account here.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings

from .base import PayoutError, PayoutProvider, PayoutResult

if TYPE_CHECKING:  # pragma: no cover
    from app.models import models

logger = logging.getLogger(__name__)

# Cached Flutterwave NG bank list (normalized name -> code).
_fw_bank_cache: dict[str, str] = {}
_fw_bank_cache_at: float = 0.0
_BANK_CACHE_TTL = 24 * 60 * 60  # 24h


def _normalize_bank_name(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


class FlutterwavePayoutProvider(PayoutProvider):
    """Pays sellers via the Flutterwave v3 Transfers API."""

    name = "flutterwave"

    def _base(self) -> str:
        return settings.FLUTTERWAVE_BASE.rstrip("/")

    def _headers(self) -> dict[str, str]:
        if not settings.FLUTTERWAVE_SECRET:
            raise PayoutError("FLUTTERWAVE_SECRET is not configured")
        return {
            "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET}",
            "Content-Type": "application/json",
        }

    def _resolve_bank_code(self, bank_name: str) -> str:
        global _fw_bank_cache, _fw_bank_cache_at

        now = time.time()
        if not _fw_bank_cache or (now - _fw_bank_cache_at) > _BANK_CACHE_TTL:
            with httpx.Client(timeout=20) as client:
                resp = client.get(f"{self._base()}/v3/banks/NG", headers=self._headers())
            data = resp.json()
            if data.get("status") != "success":
                raise PayoutError(f"Could not load bank list: {data.get('message')}")
            _fw_bank_cache = {
                _normalize_bank_name(b["name"]): str(b["code"])
                for b in data.get("data", [])
                if b.get("name") and b.get("code")
            }
            _fw_bank_cache_at = now

        code = _fw_bank_cache.get(_normalize_bank_name(bank_name))
        if not code:
            raise PayoutError(f"Unknown bank: {bank_name!r}")
        return code

    def transfer(
        self,
        db: Session,
        *,
        seller: "models.User",
        amount_kobo: int,
        reference: str,
        reason: str,
    ) -> PayoutResult:
        account_number = seller.payout_account_number or seller.account_number
        bank_name = seller.payout_bank_name or seller.bank_name
        if not (account_number and bank_name):
            raise PayoutError("Seller has no bank details set for payouts")

        bank_code = self._resolve_bank_code(bank_name)
        try:
            with httpx.Client(timeout=20) as client:
                resp = client.post(
                    f"{self._base()}/v3/transfers",
                    headers=self._headers(),
                    json={
                        "account_bank": bank_code,
                        "account_number": account_number,
                        "amount": round(amount_kobo / 100, 2),  # Naira (major unit)
                        "narration": reason,
                        "currency": "NGN",
                        "debit_currency": "NGN",
                        "reference": reference,
                    },
                )
            data = resp.json()
        except Exception as exc:  # noqa: BLE001 — network/timeout → retry later
            raise PayoutError(f"Transfer request failed: {exc}") from exc

        return PayoutResult(
            ok=data.get("status") == "success",
            reference=reference,
            provider=self.name,
            message=data.get("message"),
            raw=data,
        )

    def transfer_exists(self, reference: str) -> bool:
        # Best-effort: scan recent transfers for a matching (non-failed) reference.
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(
                    f"{self._base()}/v3/transfers",
                    headers=self._headers(),
                    params={"page": 1},
                )
            data = resp.json()
            for t in data.get("data", []) or []:
                if t.get("reference") == reference and str(t.get("status", "")).upper() != "FAILED":
                    return True
        except Exception:  # noqa: BLE001
            return False
        return False
