"""Real-time NGN/USD exchange rate with caching.

Fetches the current rate from a free public API and caches it for 1 hour.
Falls back to the NGN_USD_RATE env var, then to a hardcoded default,
so the dashboard never breaks even if the API is down.
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
_CACHE_TTL_SECONDS = 3600  # 1 hour

# Free, no-key-required API.  Returns JSON like:
#   {"result":"success","base_code":"USD","target_code":"NGN","conversion_rate":1580.5}
_API_URL = "https://open.er-api.com/v6/latest/USD"


def _fetch_live_rate() -> Decimal | None:
    """Call the exchange-rate API and return the NGN rate, or None on failure."""
    try:
        resp = httpx.get(_API_URL, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        ngn_rate = data.get("rates", {}).get("NGN")
        if ngn_rate is not None:
            rate = Decimal(str(ngn_rate))
            logger.info("Fetched live NGN/USD rate: %s", rate)
            return rate
        logger.warning("NGN rate not found in API response: %s", data)
    except httpx.HTTPError as exc:
        logger.warning("Exchange rate API HTTP error: %s", exc)
    except (ValueError, KeyError, InvalidOperation) as exc:
        logger.warning("Failed to parse exchange rate response: %s", exc)
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
      1. Return the cached value if it's less than 1 hour old.
      2. Try the live API.
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

    # API failed — try env var, then hardcoded
    fallback = _get_env_fallback()
    logger.warning("Using fallback NGN/USD rate: %s", fallback)
    # Cache the fallback for 5 minutes so we retry the API sooner
    _cached_rate = fallback
    _cached_at = now - (_CACHE_TTL_SECONDS - 300)
    return fallback


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
