"""Escrow trust + window unit tests (step 3)."""
import datetime as dt

from app.services import escrow_service as es


def test_hold_window_same_vs_cross_state():
    assert es.hold_window(True) == dt.timedelta(hours=12)
    assert es.hold_window(False) == dt.timedelta(days=3)


def test_release_escrow_status_guards():
    """release_escrow short-circuits (no Paystack) for non-releasable states."""
    from types import SimpleNamespace

    from app.db.session import SessionLocal

    s = SessionLocal()
    try:
        assert es.release_escrow(s, SimpleNamespace(status="released")) is True
        assert es.release_escrow(s, SimpleNamespace(status="pending")) is False
        assert es.release_escrow(s, SimpleNamespace(status="disputed")) is False
        assert es.release_escrow(s, SimpleNamespace(status="refunded")) is False
    finally:
        s.close()


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


def test_activate_escrow_sets_held_and_window():
    """On payment, a pending same-state hold becomes 'held' with a 12h window."""
    from decimal import Decimal

    from app.db.session import SessionLocal
    from app.models import models

    s = SessionLocal()
    try:
        seller = models.User(name="Seller", phone="+2349990008080", storefront_state="Lagos")
        s.add(seller)
        s.commit()
        s.refresh(seller)

        customer = models.Customer(name="Buyer")
        s.add(customer)
        s.commit()
        s.refresh(customer)

        paid_at = dt.datetime(2026, 7, 8, 10, 0, tzinfo=dt.timezone.utc)
        inv = models.Invoice(
            invoice_id="EXP-ESCROWTEST-1",
            issuer_id=seller.id,
            customer_id=customer.id,
            amount=Decimal("5000"),
            status="paid",
            paid_at=paid_at,
            invoice_type="revenue",
            channel="storefront",
        )
        s.add(inv)
        s.commit()
        s.refresh(inv)

        esc = models.StorefrontOrderEscrow(
            invoice_id=inv.id,
            seller_id=seller.id,
            status="pending",
            same_state=True,
            gross_kobo=500000,
            fee_kobo=15000,
            payout_kobo=485000,
        )
        s.add(esc)
        s.commit()
        s.refresh(esc)

        try:
            es.activate_escrow_on_payment(s, inv)
            s.refresh(esc)
            assert esc.status == "held"
            expected = paid_at + dt.timedelta(hours=12)
            # Test DB (SQLite) strips tzinfo — compare naive to naive.
            assert esc.release_due_at.replace(tzinfo=None) == expected.replace(tzinfo=None)
        finally:
            s.delete(esc)
            s.delete(inv)
            s.delete(customer)
            s.delete(seller)
            s.commit()
    finally:
        s.close()
