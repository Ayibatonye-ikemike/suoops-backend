"""Subscription management and Paystack payment integration.

Refactored from monolithic routes_subscription.py for SRP compliance.

Sub-modules:
- constants: Plan pricing
- initialize: Initialize payment endpoint
- verify: Verify payment endpoint
- history: Payment history endpoints
"""
from fastapi import APIRouter

from .initialize import router as initialize_router
from .verify import router as verify_router
from .history import router as history_router
from .constants import PLAN_PRICES

# Create main router and include sub-routers
router = APIRouter()
router.include_router(initialize_router)
router.include_router(verify_router)
router.include_router(history_router)

__all__ = ["router", "PLAN_PRICES"]
