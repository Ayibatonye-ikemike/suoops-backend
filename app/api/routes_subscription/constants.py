"""Subscription plan pricing constants."""

# Plan SUBSCRIPTION prices in Naira (display prices - what customers see)
# Note: Paystack plan (PLN_xxx) has the actual charge amount with fees
# When using a plan code, Paystack ignores the 'amount' param and uses the plan's amount
PLAN_PRICES = {
    "FREE": 0,
    "STARTER": 0,      # No monthly fee - pay-per-invoice (₦1,250/50 invoices) + Tax features
    "PRO": 3250,       # Display: ₦3,250/month. Paystack plan charges ₦3,402 (includes fees)
    "BUSINESS": 10000, # ₦10,000/month - 50 invoices included + Photo OCR (15 max)
}

# Paystack Plan Codes for auto-recurring subscriptions
# The plan in Paystack dashboard has the actual amount (₦3,402 for PRO)
# Customer sees ₦3,250 on our site, pays ₦3,402 at Paystack checkout
PAYSTACK_PLAN_CODES = {
    "PRO": "PLN_b9uq4itr2415bdf",  # Plan amount: ₦3,402 (₦3,250 + fees)
    # "BUSINESS": "PLN_xxxxxxxx",  # Add when Business plan is enabled
}

# Invoice pack pricing (available to all tiers)
INVOICE_PACK_SIZE = 50
INVOICE_PACK_PRICE = 1250  # ₦1,250 per 50 invoices
