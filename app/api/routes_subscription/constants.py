"""Subscription plan pricing constants."""

# Plan SUBSCRIPTION prices in Naira (monthly fees)
# Note: STARTER has no subscription - users buy invoice packs (100 = ₦2,500)
PLAN_PRICES = {
    "FREE": 0,
    "STARTER": 0,      # No monthly fee - pay-per-invoice (₦2,500/100 invoices) + Tax features
    "PRO": 5000,       # ₦5,000/month - 100 invoices included + Custom logo branding
    "BUSINESS": 10000, # ₦10,000/month - 100 invoices included + Photo OCR (15 max)
}

# Invoice pack pricing (available to all tiers)
INVOICE_PACK_SIZE = 100
INVOICE_PACK_PRICE = 2500  # ₦2,500 per 100 invoices
