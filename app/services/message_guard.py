"""Leak-detection + redaction for order-scoped storefront messaging.

The storefront is deliberately on-platform (escrow + commission). Free-form
buyer/seller messages are the obvious way to leak the relationship off-platform
(share a phone / bank account, or push a direct transfer that bypasses escrow),
or to socially-engineer the buyer-only delivery code. This module masks the
concrete leak vectors, flags circumvention attempts, and blocks the most
unambiguous ones — before a message is ever delivered.

Pure functions only (no DB / IO) so they're cheap and heavily testable.
"""
from __future__ import annotations

import dataclasses
import re

MASK = "▓▓▓"

# Emails.
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Links + social handles (WhatsApp/Telegram/Instagram/@handles).
_LINK_RE = re.compile(
    r"(https?://\S+|www\.\S+|(?:wa\.me|t\.me|instagram\.com|facebook\.com)/\S+|@[A-Za-z0-9_]{3,})",
    re.IGNORECASE,
)
# A run of 10–14 digits (allowing spaces / dashes / dots / leading +) — phone
# numbers and 10-digit NUBAN account numbers.
_LONG_NUM_RE = re.compile(r"\+?\d(?:[\s.\-]?\d){9,13}")
# A standalone 6-digit number — could be the buyer-only delivery code.
_CODE_RE = re.compile(r"(?<!\d)\d{6}(?!\d)")

# Unambiguous "leave the platform" phrases → the message is blocked (not delivered).
_HARD_BLOCK_RES = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"pay\s+me\s+direct",
        r"pay\s+(me\s+)?outside",
        r"outside\s+(the\s+)?app",
        r"off[\s-]?platform",
        r"don'?t\s+pay\s+on\s+(the\s+)?app",
        r"outside\s+suoops",
    )
]
# Softer payment-nudge phrases → delivered, but flagged (feeds seller trust score).
_SOFT_NUDGE_RES = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"bank\s+transfer",
        r"account\s+number",
        r"send\s+(the\s+)?money",
        r"transfer\s+to",
        r"my\s+account",
        r"cash\s+on\s+delivery",
    )
]


@dataclasses.dataclass
class GuardResult:
    """Outcome of scanning one message."""

    redacted: str
    reasons: list[str]
    blocked: bool

    @property
    def flagged(self) -> bool:
        return bool(self.reasons) or self.blocked


def scan_message(text: str) -> GuardResult:
    """Mask leak vectors, flag circumvention, and block the clearest attempts.

    Masking order matters: emails/links first (they contain digits), then long
    numbers (phone/account), then standalone 6-digit codes.
    """
    reasons: list[str] = []
    redacted = text or ""

    def _mask(pattern: re.Pattern, reason: str) -> None:
        nonlocal redacted
        if pattern.search(redacted):
            reasons.append(reason)
            redacted = pattern.sub(MASK, redacted)

    _mask(_EMAIL_RE, "email")
    _mask(_LINK_RE, "link_or_handle")
    _mask(_LONG_NUM_RE, "contact_or_account")
    _mask(_CODE_RE, "possible_delivery_code")

    for rx in _SOFT_NUDGE_RES:
        if rx.search(redacted):
            reasons.append("payment_nudge")
            break

    blocked = any(rx.search(text or "") for rx in _HARD_BLOCK_RES)
    if blocked and "payment_circumvention" not in reasons:
        reasons.append("payment_circumvention")

    # De-dup while preserving order.
    seen: set[str] = set()
    reasons = [r for r in reasons if not (r in seen or seen.add(r))]
    return GuardResult(redacted=redacted, reasons=reasons, blocked=blocked)
