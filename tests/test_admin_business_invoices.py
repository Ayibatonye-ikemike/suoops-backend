"""Admin business-invoices drill-down + storefront owner-trace fields."""
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
        email="bizinv-admin@suoops.com",
        name="Biz Admin",
        hashed_password="unusable",
        is_active=True,
        is_super_admin=True,
        can_view_users=True,
        can_view_analytics=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def _seller_with_invoices(db):
    seller = models.User(
        name="Store Owner",
        phone="+2349555111222",
        business_name="Owner Biz",
        storefront_slug="owner-biz",
        email="owner@example.com",
    )
    db.add(seller)
    db.commit()
    db.refresh(seller)
    cust = models.Customer(name="A Buyer", phone="+2348123999000")
    db.add(cust)
    db.commit()
    db.refresh(cust)
    # 2 paid + 1 pending revenue invoice, plus an expense (excluded by default).
    specs = [
        ("INV-BI-1", "paid", "revenue", "5000"),
        ("INV-BI-2", "paid", "revenue", "3000"),
        ("INV-BI-3", "pending", "revenue", "2000"),
        ("INV-BI-EXP", "paid", "expense", "1000"),
    ]
    for iid, status, itype, amt in specs:
        db.add(
            models.Invoice(
                invoice_id=iid,
                issuer_id=seller.id,
                customer_id=cust.id,
                amount=Decimal(amt),
                status=status,
                invoice_type=itype,
                channel="storefront",
            )
        )
    db.commit()
    return seller


def test_business_invoices_lists_amounts_and_rollups():
    client = TestClient(app)
    db = next(get_db())
    admin = _admin(db)
    seller = _seller_with_invoices(db)
    app.dependency_overrides[get_current_admin] = lambda: admin
    try:
        r = client.get(f"/admin/businesses/{seller.id}/invoices")
        assert r.status_code == 200, r.text
        body = r.json()
        # Revenue-only by default → 3 invoices, expense excluded.
        assert body["total"] == 3
        assert len(body["invoices"]) == 3
        assert body["total_amount"] == 10000.0  # 5000+3000+2000
        assert body["paid_amount"] == 8000.0
        assert body["pending_amount"] == 2000.0
        # Newest first + customer name resolved + amounts present.
        first = body["invoices"][0]
        assert first["customer_name"] == "A Buyer"
        assert first["amount"] > 0
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        db.close()


def test_business_invoices_all_includes_expenses():
    client = TestClient(app)
    db = next(get_db())
    admin = _admin(db)
    seller = _seller_with_invoices(db)
    app.dependency_overrides[get_current_admin] = lambda: admin
    try:
        r = client.get(f"/admin/businesses/{seller.id}/invoices?invoice_type=all")
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 4  # includes the expense row
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        db.close()


def test_business_invoices_404_for_unknown_user():
    client = TestClient(app)
    db = next(get_db())
    admin = _admin(db)
    app.dependency_overrides[get_current_admin] = lambda: admin
    try:
        r = client.get("/admin/businesses/99999999/invoices")
        assert r.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        db.close()


def test_storefronts_expose_owner_contact():
    client = TestClient(app)
    db = next(get_db())
    admin = _admin(db)
    seller = _seller_with_invoices(db)  # has a storefront_slug
    app.dependency_overrides[get_current_admin] = lambda: admin
    try:
        r = client.get("/admin/storefronts?search=owner-biz")
        assert r.status_code == 200, r.text
        stores = r.json()["storefronts"]
        mine = [s for s in stores if s["id"] == seller.id]
        assert mine, "store not returned"
        s = mine[0]
        assert s["owner_phone"] == "+2349555111222"
        assert s["owner_email"] == "owner@example.com"
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        db.close()
