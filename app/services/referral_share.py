"""Helpers for sharing referral codes via WhatsApp / email."""
from __future__ import annotations

from app.core.config import settings


def build_referral_link(code: str) -> str:
    """Build the public signup URL with the referral code pre-filled."""
    base = (getattr(settings, "FRONTEND_URL", None) or "https://suoops.com").rstrip("/")
    return f"{base}/register?ref={code}"


def build_referral_whatsapp_message(name: str, code: str) -> str:
    """Friendly WhatsApp message a user receives showing their referral code.

    Sent shortly after signup so users have their code without hunting for it,
    and any time the user types ``referral`` / ``my code`` in the bot.
    """
    link = build_referral_link(code)
    first_name = (name or "there").split()[0]
    return (
        f"🎁 *Earn ₦488 per friend, {first_name}!*\n\n"
        f"Share SuoOps with other business owners. When a friend you invite "
        f"upgrades to *Pro*, you instantly earn *₦488* — paid out monthly in cash.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"*Your referral code:* `{code}`\n"
        f"*Your invite link:*\n{link}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💡 *How to share:*\n"
        f"1️⃣ Forward this message to a friend\n"
        f"2️⃣ Or copy the link above into any chat\n"
        f"3️⃣ Track your earnings anytime — type *referral*\n\n"
        f"_Tip: tap and hold the link or code to copy._"
    )
