"""Server-side reverse geocoding (lat/lng -> Nigerian state/city) via Mapbox.

Used to derive a TRUSTED state from GPS coordinates for the escrow same/different
-state window — the client sends coordinates, the server decides the state, so a
client can't fake "same state" to shorten the hold.
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_MAPBOX_GEOCODE = "https://api.mapbox.com/geocoding/v5/mapbox.places"


def reverse_geocode(lat: float, lng: float) -> tuple[str | None, str | None]:
    """Return ``(state, city)`` for a coordinate, or ``(None, None)`` if it can't
    be resolved (e.g. no token configured). Never raises."""
    token = settings.MAPBOX_TOKEN
    if not token:
        logger.info("MAPBOX_TOKEN not set — skipping reverse geocode")
        return (None, None)
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{_MAPBOX_GEOCODE}/{lng},{lat}.json",
                params={
                    "access_token": token,
                    "country": "NG",
                    "types": "region,place",
                    "limit": 5,
                },
            )
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 — geocoding must never break the request
        logger.warning("Reverse geocode failed: %s", exc)
        return (None, None)

    state: str | None = None
    city: str | None = None
    for feat in data.get("features", []):
        place_types = feat.get("place_type", [])
        if "region" in place_types and not state:
            state = (feat.get("text") or "").strip() or None
        elif "place" in place_types and not city:
            city = (feat.get("text") or "").strip() or None
    return (state, city)
