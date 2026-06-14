"""Subscription plan pricing constants.

Note: Pro is now PREPAID (one-time Pro Pack / Pro Features pass) — the recurring
subscription tier has been retired and the Paystack plan is archived/unused.
These constants are kept for legacy/display only.
"""

# Plan prices in Naira (display prices - what customers see)
PLAN_PRICES = {
    "FREE": 0,
    # STARTER removed - users are FREE and buy invoice packs as needed
    "PRO": 2000,       # Prepaid Pro Pack: ₦2,000 one-time (20 invoices + 30 days Pro features)
    "BUSINESS": 10000, # ₦10,000 - 50 invoices included + Photo OCR (15 max)
}

# Paystack Plan Codes (LEGACY — recurring subscriptions retired).
# Pro is now prepaid (one-time Pro Pack / Pro Features pass); this recurring
# plan is archived/unused and kept only so legacy subscribers don't break.
PAYSTACK_PLAN_CODES = {
    "PRO": "PLN_b9uq4itr2415bdf",  # archived recurring plan (unused)
    # "BUSINESS": "PLN_xxxxxxxx",  # Add when Business plan is enabled
}

# Invoice pack pricing (available to all tiers)
INVOICE_PACK_SIZE = 50
INVOICE_PACK_PRICE = 1250  # ₦1,250 per 50 invoices
