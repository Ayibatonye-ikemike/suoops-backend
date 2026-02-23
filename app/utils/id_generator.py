from __future__ import annotations

import uuid


def generate_id(prefix: str) -> str:
    """Generate a non-guessable public ID.

    Format: ``{PREFIX}-{uuid4}`` — e.g. ``INV-a1b2c3d4e5f64789abcdef0123456789``

    The UUID provides 122 bits of cryptographic randomness, making
    enumeration / brute-force infeasible.  The prefix is kept for
    human readability (INV = revenue, EXP = expense, PO = purchase order).

    The total length is ``len(prefix) + 1 + 32 = 36`` for a 3-char prefix,
    which fits within the existing ``String(40)`` column.
    """
    return f"{prefix}-{uuid.uuid4().hex}".upper()
