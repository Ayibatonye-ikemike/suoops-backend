"""Buyer-pays-delivery money math: the delivery fee is added to the amount
charged but excluded from the seller's escrow gross/payout."""
from decimal import Decimal
from unittest.mock import AsyncMock

from app.core.config import settings
from app.models import models
from app.models.inventory_models import Product
from app.services.shipping.shipbubble import DeliveryOption


def _seed_store(db):
    owner = models.User(
        phone="+2348160000010",
        name="Store",
        business_name="Store Biz",
        bank_name="Opay",
        account_number="0123456789",
        account_name="STORE",
        paystack_subaccount_active=True,
        paystack_subaccount_code="ACCT_x",
        storefront_enabled=True,
        store_status="active",
        storefront_slug="teststore",
        storefront_state="Lagos",
        storefront_city="Ikeja",
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)
    prod = Product(
        user_id=owner.id,
        sku="CAKE-1",
        name="Cake",
        description="Yummy cake",
        image_url="http://img/x.jpg",
        selling_price=Decimal("10000"),
        is_active=True,
        track_stock=False,
    )
    db.add(prod)
    db.commit()
    db.refresh(prod)
    return owner, prod


def test_delivery_fee_added_and_excluded_from_payout(db_session, client, monkeypatch):
    owner, prod = _seed_store(db_session)
    monkeypatch.setattr(settings, "SHIPBUBBLE_CHECKOUT_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ESCROW_ENABLED", True, raising=False)

    opt = DeliveryOption(
        courier_id="gig",
        service_code="gig",
        name="GIG",
        image=None,
        amount=1500.0,
        wallet_total=1500.0,
        currency="NGN",
        delivery_eta="1-2 days",
        delivery_eta_time=None,
        service_type="pickup",
    )
    import app.api.routes_storefront as rs

    monkeypatch.setattr(
        rs, "_shipbubble_quote", lambda db, owner, payload: {"request_token": "tok", "options": [opt]}
    )
    monkeypatch.setattr("app.services.escrow_service.is_trusted_seller", lambda db, u: False)
    monkeypatch.setattr(
        "app.services.escrow_service.detect_order_collusion", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "app.services.escrow_service.seller_velocity_hold_reason", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "app.services.invoice_payment_service.start_invoice_payment",
        AsyncMock(return_value={"authorization_url": "http://pay"}),
    )

    resp = client.post(
        "/public/store/teststore/order",
        json={
            "customer_name": "Buyer",
            "customer_phone": "+2348161111111",
            "items": [{"product_id": prod.id, "quantity": 1}],
            "delivery_courier_id": "gig",
            "delivery_service_code": "gig",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["delivery_fee"] == 1500.0

    inv = (
        db_session.query(models.Invoice)
        .filter_by(invoice_id=body["invoice_id"])
        .one()
    )
    assert inv.amount == Decimal("11500")  # goods 10,000 + delivery 1,500

    escrow = (
        db_session.query(models.StorefrontOrderEscrow)
        .filter_by(invoice_id=inv.id)
        .one()
    )
    assert escrow.gross_kobo == 1_000_000  # goods only — delivery excluded
    assert escrow.delivery_fee_kobo == 150_000
    assert escrow.delivery_courier == "GIG"
    assert escrow.delivery_request_token == "tok"
