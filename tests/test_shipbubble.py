"""Shipbubble courier integration — disabled-path (default) tests.

The integration ships OFF (no key). These lock in the fail-soft behaviour so the
manual dispatch flow is never affected until a key + wallet are configured.
"""
from app.services.shipping import shipbubble


def test_disabled_by_default():
    assert shipbubble.enabled() is False


def test_calls_return_none_when_disabled():
    assert shipbubble.validate_address(
        name="A", email="a@b.com", phone="080", address="Lagos"
    ) is None
    assert (
        shipbubble.fetch_rates(
            sender_address_code=1, receiver_address_code=2, package_items=[]
        )
        is None
    )
    assert (
        shipbubble.create_shipment(
            request_token="x", courier_id="c", service_code="s"
        )
        is None
    )


def test_to_option_normalizes_courier():
    opt = shipbubble._to_option(
        {
            "courier_id": "gig",
            "service_code": "gig",
            "courier_name": "GIG Logistics",
            "courier_image": "http://img",
            "rate_card_amount": 2500,
            "total": 2500,
            "currency": "NGN",
            "delivery_eta": "Within 1 - 2 working days",
            "service_type": "pickup",
        }
    )
    assert opt is not None
    assert opt.name == "GIG Logistics"
    assert opt.amount == 2500
    assert opt.currency == "NGN"
