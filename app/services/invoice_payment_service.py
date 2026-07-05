"""
Shared invoice online-payment service.

Single source of truth for starting a Paystack payment for an invoice through
the issuer's subaccount. Reused by the public pay endpoint, the storefront
checkout, and the WhatsApp bot so there is no duplicated payment logic.
"""
from __future__ import annotations

import logging
import uuid

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.payment_models import (
    PaymentProvider,
    PaymentStatus,
    PaymentTransaction,
)

logger = logging.getLogger(__name__)


class PaymentInitError(Exception):
    """Raised when an invoice payment cannot be initialized."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def start_invoice_payment(db: Session, invoice, issuer) -> dict:
    """
    Initialize a Paystack payment for ``invoice`` via ``issuer``'s subaccount.

    Returns ``{authorization_url, reference, amount}``. Raises PaymentInitError
    with a user-safe message + HTTP status on any failure.
    """
    if invoice.status in {"paid", "cancelled"}:
        raise PaymentInitError(f"Invoice is already {invoice.status}", 400)

    if not (
        getattr(issuer, "paystack_subaccount_active", False)
        and getattr(issuer, "paystack_subaccount_code", None)
    ):
        raise PaymentInitError("This business has not enabled online payments yet.", 409)

    amount = invoice.amount
    if amount is None or amount <= 0:
        raise PaymentInitError("Invoice has no payable amount", 400)

    if not settings.PAYSTACK_SECRET:
        raise PaymentInitError("Online payments are not configured", 503)

    # Platform commission: 3% clamped to [₦20, ₦2,000]. Sent to Paystack as a
    # flat transaction_charge so it overrides the subaccount's percentage split
    # and stays capped; never exceed the transaction amount.
    from app.utils.feature_gate import platform_fee_kobo

    commission_kobo = min(platform_fee_kobo(amount), int(amount * 100))

    customer = getattr(invoice, "customer", None)
    customer_email = (
        (customer.email if customer and customer.email else None)
        or (f"{customer.phone}@suoops.com" if customer and customer.phone else None)
        or f"invoice-{invoice.invoice_id}@suoops.com"
    )

    reference = f"INVPAY-{invoice.invoice_id}-{uuid.uuid4().hex[:8].upper()}"

    transaction = PaymentTransaction(
        user_id=issuer.id,
        reference=reference,
        amount=int(amount * 100),  # kobo
        currency=getattr(invoice, "currency", "NGN") or "NGN",
        provider=PaymentProvider.PAYSTACK,
        status=PaymentStatus.PENDING,
        customer_email=customer_email,
        customer_phone=customer.phone if customer else None,
        payment_metadata={
            "payment_type": "invoice_payment",
            "invoice_id": invoice.invoice_id,
            "issuer_id": issuer.id,
        },
    )
    db.add(transaction)
    db.commit()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.paystack.co/transaction/initialize",
                headers={
                    "Authorization": f"Bearer {settings.PAYSTACK_SECRET}",
                    "Content-Type": "application/json",
                },
                json={
                    "email": customer_email,
                    "amount": int(amount * 100),
                    "reference": reference,
                    "subaccount": issuer.paystack_subaccount_code,
                    "bearer": "subaccount",  # business absorbs the Paystack fee
                    "transaction_charge": commission_kobo,  # platform 3%, capped ₦20–₦2,000
                    "callback_url": f"{settings.FRONTEND_URL}/pay/{invoice.invoice_id}?ref={reference}",
                    "metadata": {
                        "payment_type": "invoice_payment",
                        "invoice_id": invoice.invoice_id,
                        "issuer_id": issuer.id,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        transaction.status = PaymentStatus.FAILED
        db.commit()
        logger.error("Paystack invoice-pay init error (ref=%s): %s", reference, exc)
        raise PaymentInitError("Payment gateway error. Please try again.", 502) from exc

    if not data.get("status"):
        transaction.status = PaymentStatus.FAILED
        db.commit()
        raise PaymentInitError(data.get("message", "Payment initialization failed"), 502)

    return {
        "authorization_url": data["data"]["authorization_url"],
        "reference": reference,
        "amount": float(amount),
    }
