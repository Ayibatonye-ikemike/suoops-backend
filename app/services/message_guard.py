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
# Spelled-out phone/account numbers ("zero eight zero three …", "oh eight oh…") —
# a common way to dodge the digit filter. A run of 6+ number-words in a row is
# almost never innocent prose, so we treat it as a shared contact number.
_NUM_WORDS = (
    r"zero|one|two|three|four|five|six|seven|eight|nine|ten|oh|nought|niner|double"
)
_SPELLED_NUM_RE = re.compile(
    rf"(?:\b(?:{_NUM_WORDS})\b[\s,.\-]*){{6,}}",
    re.IGNORECASE,
)
# Off-platform contact channels — naming a chat app or asking to be contacted
# directly is a circumvention signal inside an on-platform order thread.
_PLATFORM_RE = re.compile(
    r"(whats\s?app|telegram|snapchat|\bviber\b|\bimo\b|"
    r"dm\s+me|message\s+me\s+on|reach\s+me\s+(on|at)|add\s+me\s+on|"
    r"call\s+me\s+(on|at)|text\s+me\s+(on|at)|my\s+(number|line|digits|contact))",
    re.IGNORECASE,
)
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
    _mask(_SPELLED_NUM_RE, "spelled_contact")
    _mask(_CODE_RE, "possible_delivery_code")
    _mask(_PLATFORM_RE, "off_platform_contact")

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


# Individual number-words + runs, for cross-message accumulation: a phone number
# spelled out and split across several short messages ("six seven eight" … "nine
# ten" … "zero zero") slips past the single-message filter, so the caller sums
# the number-words a sender used across their recent messages.
_NUM_WORD_RE = re.compile(rf"\b(?:{_NUM_WORDS})\b", re.IGNORECASE)
_NUM_WORD_RUN_RE = re.compile(rf"(?:\b(?:{_NUM_WORDS})\b[\s,.\-]*)+", re.IGNORECASE)


def count_number_words(text: str) -> int:
    """How many spelled-out number-words a message contains (zero, one, oh…)."""
    return len(_NUM_WORD_RE.findall(text or ""))


def mask_number_words(text: str) -> str:
    """Mask runs of spelled-out number-words — used once a thread's accumulated
    spelled digits look like a shared phone number."""
    return _NUM_WORD_RUN_RE.sub(MASK, text or "")
