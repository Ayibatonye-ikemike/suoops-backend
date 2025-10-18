from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def format_naira(amount: Decimal) -> str:
    q = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"₦{q:,}"
