"""Aggregate tax router combining split modules for main app inclusion."""
from fastapi import APIRouter

from app.api import routes_tax_profile, routes_tax_vat, routes_tax_reports, routes_tax_misc

router = APIRouter()

# Each sub-router already has prefix /tax; just include them
router.include_router(routes_tax_profile.router)
router.include_router(routes_tax_vat.router)
router.include_router(routes_tax_reports.router)
router.include_router(routes_tax_misc.router)

__all__ = ["router"]
