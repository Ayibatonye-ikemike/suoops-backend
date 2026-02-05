"""Subscription plan pricing constants."""

# Plan SUBSCRIPTION prices in Naira (display prices - what customers see)
# Note: Paystack plan has fees included, shown at checkout
# STARTER has no subscription - users buy invoice packs (50 = ₦1,250)
PLAN_PRICES = {
    "FREE": 0,
    "STARTER": 0,      # No monthly fee - pay-per-invoice (₦1,250/50 invoices) + Tax features
    "PRO": 3250,       # ₦3,250/month displayed, Paystack charges ₦3,402 (includes fees)
    "BUSINESS": 10000, # ₦10,000/month - 50 invoices included + Photo OCR (15 max)
}

# Paystack Plan Codes for auto-recurring subscriptions
# Plans set in Paystack dashboard with fees included
PAYSTACK_PLAN_CODES = {
    "PRO": "PLN_b9uq4itr2415bdf",  # ₦3,402/month in Paystack (₦3,250 + fees)
    # "BUSINESS": "PLN_xxxxxxxx",  # Add when Business plan is enabled
}

# Paystack plan amounts in Naira (actual charge amount with fees)
# Must match what's set in Paystack dashboard
PAYSTACK_PLAN_AMOUNTS = {
    "PRO": 3402,  # ₦3,402 (₦3,250 base + Paystack fees)
}

# Invoice pack pricing (available to all tiers)
INVOICE_PACK_SIZE = 50
INVOICE_PACK_PRICE = 1250  # ₦1,250 per 50 invoices
