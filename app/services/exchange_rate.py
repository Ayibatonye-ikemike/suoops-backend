"""Real-time NGN/USD exchange rate with caching.

Fetches the current rate from multiple free public APIs (with fallback chain)
and caches it for 15 minutes.  Falls back to the NGN_USD_RATE env var, then
to a hardcoded default, so the dashboard never breaks even if every API is down.
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal, InvalidOperation

import httpx

logger = logging.getLogger(__name__)

# ── In-memory cache ──────────────────────────────────────────────────
_cached_rate: Decimal | None = None
_cached_at: float = 0.0
_CACHE_TTL_SECONDS = 900  # 15 minutes — keeps the rate fresher

# ── API endpoints (tried in order) ───────────────────────────────────
_APIS: list[dict[str, str]] = [
    {
        # ExchangeRate-API v4 — free, no key, ~daily updates
        "url": "https://api.exchangerate-api.com/v4/latest/USD",
        "path": "rates.NGN",
        "name": "exchangerate-api.com",
    },
    {
        # Open Exchange Rates (free tier) — the previous default
        "url": "https://open.er-api.com/v6/latest/USD",
        "path": "rates.NGN",
        "name": "open.er-api.com",
    },
]


def _extract_nested(data: dict, dotted_path: str):
    """Drill into *data* using a dotted key path like ``rates.NGN``."""
    for key in dotted_path.split("."):
        data = data[key]
    return data


def _fetch_live_rate() -> Decimal | None:
    """Try each API in order and return the first successful NGN rate."""
    for api in _APIS:
        try:
            resp = httpx.get(api["url"], timeout=5)
            resp.raise_for_status()
            raw = _extract_nested(resp.json(), api["path"])
            if raw is not None:
                rate = Decimal(str(raw))
                logger.info("Fetched live NGN/USD rate %s from %s", rate, api["name"])
                return rate
        except (httpx.HTTPError, KeyError, ValueError, InvalidOperation, TypeError) as exc:
            logger.warning("Exchange rate fetch from %s failed: %s", api["name"], exc)
    return None


def _get_env_fallback() -> Decimal:
    """Read the operator-configured fallback from the env var."""
    from app.core.config import settings

    if settings.NGN_USD_RATE:
        try:
            return Decimal(settings.NGN_USD_RATE)
        except (InvalidOperation, ValueError):
            logger.warning(
                "Invalid NGN_USD_RATE env value '%s', using hardcoded fallback",
                settings.NGN_USD_RATE,
            )
    return Decimal("1600")


def get_ngn_usd_rate() -> Decimal:
    """Return the current NGN per 1 USD rate (e.g. 1580).

    Strategy:
      1. Return the cached value if it's less than 15 minutes old.
      2. Try the live APIs (in order).
      3. Fall back to ``NGN_USD_RATE`` env var.
      4. Fall back to hardcoded 1600.
    """
    global _cached_rate, _cached_at  # noqa: PLW0603

    now = time.monotonic()
    if _cached_rate is not None and (now - _cached_at) < _CACHE_TTL_SECONDS:
        return _cached_rate

    live = _fetch_live_rate()
    if live is not None:
        _cached_rate = live
        _cached_at = now
        return live

    # All APIs failed — try env var, then hardcoded
    fallback = _get_env_fallback()
    logger.warning("Using fallback NGN/USD rate: %s", fallback)
    # Cache the fallback for only 2 minutes so we retry the APIs sooner
    _cached_rate = fallback
    _cached_at = now - (_CACHE_TTL_SECONDS - 120)
    return fallback


def force_refresh_rate() -> Decimal:
    """Bust the cache and fetch a fresh rate right now.

    Called by the ``POST /exchange-rate/refresh`` endpoint so the user
    can manually trigger an update from the dashboard.
    """
    global _cached_rate, _cached_at  # noqa: PLW0603
    _cached_rate = None
    _cached_at = 0.0
    return get_ngn_usd_rate()


def get_conversion_rate(currency: str) -> Decimal:
    """Get currency conversion rate for analytics.

    Returns the NGN-per-USD rate for USD, or 1 for NGN (no conversion).
    Uses real-time API with in-memory caching.
    """
    if currency != "USD":
        return Decimal("1")
    return get_ngn_usd_rate()


def get_exchange_rate_info() -> dict:
    """Return current rate info for the frontend (rate + freshness)."""
    rate = get_ngn_usd_rate()
    return {
        "rate": float(rate),
        "currency_pair": "NGN/USD",
        "description": f"₦{rate:,.0f} = $1",
    }
