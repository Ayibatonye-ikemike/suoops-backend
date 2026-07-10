"""Storefront order escrow — trust rules, hold windows, and seller payout setup.

This module holds the pure/decision logic + the seller Paystack Transfer
Recipient onboarding. It does NOT move money — the actual hold/release/refund
flow (payment webhook, auto-release worker, refunds) lands in later steps and
uses these helpers.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import secrets

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import models

logger = logging.getLogger(__name__)


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

    # Breadth, not just volume: trust requires many DISTINCT paying customers so
    # a seller can't self-deal (pay their own invoices) into trusted status.
    distinct_customers = (
        db.query(func.count(func.distinct(models.Invoice.customer_id)))
        .filter(
            models.Invoice.issuer_id == user.id,
            models.Invoice.invoice_type == "revenue",
            models.Invoice.status == "paid",
        )
        .scalar()
    ) or 0
    if distinct_customers < settings.ESCROW_TRUST_MIN_DISTINCT_CUSTOMERS:
        return False

    # A track record of actually-completed storefront deliveries (released holds).
    deliveries = (
        db.query(func.count(models.StorefrontOrderEscrow.id))
        .filter(
            models.StorefrontOrderEscrow.seller_id == user.id,
            models.StorefrontOrderEscrow.status == "released",
        )
        .scalar()
    ) or 0
    if deliveries < settings.ESCROW_TRUST_MIN_DELIVERIES:
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


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres between two lat/lng points."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def detect_order_collusion(
    seller: "models.User",
    *,
    buyer_ip: str | None,
    customer_lat: float | None,
    customer_lng: float | None,
) -> str | None:
    """Return a short reason string if a storefront order looks like the seller
    ordering from themselves (trust-farming / laundering), else None.

    Signals: buyer shares the seller's signup IP, or the buyer's GPS pin sits on
    top of the seller's own store location.
    """
    reasons: list[str] = []
    if buyer_ip and seller.signup_ip and buyer_ip == seller.signup_ip:
        reasons.append("shared IP")
    if (
        customer_lat is not None
        and customer_lng is not None
        and seller.storefront_lat is not None
        and seller.storefront_lng is not None
    ):
        try:
            if _haversine_m(customer_lat, customer_lng, seller.storefront_lat, seller.storefront_lng) < 75:
                reasons.append("buyer at seller location")
        except (ValueError, TypeError):
            pass
    return ", ".join(reasons) or None



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
    review_reason: str | None = None,
) -> "models.StorefrontOrderEscrow":
    """Create the PENDING escrow hold for a fresh storefront order.

    Captures the customer's GPS-derived state (server-side) and whether it
    matches the seller's state (drives the 12h vs 3-day window). Generates the
    buyer-only delivery code and flags the order for review if it looks like
    self-dealing. The hold is activated (status 'held', release_due_at set) when
    payment is confirmed.
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
        # 6-digit buyer-only delivery code (never shown to the seller).
        confirmation_code=f"{secrets.randbelow(900000) + 100000}",
        held_for_review=bool(review_reason),
        review_reason=review_reason,
    )
    db.add(escrow)
    db.commit()
    db.refresh(escrow)
    if review_reason:
        logger.warning(
            "Storefront order %s flagged for review (seller %s): %s",
            invoice.id, seller.id, review_reason,
        )
    return escrow


def activate_escrow_on_payment(
    db: Session, invoice: "models.Invoice", *, charge_reference: str | None = None
) -> None:
    """Activate a pending storefront-order hold once payment is confirmed.

    Flips ``pending -> held`` and sets ``release_due_at = paid_at + window`` (12h
    same-state, else 3 days; unknown state → the safer cross-state window).
    Captures the Paystack charge reference so the buyer can be refunded on a
    dispute. Idempotent — only acts on a pending row. No money moves here.
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
    if charge_reference:
        escrow.charge_reference = charge_reference
    db.commit()
    logger.info(
        "Escrow held for order invoice=%s (same_state=%s, release_due_at=%s)",
        invoice.id, escrow.same_state, escrow.release_due_at,
    )

    # Best-effort: send the buyer their delivery code so they can release the
    # payment on arrival. It's shown to the buyer at checkout too.
    try:
        customer = getattr(invoice, "customer", None)
        seller = db.query(models.User).filter(models.User.id == escrow.seller_id).first()
        send_delivery_code(
            getattr(customer, "phone", None),
            escrow.confirmation_code or "",
            getattr(seller, "business_name", None) if seller else None,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to dispatch delivery code for invoice %s", invoice.id)


# ── Release (pay the seller) ───────────────────────────────────────────

def release_escrow(db: Session, escrow: "models.StorefrontOrderEscrow", *, reason: str = "auto") -> bool:
    """Pay held funds out to the seller (gross − commission) via the configured
    payout provider.

    Transfers are ASYNCHRONOUS on both rails — a queued transfer is not yet
    disbursed — so this is an idempotent state machine, not a fire-and-forget:

    * If a transfer was already initiated (``transfer_reference`` set), reconcile
      its outcome FIRST and never re-send while it's in flight:
        - ``successful`` → mark released.
        - ``pending`` / ``unknown`` → leave 'held', return False (wait for a later
          run to confirm). ``unknown`` is treated as "wait" so a transport blip
          never triggers a double-payment.
        - ``failed`` → retry with a FRESH reference (the old one is burned).
    * A freshly queued transfer is only finalized once confirmed ``successful``;
      otherwise the row stays 'held' and the worker retries.

    Returns True once released (or already released). Returns False when a payout
    is in flight / not yet confirmed. Raises EscrowError on a genuine failure so
    the caller can retry later (the row stays 'held').
    """
    if escrow.status == "released":
        return True
    if escrow.status != "held":
        return False  # pending / disputed / refunded — not releasable

    # Collusion/anomaly-flagged orders never auto-pay — an admin must decide.
    if escrow.held_for_review:
        raise EscrowError(f"Escrow {escrow.id} held for review — not auto-releasable")

    if escrow.payout_kobo <= 0:
        # Nothing to pay out (shouldn't happen) — close it cleanly.
        escrow.status = "released"
        escrow.released_at = dt.datetime.now(dt.timezone.utc)
        db.commit()
        return True

    seller = db.query(models.User).filter(models.User.id == escrow.seller_id).first()
    if not seller:
        raise EscrowError(f"Seller {escrow.seller_id} not found for escrow {escrow.id}")

    # Payouts are frozen for a cooldown after a bank/payout change (anti-takeover).
    frozen = seller.payout_frozen_until
    if frozen is not None:
        if frozen.tzinfo is None:
            frozen = frozen.replace(tzinfo=dt.timezone.utc)
        if frozen > dt.datetime.now(dt.timezone.utc):
            raise EscrowError(
                f"Payouts frozen for seller {seller.id} until {frozen.isoformat()}"
            )

    from app.services.payouts import PayoutError, get_payout_provider

    provider = get_payout_provider()

    def _finalize(ref: str) -> bool:
        escrow.status = "released"
        escrow.released_at = dt.datetime.now(dt.timezone.utc)
        db.commit()
        logger.info(
            "Escrow %s released via %s — %s kobo to seller %s (ref=%s)",
            escrow.id, provider.name, escrow.payout_kobo, seller.id, ref,
        )
        return True

    # Reconcile an already-initiated transfer before sending anything new.
    if escrow.transfer_reference:
        prior = provider.transfer_status(escrow.transfer_reference)
        if prior == "successful":
            return _finalize(escrow.transfer_reference)
        if prior in ("pending", "unknown"):
            # In flight or indeterminate — do NOT re-send; a later run confirms.
            return False
        # prior == "failed" → the reference is burned; retry with a fresh one below.

    # First-ever attempt keeps the clean deterministic reference; a retry after a
    # confirmed-failed transfer gets a fresh (unburned) reference.
    if not escrow.transfer_reference:
        reference = f"ESCROWREL-{escrow.id}"
    else:
        reference = f"ESCROWREL-{escrow.id}-{int(dt.datetime.now(dt.timezone.utc).timestamp())}"

    payout_reason = f"Storefront order payout ({reason}) — invoice {escrow.invoice_id}"

    # Record intent before calling the provider so a crash mid-flight is recoverable.
    if escrow.transfer_reference != reference:
        escrow.transfer_reference = reference
        db.commit()

    try:
        result = provider.transfer(
            db,
            seller=seller,
            amount_kobo=int(escrow.payout_kobo),
            reference=reference,
            reason=payout_reason,
        )
    except PayoutError as exc:  # network/transport failure → retry later
        raise EscrowError(f"Transfer request failed: {exc}") from exc

    status = (result.status or "").lower()
    # Only finalize on confirmed disbursement. A confirmed-successful response (or
    # verify call) releases; an accepted/queued transfer stays 'held' until a
    # later run confirms it (avoids marking released before the money moves).
    if status == "successful" or provider.transfer_exists(reference):
        return _finalize(reference)
    if result.ok or status in ("pending", "queued", "new"):
        return False  # accepted/in-flight — confirm on the next run, do NOT re-send
    raise EscrowError(f"Transfer failed for escrow {escrow.id}: {result.message}")


# ── Refund (return money to the buyer) ─────────────────────────────────

def _collector_for_charge(db: Session, charge_reference: str) -> str:
    """Which provider collected this charge (recorded in the payment metadata).
    Refunds MUST go back through the collecting rail. Defaults to Paystack."""
    from app.models.payment_models import PaymentTransaction

    txn = (
        db.query(PaymentTransaction)
        .filter(PaymentTransaction.reference == charge_reference)
        .one_or_none()
    )
    if txn and txn.payment_metadata:
        return txn.payment_metadata.get("collector") or "paystack"
    return "paystack"


def refund_escrow(db: Session, escrow: "models.StorefrontOrderEscrow", *, reason: str = "dispute") -> bool:
    """Refund the buyer for a held/disputed order via the COLLECTING provider.

    A refund reverses the exact original charge, so it routes back through the
    provider that collected the order (Paystack or Flutterwave). The full gross
    amount is refunded (funds were held, never transferred to the seller).
    Idempotent: once ``refunded`` it is a no-op. Raises EscrowError on a genuine
    failure so the caller can retry (row stays in its current state).
    """
    if escrow.status == "refunded":
        return True
    if escrow.status == "released":
        raise EscrowError(f"Escrow {escrow.id} already paid out — cannot refund")

    if not escrow.charge_reference:
        raise EscrowError(f"Escrow {escrow.id} has no charge reference to refund")

    from app.services.collections import CollectionError, get_collection_provider_named

    collector = get_collection_provider_named(_collector_for_charge(db, escrow.charge_reference))

    try:
        data = collector.refund(
            reference=escrow.charge_reference,
            amount_kobo=int(escrow.gross_kobo),
            note=f"Storefront buyer protection ({reason}) — invoice {escrow.invoice_id}",
        )
    except CollectionError as exc:  # network/timeout / provider error → retry later
        raise EscrowError(str(exc)) from exc

    refund = data.get("data") or {}
    escrow.status = "refunded"
    escrow.refunded_at = dt.datetime.now(dt.timezone.utc)
    escrow.refund_reference = str(refund.get("id") or escrow.charge_reference)[:100]
    db.commit()
    logger.info(
        "Escrow %s refunded via %s — %s kobo returned to buyer (charge=%s)",
        escrow.id, collector.name, escrow.gross_kobo, escrow.charge_reference,
    )
    return True


# ── Payout security (account-takeover protection) ──────────────────────

def on_payout_details_changed(db: Session, user: "models.User") -> None:
    """Handle a change to a seller's payout/bank details defensively.

    A hijacked account's first move is to reroute payouts, so on any change we:
    invalidate the cached Paystack recipient (forces re-create from the new
    details), freeze escrow payouts for a cooldown, and alert the owner. This
    never blocks the (legitimate) update itself.
    """
    user.paystack_recipient_code = None
    user.payout_frozen_until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
        hours=settings.ESCROW_PAYOUT_FREEZE_HOURS_ON_BANK_CHANGE
    )
    db.commit()
    logger.info(
        "Payout details changed for user %s — payouts frozen until %s",
        user.id, user.payout_frozen_until,
    )

    # Best-effort owner alert on WhatsApp — never let a messaging hiccup break the flow.
    try:
        if user.phone:
            from app.bot.whatsapp_client import WhatsAppClient

            hours = settings.ESCROW_PAYOUT_FREEZE_HOURS_ON_BANK_CHANGE
            msg = (
                "🔒 SuoOps security alert\n\n"
                "Your payout bank details were just changed. For your safety, "
                f"storefront payouts are paused for {hours} hours.\n\n"
                "If this was NOT you, contact support@suoops.com immediately — "
                "your account may be compromised."
            )
            WhatsAppClient(settings.WHATSAPP_API_KEY).send_text(user.phone, msg)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send payout-change alert to user %s", user.id)


def send_delivery_code(user_phone: str | None, code: str, business_name: str | None) -> None:
    """Best-effort WhatsApp delivery of the buyer-only confirmation code."""
    if not (user_phone and code):
        return
    try:
        from app.bot.whatsapp_client import WhatsAppClient

        shop = business_name or "the store"
        msg = (
            f"🛡️ Your SuoOps delivery code for your order from {shop} is: {code}\n\n"
            "Give this code to the seller ONLY when your order arrives — it "
            "releases your payment. Your money is safely held until then."
        )
        WhatsAppClient(settings.WHATSAPP_API_KEY).send_text(user_phone, msg)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send delivery code to buyer")


# ── Buyer reputation (deter false "not delivered" claims) ──────────────

def _norm_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    try:
        from app.utils.phone import normalize_phone

        return normalize_phone(phone.strip())
    except Exception:  # noqa: BLE001
        return phone.strip()


def _buyer_rep_row(db: Session, phone: str) -> "models.BuyerReputation":
    rep = (
        db.query(models.BuyerReputation)
        .filter(models.BuyerReputation.phone == phone)
        .first()
    )
    if not rep:
        rep = models.BuyerReputation(phone=phone)
        db.add(rep)
    return rep


def record_buyer_dispute(db: Session, phone: str | None) -> None:
    """Count that this buyer filed a dispute (any report)."""
    p = _norm_phone(phone)
    if not p:
        return
    rep = _buyer_rep_row(db, p)
    rep.disputes = (rep.disputes or 0) + 1
    db.commit()


def record_buyer_false_dispute(db: Session, phone: str | None) -> None:
    """Count a dispute an admin ruled against the buyer (released to seller).

    Flags the buyer once they cross the abuse threshold.
    """
    p = _norm_phone(phone)
    if not p:
        return
    rep = _buyer_rep_row(db, p)
    rep.false_disputes = (rep.false_disputes or 0) + 1
    if rep.false_disputes >= settings.ESCROW_BUYER_ABUSE_FLAG_AT:
        rep.flagged = True
    db.commit()


def get_buyer_reputation(db: Session, phone: str | None) -> "models.BuyerReputation | None":
    p = _norm_phone(phone)
    if not p:
        return None
    return (
        db.query(models.BuyerReputation)
        .filter(models.BuyerReputation.phone == p)
        .first()
    )
