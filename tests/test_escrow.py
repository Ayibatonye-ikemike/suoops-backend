"""Escrow trust + window unit tests (step 3)."""
import datetime as dt

from app.services import escrow_service as es


def test_hold_window_same_vs_cross_state():
    assert es.hold_window(True) == dt.timedelta(hours=12)
    assert es.hold_window(False) == dt.timedelta(days=3)


def test_fresh_seller_is_not_trusted():
    """A brand-new seller (young account, no paid invoices) must NOT be trusted,
    so their storefront orders are always held."""
    from app.db.session import SessionLocal
    from app.models import models

    s = SessionLocal()
    try:
        u = models.User(name="Fresh Seller", phone="+2349990009090")
        s.add(u)
        s.commit()
        s.refresh(u)
        try:
            assert es.is_trusted_seller(s, u) is False
        finally:
            s.delete(u)
            s.commit()
    finally:
        s.close()
