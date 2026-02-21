"""Support FAQ, onboarding activation, and escalation handler for WhatsApp bot.

Answers common support questions, walks new users through account setup,
and escalates to support.suoops.com when the bot can't resolve the issue.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.bot.whatsapp_client import WhatsAppClient
from app.models import models

logger = logging.getLogger(__name__)

# ── FAQ knowledge base ────────────────────────────────────────────────
# Each entry: list of trigger patterns → response builder
# Patterns are checked with substring / keyword matching (case-insensitive)
_FAQ_ENTRIES: list[dict[str, Any]] = [
    # ── Account & Registration ──
    {
        "patterns": [
            "how to register", "how do i register", "how to sign up",
            "how do i sign up", "create account", "create an account",
            "open account", "sign up", "signup", "register",
        ],
        "answer": (
            "📝 *How to Register*\n\n"
            "1️⃣ Go to suoops.com\n"
            "2️⃣ Tap *Get Started Free*\n"
            "3️⃣ Enter your email and create a password\n"
            "4️⃣ Verify your email via the link we send\n\n"
            "✅ That's it — you're ready to start invoicing!"
        ),
    },
    {
        "patterns": [
            "how to verify", "verify my number", "verify whatsapp",
            "verify phone", "link whatsapp", "connect whatsapp",
            "link my number", "add my number", "otp",
        ],
        "answer": (
            "📱 *How to Verify Your WhatsApp Number*\n\n"
            "1️⃣ Log in at suoops.com/dashboard\n"
            "2️⃣ Go to *Settings*\n"
            "3️⃣ Enter your WhatsApp number\n"
            "4️⃣ Tap *Send OTP* — you'll get a code here\n"
            "5️⃣ Enter the code to verify\n\n"
            "✅ Once verified, you can create invoices by texting this bot!"
        ),
    },
    # ── Invoicing ──
    {
        "patterns": [
            "how to create invoice", "how to send invoice",
            "how to make invoice", "how do i invoice",
            "how to use", "how does this work", "how it works",
        ],
        "answer": (
            "📄 *How to Create an Invoice*\n\n"
            "*Via WhatsApp (fastest):*\n"
            "Just type:\n"
            "`Invoice Joy 08012345678, 5000 wig`\n\n"
            "*Via Dashboard:*\n"
            "Go to suoops.com/dashboard → *Create Invoice*\n\n"
            "Your customer gets a WhatsApp notification with payment link + PDF!\n\n"
            "Type *help* for the full formatting guide."
        ),
    },
    {
        "patterns": [
            "invoice not sent", "customer didn't receive",
            "customer no receive", "invoice not delivered",
            "customer didn't get", "not receiving",
        ],
        "answer": (
            "⚠️ *Invoice Not Delivered?*\n\n"
            "Common causes:\n"
            "• Customer's number may be wrong — double-check it\n"
            "• Number must include country code (e.g. 08012345678)\n"
            "• Customer needs WhatsApp on that number\n\n"
            "💡 *Quick fix:* Share the payment link directly!\n"
            "Find it in your dashboard under the invoice.\n\n"
            "Still stuck? Visit support.suoops.com/contact"
        ),
    },
    # ── Payments ──
    {
        "patterns": [
            "how to get paid", "how do i get paid", "receive payment",
            "how to receive money", "payment method", "bank details",
            "add bank", "bank account", "set up bank", "setup bank",
        ],
        "answer": (
            "💳 *How to Get Paid*\n\n"
            "1️⃣ Log in at suoops.com/dashboard\n"
            "2️⃣ Go to *Settings* → *Bank Details*\n"
            "3️⃣ Add your bank name, account number & account name\n\n"
            "Once set, your bank details appear on every invoice automatically!\n\n"
            "Customers can pay via:\n"
            "• Bank transfer (details on invoice)\n"
            "• Online payment link"
        ),
    },
    {
        "patterns": [
            "customer paid but", "payment not showing",
            "paid but not confirmed", "payment not reflected",
            "mark as paid", "confirm payment",
        ],
        "answer": (
            "💰 *Payment Not Showing?*\n\n"
            "1️⃣ Ask customer to reply *paid* to this bot\n"
            "2️⃣ Or manually mark it paid in your dashboard:\n"
            "   → suoops.com/dashboard → find the invoice → *Mark Paid*\n\n"
            "📝 Bank transfers can take a few minutes to reflect.\n\n"
            "If the issue persists, contact us at support.suoops.com/contact"
        ),
    },
    # ── Plans & Pricing ──
    {
        "patterns": [
            "pricing", "how much", "price", "plans", "subscription",
            "upgrade", "pro plan", "starter plan", "free plan",
            "what plan", "my plan",
        ],
        "answer": (
            "💰 *SuoOps Plans*\n\n"
            "🆓 *Free* — 5 invoices to try it out\n\n"
            "⭐ *Starter* — No monthly fee!\n"
            "   Buy packs: ₦2,500 for 100 invoices\n"
            "   Includes: Tax reports, analytics\n\n"
            "👑 *Pro* — ₦5,000/month\n"
            "   100 invoices/month included\n"
            "   + Product catalog, voice invoicing, all features\n\n"
            "Manage your plan at suoops.com/dashboard/subscription"
        ),
    },
    # ── Expenses ──
    {
        "patterns": [
            "how to track expense", "how to add expense",
            "record expense", "log expense", "expense tracking",
            "how to expense",
        ],
        "answer": (
            "💸 *How to Track Expenses*\n\n"
            "*Via WhatsApp:*\n"
            "Just type:\n"
            "• `Expense: ₦5,000 for transport`\n"
            "• `Spent 3000 naira on data`\n"
            "• Send a photo of your receipt 📸\n\n"
            "*Via Dashboard:*\n"
            "Go to suoops.com/dashboard → *Expenses*\n\n"
            "Expenses are used in your tax reports automatically!"
        ),
    },
    # ── Tax ──
    {
        "patterns": [
            "how to get tax report", "tax report how",
            "what is tax report", "tax help", "nta",
        ],
        "answer": (
            "🏛️ *Tax Reports*\n\n"
            "Type *tax report* here to get your monthly tax summary + PDF.\n\n"
            "Or visit suoops.com/dashboard/tax for full details.\n\n"
            "📋 Includes: Income tax, VAT, dev levy — all auto-calculated!\n\n"
            "⚠️ Requires Starter plan or above."
        ),
    },
    # ── Account Issues ──
    {
        "patterns": [
            "can't login", "cannot login", "can't log in", "cannot log in",
            "forgot password", "reset password", "password reset",
            "locked out", "account locked",
        ],
        "answer": (
            "🔐 *Login Issues*\n\n"
            "1️⃣ Go to suoops.com/login\n"
            "2️⃣ Tap *Forgot Password*\n"
            "3️⃣ Enter your email → we'll send a reset link\n\n"
            "Still can't get in? Contact us at support.suoops.com/contact"
        ),
    },
    {
        "patterns": [
            "delete account", "delete my account", "remove account",
            "close account", "deactivate",
        ],
        "answer": (
            "🗑️ *Account Deletion*\n\n"
            "To delete your account and all data:\n"
            "1️⃣ Go to suoops.com/dashboard/settings\n"
            "2️⃣ Scroll to *Delete Account*\n"
            "3️⃣ Click *Contact Support*\n\n"
            "Or email support@suoops.com with your request.\n"
            "We'll process it within 72 hours."
        ),
    },
    # ── General ──
    {
        "patterns": [
            "what is suoops", "what's suoops", "what does suoops do",
            "tell me about suoops", "about suoops",
        ],
        "answer": (
            "🇳🇬 *What is SuoOps?*\n\n"
            "SuoOps is the easiest way for Nigerian businesses to:\n\n"
            "📄 Create professional invoices in seconds\n"
            "💬 Send them via WhatsApp — customers pay fast\n"
            "💳 Accept bank transfers with auto-confirmation\n"
            "📊 Track revenue, expenses & tax reports\n\n"
            "Start free at suoops.com!"
        ),
    },
]

# ── Onboarding steps ─────────────────────────────────────────────────
# Checks run in order; the first incomplete step is surfaced to the user.

def _check_onboarding_status(db: Session, user: models.User) -> list[dict[str, Any]]:
    """Return list of onboarding steps with completion status."""
    steps: list[dict[str, Any]] = []

    # 1. Email verified
    email_verified = bool(getattr(user, "email_verified", False) or getattr(user, "is_verified", False))
    steps.append({
        "label": "Verify your email",
        "done": email_verified,
        "help": "Check your inbox for the verification link from SuoOps.",
    })

    # 2. Phone verified (WhatsApp linked)
    phone_linked = bool(user.phone and getattr(user, "phone_verified", False))
    steps.append({
        "label": "Link your WhatsApp number",
        "done": phone_linked,
        "help": (
            "Go to suoops.com/dashboard/settings → enter your WhatsApp number "
            "→ tap *Send OTP* → enter the code."
        ),
    })

    # 3. Bank details added
    has_bank = bool(user.bank_name and user.account_number)
    steps.append({
        "label": "Add your bank details",
        "done": has_bank,
        "help": (
            "Go to suoops.com/dashboard/settings → *Bank Details* "
            "→ enter your bank, account number and name."
        ),
    })

    # 4. First invoice created
    from app.models.models import Invoice
    has_invoice = db.query(Invoice.id).filter(Invoice.issuer_id == user.id).first() is not None
    steps.append({
        "label": "Create your first invoice",
        "done": has_invoice,
        "help": (
            "Type here:\n"
            "`Invoice Joy 08012345678, 5000 wig`\n\n"
            "Or go to suoops.com/dashboard → *Create Invoice*."
        ),
    })

    return steps


class SupportHandler:
    """Handles support questions, onboarding guidance, and escalation."""

    SUPPORT_KEYWORDS = {
        "support", "contact", "talk to human", "speak to someone",
        "escalate", "complaint", "complain", "issue", "problem",
        "bug", "error", "broken", "not working", "doesn't work",
    }

    ONBOARDING_KEYWORDS = {
        "setup", "set up", "get started", "getting started",
        "onboard", "onboarding", "activate", "activation",
        "what next", "what do i do", "next step", "next steps",
        "how to start", "first time",
    }

    def __init__(self, db: Session, client: WhatsAppClient):
        self.db = db
        self.client = client

    def try_handle(self, sender: str, text: str) -> bool:
        """Try to handle the message as a support/FAQ/onboarding question.

        Returns True if handled (a response was sent), False otherwise.
        """
        text_lower = text.lower().strip()

        # 1. Direct escalation request
        if self._is_escalation_request(text_lower):
            self._send_escalation(sender)
            return True

        # 2. Onboarding / activation request
        if self._is_onboarding_request(text_lower):
            return self._handle_onboarding(sender)

        # 3. FAQ match
        answer = self._match_faq(text_lower)
        if answer:
            # Append soft escalation footer to every FAQ answer
            full_response = answer + "\n\n━━━━━━━━━━━━━━━━━━━━━\n💬 Still need help? Visit support.suoops.com"
            self.client.send_text(sender, full_response)
            return True

        return False

    # ── Private helpers ───────────────────────────────────────────

    def _is_escalation_request(self, text: str) -> bool:
        """Check if user is explicitly asking for human support."""
        # Exact keyword matches
        for kw in self.SUPPORT_KEYWORDS:
            if kw in text:
                return True
        return False

    def _is_onboarding_request(self, text: str) -> bool:
        """Check if user is asking about getting started / activation."""
        for kw in self.ONBOARDING_KEYWORDS:
            if kw in text:
                return True
        return False

    def _match_faq(self, text: str) -> str | None:
        """Find a matching FAQ entry for the user's question.

        Returns the answer text or None if no match.
        """
        best_match: str | None = None
        best_score = 0

        for entry in _FAQ_ENTRIES:
            for pattern in entry["patterns"]:
                # Exact substring match
                if pattern in text:
                    score = len(pattern)  # Longer matches win
                    if score > best_score:
                        best_score = score
                        best_match = entry["answer"]

        return best_match

    def _handle_onboarding(self, sender: str) -> bool:
        """Walk user through account setup checklist."""
        # Resolve user
        user = self._resolve_user(sender)
        if not user:
            # Unregistered — guide them to sign up
            self.client.send_text(
                sender,
                "🚀 *Get Started with SuoOps*\n\n"
                "Let's get you set up in 3 easy steps:\n\n"
                "1️⃣ *Register* → suoops.com (it's free!)\n"
                "2️⃣ *Verify WhatsApp* → Settings → Send OTP\n"
                "3️⃣ *Add bank details* → Settings → Bank Details\n\n"
                "Then just text me:\n"
                "`Invoice Joy 08012345678, 5000 wig`\n\n"
                "...and your first invoice goes out instantly! 🎉\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "💬 Need help? Visit support.suoops.com"
            )
            return True

        # Registered — show personalised checklist
        steps = _check_onboarding_status(self.db, user)
        all_done = all(s["done"] for s in steps)

        if all_done:
            self.client.send_text(
                sender,
                "✅ *You're all set!*\n\n"
                "Your account is fully activated. Here's what you can do:\n\n"
                "📝 Create invoice: `Invoice Joy 08012345678, 5000 wig`\n"
                "💸 Track expense: `Expense: ₦5,000 for transport`\n"
                "📊 Business report: Type *report*\n"
                "🏛️ Tax report: Type *tax report*\n\n"
                "Type *help* for the full guide."
            )
            return True

        # Build checklist message
        msg = "🚀 *Your Setup Progress*\n\n"
        first_incomplete = None

        for i, step in enumerate(steps, 1):
            icon = "✅" if step["done"] else "⬜"
            msg += f"{icon} {i}. {step['label']}\n"
            if not step["done"] and first_incomplete is None:
                first_incomplete = step

        msg += "\n━━━━━━━━━━━━━━━━━━━━━\n"

        if first_incomplete:
            msg += (
                f"👉 *Next step: {first_incomplete['label']}*\n\n"
                f"{first_incomplete['help']}\n"
            )

        msg += "\n━━━━━━━━━━━━━━━━━━━━━\n💬 Stuck? Visit support.suoops.com for help"

        self.client.send_text(sender, msg)
        return True

    def _send_escalation(self, sender: str) -> None:
        """Send escalation message with all support channels."""
        self.client.send_text(
            sender,
            "🤝 *We're Here to Help*\n\n"
            "Here's how to reach our team:\n\n"
            "1️⃣ 📚 *Help Center* (instant answers)\n"
            "   → support.suoops.com\n\n"
            "2️⃣ ✉️ *Email Support* (within 24hrs)\n"
            "   → support@suoops.com\n\n"
            "3️⃣ 🚨 *Urgent / Payment Issues*\n"
            "   → support.suoops.com/contact\n\n"
            "Please include:\n"
            "• Your registered email\n"
            "• Description of the issue\n"
            "• Any invoice numbers involved\n\n"
            "We'll get back to you as fast as possible! 💪"
        )

    def _resolve_user(self, phone: str) -> models.User | None:
        """Look up a registered user by phone number."""
        clean = phone.strip().replace(" ", "").replace("-", "")
        candidates: set[str] = {clean}
        digits = re.sub(r"[^\d]", "", clean)
        if digits:
            candidates.add(digits)
            if digits.startswith("234"):
                candidates.add(f"+{digits}")
                candidates.add("0" + digits[3:])
            elif digits.startswith("0"):
                candidates.add("234" + digits[1:])
                candidates.add("+234" + digits[1:])
            else:
                candidates.add(f"+{digits}")

        return (
            self.db.query(models.User)
            .filter(models.User.phone.in_(list(candidates)))
            .first()
        )
