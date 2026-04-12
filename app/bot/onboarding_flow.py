"""Guided first-invoice onboarding flow for new WhatsApp users.

After signup, the bot proactively walks the user through creating their
first invoice step by step:

  Step 1: Ask customer name
  Step 2: Ask amount and item description
  Step 3: Ask customer phone (optional)
  Step 4: Create the invoice

Uses the same ephemeral in-memory state pattern as PendingPriceSession
and CartSession. Sessions expire after 30 minutes of inactivity.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_ONBOARDING_TTL = 1800  # 30 minutes


@dataclass
class OnboardingSession:
    """Tracks a user's progress through the guided first-invoice flow."""

    user_id: int
    step: str = "customer_name"  # customer_name → amount → phone → done
    customer_name: str = ""
    amount: float = 0
    description: str = ""
    customer_phone: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.updated_at) > _ONBOARDING_TTL

    def touch(self) -> None:
        self.updated_at = time.time()


# In-memory store: phone → OnboardingSession
_sessions: dict[str, OnboardingSession] = {}


def get_onboarding_session(phone: str) -> OnboardingSession | None:
    """Get active onboarding session, or None if expired/missing."""
    session = _sessions.get(phone)
    if session and session.is_expired:
        del _sessions[phone]
        return None
    return session


def start_onboarding(phone: str, user_id: int) -> OnboardingSession:
    """Start a new onboarding session for a user."""
    session = OnboardingSession(user_id=user_id)
    _sessions[phone] = session
    return session


def clear_onboarding(phone: str) -> None:
    """Remove onboarding session."""
    _sessions.pop(phone, None)


def send_onboarding_prompt(client, phone: str, name: str) -> None:
    """Send the initial onboarding message that starts the guided flow."""
    msg = (
        f"🎉 Welcome to SuoOps, {name}!\n\n"
        "Let's create your *first invoice* together — "
        "it only takes 30 seconds.\n\n"
        "👤 *What's your customer's name?*\n\n"
        "_Type their name (e.g. Joy, Ade, Mrs Bello)_\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 Type *skip* to explore on your own"
    )
    client.send_text(phone, msg)


def handle_onboarding_reply(
    session: OnboardingSession,
    client,
    phone: str,
    text: str,
) -> dict[str, Any] | None:
    """Process user reply in the onboarding flow.

    Returns invoice data dict when all steps are complete, None otherwise.
    The caller is responsible for actually creating the invoice.
    """
    text = text.strip()
    text_lower = text.lower()

    # Allow user to skip/cancel at any point
    if text_lower in {"skip", "cancel", "stop", "no", "later", "not now"}:
        clear_onboarding(phone)
        client.send_text(
            phone,
            "👍 No problem! You can create an invoice anytime by typing:\n\n"
            "`Invoice Joy 08012345678, 5000 wig`\n\n"
            "Type *help* for the full guide."
        )
        return None

    session.touch()

    if session.step == "customer_name":
        return _handle_customer_name(session, client, phone, text)
    elif session.step == "amount":
        return _handle_amount(session, client, phone, text)
    elif session.step == "phone":
        return _handle_phone(session, client, phone, text)

    return None


def _handle_customer_name(
    session: OnboardingSession,
    client,
    phone: str,
    text: str,
) -> dict[str, Any] | None:
    """Step 1: Capture customer name."""
    # Basic validation — name should be at least 2 chars
    name = text.strip()
    if len(name) < 2:
        client.send_text(
            phone,
            "Please enter a valid customer name (at least 2 characters).\n\n"
            "👤 *What's your customer's name?*"
        )
        return None

    # Don't accept numbers-only as names
    if name.replace(" ", "").isdigit():
        client.send_text(
            phone,
            "That looks like a number, not a name 😊\n\n"
            "👤 *What's your customer's name?*\n"
            "_e.g. Joy, Ade, Mrs Bello_"
        )
        return None

    session.customer_name = name
    session.step = "amount"

    client.send_text(
        phone,
        f"✅ Customer: *{name}*\n\n"
        "💰 *How much and what is it for?*\n\n"
        "_Type the amount and item, e.g:_\n"
        "• `5000 wig`\n"
        "• `15000 website design`\n"
        "• `50000`"
    )
    return None


def _handle_amount(
    session: OnboardingSession,
    client,
    phone: str,
    text: str,
) -> dict[str, Any] | None:
    """Step 2: Capture amount and optional description."""
    import re

    # Try to extract amount from text like "5000 wig" or "15,000 website design" or just "5000"
    text = text.strip()
    amount_match = re.match(
        r"^[\₦N]?\s*([\d,]+(?:\.\d{1,2})?)\s*(.*)?$",
        text,
        re.IGNORECASE,
    )

    if not amount_match:
        client.send_text(
            phone,
            "I couldn't find an amount in that.\n\n"
            "💰 *Please type the amount and what it's for:*\n"
            "_e.g. `5000 wig` or `15000 website design`_"
        )
        return None

    amount_str = amount_match.group(1).replace(",", "")
    try:
        amount = float(amount_str)
    except ValueError:
        client.send_text(
            phone,
            "That doesn't look like a valid amount.\n\n"
            "💰 *Try again:* _e.g. `5000 wig` or `15000`_"
        )
        return None

    if amount < 100:
        client.send_text(
            phone,
            "⚠️ Amount seems too low. Minimum is ₦100.\n\n"
            "💰 *Try again:* _e.g. `5000 wig`_"
        )
        return None

    description = (amount_match.group(2) or "").strip()
    session.amount = amount
    session.description = description or "Service"
    session.step = "phone"

    desc_text = f" for *{session.description}*" if description else ""

    client.send_text(
        phone,
        f"✅ Amount: *₦{amount:,.0f}*{desc_text}\n\n"
        "📱 *What's your customer's phone number?*\n\n"
        "_Type their number so they get the invoice on WhatsApp._\n"
        "_Or type *skip* to create without a phone number._"
    )
    return None


def _handle_phone(
    session: OnboardingSession,
    client,
    phone: str,
    text: str,
) -> dict[str, Any] | None:
    """Step 3: Capture customer phone (optional) and complete."""
    import re

    text_lower = text.lower().strip()

    customer_phone = ""
    if text_lower not in {"skip", "no", "none", "no phone", "n/a", "-"}:
        # Try to extract a phone number
        digits = re.sub(r"[^\d+]", "", text)
        if len(digits) >= 10:
            customer_phone = digits
        else:
            client.send_text(
                phone,
                "That doesn't look like a valid phone number.\n\n"
                "📱 *Enter a phone number* (e.g. 08012345678)\n"
                "_or type *skip* to continue without one_"
            )
            return None

    session.customer_phone = customer_phone

    # Build invoice data in the format _create_invoice expects
    lines = [
        {
            "description": session.description,
            "quantity": 1,
            "unit_price": session.amount,
        }
    ]

    invoice_data: dict[str, Any] = {
        "customer_name": session.customer_name,
        "customer_phone": customer_phone,
        "amount": session.amount,
        "lines": lines,
        "currency": "NGN",
    }

    # Clean up the session
    clear_onboarding(phone)

    return invoice_data
