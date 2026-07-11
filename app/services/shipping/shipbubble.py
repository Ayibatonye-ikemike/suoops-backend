"""Shipbubble courier integration (feature-flagged, OFF by default).

Shipbubble is a Nigerian shipping-API aggregator: you fund a Naira wallet and,
when a shipment is booked, the courier fee is drawn from that wallet. The API
itself is free — you pay per shipment. In SuoOps the BUYER pays delivery at
checkout, so SuoOps carries no shipping cost.

Flow (per Shipbubble docs):
  1. validate_address()  → POST /shipping/address/validate  → address_code
  2. fetch_rates()       → POST /shipping/fetch_rates       → request_token + couriers[]
  3. create_shipment()   → POST /shipping/labels            → order_id + tracking_url

Everything here is best-effort and fail-soft: if the flag is off, the key is
missing, or the API errors, callers get ``None``/``[]`` and the manual dispatch
flow continues unaffected. Nothing activates until ``SHIPBUBBLE_ENABLED`` is set
and an API key + funded wallet exist.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def enabled() -> bool:
    """True only when the integration is switched on AND a key is configured."""
    return bool(settings.SHIPBUBBLE_ENABLED and settings.SHIPBUBBLE_API_KEY)


@dataclasses.dataclass
class DeliveryOption:
    """One courier rate, normalized for the checkout UI."""

    courier_id: str
    service_code: str
    name: str
    image: str | None
    amount: float  # what to charge the buyer (rate_card_amount)
    wallet_total: float  # what Shipbubble deducts from the wallet (total)
    currency: str
    delivery_eta: str | None
    delivery_eta_time: str | None
    service_type: str | None

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.SHIPBUBBLE_BASE_URL,
        headers={
            "Authorization": f"Bearer {settings.SHIPBUBBLE_API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=20,
    )


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """POST helper — returns the ``data`` object on success, else None. Never raises."""
    if not enabled():
        return None
    try:
        with _client() as client:
            resp = client.post(path, json=payload)
        body = resp.json()
    except Exception as exc:  # noqa: BLE001 — shipping must never break the request
        logger.warning("Shipbubble %s failed: %s", path, exc)
        return None
    if isinstance(body, dict) and body.get("status") == "success":
        return body.get("data") or {}
    logger.warning("Shipbubble %s non-success: %s", path, (body or {}).get("message"))
    return None


def validate_address(
    *,
    name: str,
    email: str,
    phone: str,
    address: str,
    latitude: float | None = None,
    longitude: float | None = None,
) -> int | None:
    """Validate an address and return its Shipbubble ``address_code`` (or None)."""
    payload: dict[str, Any] = {
        "name": name,
        "email": email,
        "phone": phone,
        "address": address,
    }
    if latitude is not None and longitude is not None:
        payload["latitude"] = latitude
        payload["longitude"] = longitude
    data = _post("/shipping/address/validate", payload)
    return int(data["address_code"]) if data and data.get("address_code") else None


def fetch_rates(
    *,
    sender_address_code: int,
    receiver_address_code: int,
    package_items: list[dict[str, Any]],
    package_dimension: dict[str, float] | None = None,
    category_id: int | None = None,
    pickup_date: str | None = None,
) -> dict[str, Any] | None:
    """Fetch courier rates. Returns ``{"request_token": str, "options": [DeliveryOption…]}``
    or None. The ``request_token`` is required to later create the shipment."""
    payload: dict[str, Any] = {
        "sender_address_code": sender_address_code,
        # NB: Shipbubble spells the field "reciever_address_code".
        "reciever_address_code": receiver_address_code,
        "pickup_date": pickup_date or dt.date.today().isoformat(),
        "category_id": category_id or settings.SHIPBUBBLE_DEFAULT_CATEGORY_ID,
        "package_items": package_items,
        "package_dimension": package_dimension or {"length": 20, "width": 20, "height": 10},
    }
    data = _post("/shipping/fetch_rates", payload)
    if not data:
        return None
    options = [_to_option(c) for c in data.get("couriers", [])]
    return {
        "request_token": data.get("request_token"),
        "options": [o for o in options if o is not None],
    }


def create_shipment(
    *, request_token: str, courier_id: str, service_code: str
) -> dict[str, Any] | None:
    """Book the chosen courier. Returns ``{"order_id", "tracking_url", "courier",
    "delivery_eta"}`` or None. The shipping fee is drawn from the Shipbubble wallet."""
    data = _post(
        "/shipping/labels",
        {
            "request_token": request_token,
            "service_code": service_code,
            "courier_id": courier_id,
        },
    )
    if not data:
        return None
    return {
        "order_id": data.get("order_id"),
        "tracking_url": data.get("tracking_url"),
        "courier": (data.get("courier") or {}).get("name"),
        "status": data.get("status"),
    }


def _to_option(c: dict[str, Any]) -> DeliveryOption | None:
    try:
        return DeliveryOption(
            courier_id=str(c["courier_id"]),
            service_code=str(c["service_code"]),
            name=str(c.get("courier_name") or "Courier"),
            image=c.get("courier_image"),
            amount=float(c.get("rate_card_amount") or c.get("total") or 0),
            wallet_total=float(c.get("total") or 0),
            currency=str(c.get("currency") or "NGN"),
            delivery_eta=c.get("delivery_eta"),
            delivery_eta_time=c.get("delivery_eta_time"),
            service_type=c.get("service_type"),
        )
    except Exception:  # noqa: BLE001 — skip a malformed courier entry
        return None
