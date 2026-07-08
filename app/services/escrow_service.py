"""Storefront order escrow — trust rules, hold windows, and seller payout setup.

This module holds the pure/decision logic + the seller Paystack Transfer
Recipient onboarding. It does NOT move money — the actual hold/release/refund
flow (payment webhook, auto-release worker, refunds) lands in later steps and
uses these helpers.
"""
from __future__ import annotations

import datetime as dt
import logging

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import models

logger = logging.getLogger(__name__)

_PAYSTACK_BASE = "https://api.paystack.co"

# Cached Paystack bank list (normalized name -> code); rarely changes.
_bank_cache: dict[str, str] = {}
_bank_cache_at: float = 0.0
_BANK_CACHE_TTL = 24 * 60 * 60  # 24h


class EscrowError(Exception):
    """Raised when an escrow payout/recipient operation can't be completed."""


# ── Trust rules ────────────────────────────────────────────────────────

def is_trusted_seller(db: Session, user: models.User) -> bool:
    """Whether a seller may skip the escrow hold (normal/instant settlement).

    ALL must hold: active store, not fraud-flagged, ZERO unresolved disputes,
    and the configured tenure + paid-invoice thresholds. Computed per order so
    trust is automatically revoked if a seller starts getting disputes.
    """
    if user.store_status != "active" or user.flagged_for_review:
        return False

    now = dt.datetime.now(dt.timezone.utc)
    created = user.created_at
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=dt.timezone.utc)
    if created is None or (now - created).days < settings.ESCROW_TRUST_MIN_ACCOUNT_AGE_DAYS:
        return False

    paid_invoices = (
        db.query(func.count(models.Invoice.id))
        .filter(
            models.Invoice.issuer_id == user.id,
            models.Invoice.invoice_type == "revenue",
            models.Invoice.status == "paid",
        )
        .scalar()
    ) or 0
    if paid_invoices < settings.ESCROW_TRUST_MIN_PAID_INVOICES:
        return False

    # Any disputed/refunded storefront order permanently blocks trust.
    disputes = (
        db.query(func.count(models.StorefrontOrderEscrow.id))
        .filter(
            models.StorefrontOrderEscrow.seller_id == user.id,
            models.StorefrontOrderEscrow.status.in_(["disputed", "refunded"]),
        )
        .scalar()
    ) or 0
    return disputes == 0


def hold_window(same_state: bool) -> dt.timedelta:
    """Dispute/hold window: 12h when buyer & seller share a state, else 3 days."""
    if same_state:
        return dt.timedelta(hours=settings.ESCROW_SAME_STATE_HOLD_HOURS)
    return dt.timedelta(days=settings.ESCROW_CROSS_STATE_HOLD_DAYS)


def _norm_state(value: str | None) -> str | None:
    """Normalize a state name for comparison (lowercase, strip a trailing
    'state', drop non-alphanumerics). e.g. 'Lagos State' == 'lagos'."""
    if not value:
        return None
    s = "".join(ch for ch in value.lower() if ch.isalnum() or ch == " ").strip()
    if s.endswith(" state"):
        s = s[: -len(" state")].strip()
    s = s.replace(" ", "")
    return s or None


def create_order_escrow(
    db: Session,
    *,
    invoice: "models.Invoice",
    seller: "models.User",
    gross_naira,
    customer_lat: float | None,
    customer_lng: float | None,
) -> "models.StorefrontOrderEscrow":
    """Create the PENDING escrow hold for a fresh storefront order.

    Captures the customer's GPS-derived state (server-side) and whether it
    matches the seller's state (drives the 12h vs 3-day window). The hold is
    activated (status 'held', release_due_at set) when payment is confirmed.
    """
    from decimal import Decimal

    from app.services.geocode_service import reverse_geocode
    from app.utils.feature_gate import platform_fee_kobo

    customer_state = None
    if customer_lat is not None and customer_lng is not None:
        customer_state, _city = reverse_geocode(customer_lat, customer_lng)

    business_state = seller.storefront_state
    bs, cs = _norm_state(business_state), _norm_state(customer_state)
    same_state: bool | None = (bs == cs) if (bs and cs) else None

    gross_kobo = int(Decimal(str(gross_naira)) * 100)
    fee_kobo = platform_fee_kobo(gross_naira)
    payout_kobo = max(0, gross_kobo - fee_kobo)

    escrow = models.StorefrontOrderEscrow(
        invoice_id=invoice.id,
        seller_id=seller.id,
        status="pending",  # -> 'held' on payment confirmation
        same_state=same_state,
        gross_kobo=gross_kobo,
        fee_kobo=fee_kobo,
        payout_kobo=payout_kobo,
        business_state=business_state,
        customer_state=customer_state,
        customer_lat=customer_lat,
        customer_lng=customer_lng,
    )
    db.add(escrow)
    db.commit()
    db.refresh(escrow)
    return escrow


def activate_escrow_on_payment(db: Session, invoice: "models.Invoice") -> None:
    """Activate a pending storefront-order hold once payment is confirmed.

    Flips ``pending -> held`` and sets ``release_due_at = paid_at + window`` (12h
    same-state, else 3 days; unknown state → the safer cross-state window).
    Idempotent — only acts on a pending row. No money moves here.
    """
    escrow = (
        db.query(models.StorefrontOrderEscrow)
        .filter(
            models.StorefrontOrderEscrow.invoice_id == invoice.id,
            models.StorefrontOrderEscrow.status == "pending",
        )
        .first()
    )
    if not escrow:
        return

    paid_at = getattr(invoice, "paid_at", None) or dt.datetime.now(dt.timezone.utc)
    if paid_at.tzinfo is None:
        paid_at = paid_at.replace(tzinfo=dt.timezone.utc)

    # Unknown same/different state → treat as cross-state (longer, safer window).
    same = bool(escrow.same_state) if escrow.same_state is not None else False
    escrow.status = "held"
    escrow.release_due_at = paid_at + hold_window(same)
    db.commit()
    logger.info(
        "Escrow held for order invoice=%s (same_state=%s, release_due_at=%s)",
        invoice.id, escrow.same_state, escrow.release_due_at,
    )


# ── Seller payout setup (Paystack Transfer Recipient) ──────────────────

def _headers() -> dict[str, str]:
    if not settings.PAYSTACK_SECRET:
        raise EscrowError("PAYSTACK_SECRET is not configured")
    return {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET}",
        "Content-Type": "application/json",
    }


def _normalize_bank_name(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _resolve_bank_code(bank_name: str) -> str:
    global _bank_cache, _bank_cache_at
    import time

    now = time.time()
    if not _bank_cache or (now - _bank_cache_at) > _BANK_CACHE_TTL:
        with httpx.Client(timeout=20) as client:
            resp = client.get(
                f"{_PAYSTACK_BASE}/bank",
                headers=_headers(),
                params={"currency": "NGN", "perPage": 100},
            )
        data = resp.json()
        if not data.get("status"):
            raise EscrowError(f"Could not load bank list: {data.get('message')}")
        _bank_cache = {
            _normalize_bank_name(b["name"]): b["code"] for b in data.get("data", [])
        }
        _bank_cache_at = now

    code = _bank_cache.get(_normalize_bank_name(bank_name))
    if not code:
        raise EscrowError(f"Unknown bank: {bank_name!r}")
    return code


def ensure_transfer_recipient(db: Session, user: models.User) -> str:
    """Return the seller's Paystack Transfer Recipient code, creating it once.

    Uses the seller's payout bank details (falls back to their business bank).
    Cached on ``user.paystack_recipient_code`` and reused for every payout.
    """
    if user.paystack_recipient_code:
        return user.paystack_recipient_code

    account_number = user.payout_account_number or user.account_number
    bank_name = user.payout_bank_name or user.bank_name
    account_name = (
        user.payout_account_name or user.account_name or user.business_name or user.name
    )
    if not (account_number and bank_name):
        raise EscrowError("Seller has no bank details set for payouts")

    bank_code = _resolve_bank_code(bank_name)

    with httpx.Client(timeout=20) as client:
        resp = client.post(
            f"{_PAYSTACK_BASE}/transferrecipient",
            headers=_headers(),
            json={
                "type": "nuban",
                "name": account_name,
                "account_number": account_number,
                "bank_code": bank_code,
                "currency": "NGN",
            },
        )
    data = resp.json()
    if not data.get("status"):
        raise EscrowError(f"Could not create transfer recipient: {data.get('message')}")

    code = (data.get("data") or {}).get("recipient_code")
    if not code:
        raise EscrowError("Paystack did not return a recipient code")

    user.paystack_recipient_code = code
    db.commit()
    logger.info("Created Paystack transfer recipient for seller %s", user.id)
    return code


# ── Release (pay the seller) ───────────────────────────────────────────

def _transfer_exists(reference: str) -> bool:
    """Whether a Paystack transfer with this reference already exists."""
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{_PAYSTACK_BASE}/transfer/verify/{reference}", headers=_headers()
            )
        return bool(resp.json().get("status"))
    except Exception:  # noqa: BLE001
        return False


def release_escrow(db: Session, escrow: "models.StorefrontOrderEscrow", *, reason: str = "auto") -> bool:
    """Pay held funds out to the seller (gross − commission) via a Paystack
    Transfer. Idempotent (deterministic reference; Paystack rejects duplicates).

    Returns True if released (or already released). Raises EscrowError on a
    genuine failure so the caller can retry later (the row stays 'held').
    """
    if escrow.status == "released":
        return True
    if escrow.status != "held":
        return False  # pending / disputed / refunded — not releasable

    if escrow.payout_kobo <= 0:
        # Nothing to pay out (shouldn't happen) — close it cleanly.
        escrow.status = "released"
        escrow.released_at = dt.datetime.now(dt.timezone.utc)
        db.commit()
        return True

    seller = db.query(models.User).filter(models.User.id == escrow.seller_id).first()
    if not seller:
        raise EscrowError(f"Seller {escrow.seller_id} not found for escrow {escrow.id}")

    recipient = ensure_transfer_recipient(db, seller)
    reference = f"ESCROWREL-{escrow.id}"

    # Record intent before calling Paystack so a crash mid-flight is recoverable.
    if escrow.transfer_reference != reference:
        escrow.transfer_reference = reference
        db.commit()

    try:
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                f"{_PAYSTACK_BASE}/transfer",
                headers=_headers(),
                json={
                    "source": "balance",
                    "amount": int(escrow.payout_kobo),
                    "recipient": recipient,
                    "reason": f"Storefront order payout ({reason}) — invoice {escrow.invoice_id}",
                    "reference": reference,
                },
            )
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 — network/timeout → retry later
        raise EscrowError(f"Transfer request failed: {exc}") from exc

    if data.get("status") or _transfer_exists(reference):
        escrow.status = "released"
        escrow.released_at = dt.datetime.now(dt.timezone.utc)
        db.commit()
        logger.info(
            "Escrow %s released — transferred %s kobo to seller %s (ref=%s)",
            escrow.id, escrow.payout_kobo, seller.id, reference,
        )
        return True

    raise EscrowError(f"Transfer failed for escrow {escrow.id}: {data.get('message')}")
