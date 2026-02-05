"""Subscription plan pricing constants."""

# Plan SUBSCRIPTION prices in Naira (monthly fees)
# Note: STARTER has no subscription - users buy invoice packs (50 = ₦1,250)
PLAN_PRICES = {
    "FREE": 0,
    "STARTER": 0,      # No monthly fee - pay-per-invoice (₦1,250/50 invoices) + Tax features
    "PRO": 3250,       # ₦3,250/month - 50 invoices included + Custom logo branding
    "BUSINESS": 10000, # ₦10,000/month - 50 invoices included + Photo OCR (15 max)
}

# Paystack Plan Codes for auto-recurring subscriptions
# Create plans at: https://dashboard.paystack.com/plans
PAYSTACK_PLAN_CODES = {
    "PRO": "PLN_b9uq4itr2415bdf",  # ₦3,250/month
    # "BUSINESS": "PLN_xxxxxxxx",  # Add when Business plan is enabled
}

# Invoice pack pricing (available to all tiers)
INVOICE_PACK_SIZE = 50
INVOICE_PACK_PRICE = 1250  # ₦1,250 per 50 invoices
