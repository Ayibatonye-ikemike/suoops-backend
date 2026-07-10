"""Admin dispute payout-status endpoint + derived payout_state tests."""
from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.main import app
from app.api.routes_admin_auth import get_current_admin
from app.db.session import get_db
from app.models import models
from app.models.admin_models import AdminUser


def _admin(db):
    admin = AdminUser(
        email="dispute-admin@suoops.com",
        name="Dispute Admin",
        hashed_password="unusable",
        is_active=True,
        is_super_admin=True,
        can_manage_tickets=True,
        can_view_users=True,
        can_view_analytics=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def _order(db, *, status="held", transfer_reference=None):
    seller = models.User(name="Payout Seller", phone="+2349555000111")
    db.add(seller)
    db.commit()
    db.refresh(seller)
    customer = models.Customer(name="Payout Buyer", phone="+2348123450000")
    db.add(customer)
    db.commit()
    db.refresh(customer)
    inv = models.Invoice(
        invoice_id=f"INV-PAYOUT-{status}-{transfer_reference or 'x'}",
        issuer_id=seller.id,
        customer_id=customer.id,
        amount=Decimal("3000"),
        status="paid",
        invoice_type="revenue",
        channel="storefront",
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    esc = models.StorefrontOrderEscrow(
        invoice_id=inv.id,
        seller_id=seller.id,
        status=status,
        gross_kobo=300000,
        fee_kobo=9000,
        payout_kobo=291000,
        transfer_reference=transfer_reference,
    )
    db.add(esc)
    db.commit()
    db.refresh(esc)
    return esc


def test_payout_status_none_when_no_transfer():
    client = TestClient(app)
    db = next(get_db())
    admin = _admin(db)
    esc = _order(db, status="held", transfer_reference=None)
    app.dependency_overrides[get_current_admin] = lambda: admin
    try:
        r = client.get(f"/admin/disputes/{esc.id}/payout-status")
        assert r.status_code == 200, r.text
        assert r.json()["state"] == "none"
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        db.close()


def test_payout_status_paid_when_released():
    client = TestClient(app)
    db = next(get_db())
    admin = _admin(db)
    esc = _order(db, status="released", transfer_reference="ESCROWREL-9")
    app.dependency_overrides[get_current_admin] = lambda: admin
    try:
        r = client.get(f"/admin/disputes/{esc.id}/payout-status")
        assert r.status_code == 200, r.text
        assert r.json()["state"] == "paid"
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        db.close()


def test_payout_status_live_poll_normalizes_successful(monkeypatch):
    client = TestClient(app)
    db = next(get_db())
    admin = _admin(db)
    esc = _order(db, status="held", transfer_reference="ESCROWREL-42")

    import app.services.payouts as payouts

    class _Prov:
        name = "flutterwave"

        def transfer_status(self, reference):
            return "successful"

    monkeypatch.setattr(payouts, "get_payout_provider", lambda: _Prov())
    app.dependency_overrides[get_current_admin] = lambda: admin
    try:
        r = client.get(f"/admin/disputes/{esc.id}/payout-status")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["state"] == "paid"  # 'successful' normalized to 'paid'
        assert body["reference"] == "ESCROWREL-42"
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        db.close()
