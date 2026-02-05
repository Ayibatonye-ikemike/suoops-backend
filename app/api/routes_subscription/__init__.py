"""Subscription management and Paystack payment integration.

Refactored from monolithic routes_subscription.py for SRP compliance.

Sub-modules:
- constants: Plan pricing and Paystack plan codes
- initialize: Initialize payment endpoint (now uses Paystack subscriptions for recurring billing)
- verify: Verify payment endpoint
- history: Payment history endpoints
- cancel: Cancel subscription endpoint
"""
from fastapi import APIRouter

from .constants import PLAN_PRICES, PAYSTACK_PLAN_CODES
from .history import router as history_router
from .initialize import router as initialize_router
from .verify import router as verify_router
from .cancel import router as cancel_router

# Create main router and include sub-routers
router = APIRouter()
router.include_router(initialize_router)
router.include_router(verify_router)
router.include_router(history_router)
router.include_router(cancel_router)

__all__ = ["router", "PLAN_PRICES", "PAYSTACK_PLAN_CODES"]
