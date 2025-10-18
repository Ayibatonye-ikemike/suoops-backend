"""Metrics facade.

Uses Prometheus client library if available; otherwise falls back to logging-only no-ops.
Service code should ONLY call the semantic helpers here so we can change backend freely.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("metrics")

try:  # pragma: no cover - import guard
    from prometheus_client import Counter, Histogram

    _INVOICE_CREATED = Counter("invoice_created_total", "Invoices successfully created")
    _INVOICE_PAID = Counter("invoice_paid_total", "Invoices marked paid")
    _WHATSAPP_PARSE_UNKNOWN = Counter(
        "whatsapp_parse_unknown_total", "Inbound WhatsApp messages with unknown intent"
    )
    _PAYMENT_CONFIRM_LATENCY = Histogram(
        "payment_confirmation_latency_seconds", "Latency from creation to payment confirmation"
    )
    _ENABLED = True
except Exception:  # noqa: BLE001
    _ENABLED = False
    _INVOICE_CREATED = _INVOICE_PAID = _WHATSAPP_PARSE_UNKNOWN = _PAYMENT_CONFIRM_LATENCY = None  # type: ignore
    logger.warning("Prometheus client not available; metrics will be log-only")


def invoice_created():
    if _ENABLED:
        _INVOICE_CREATED.inc()  # type: ignore[union-attr]
    else:
        logger.debug("metric invoice_created_total += 1")


def invoice_paid(latency_seconds: float | None = None):
    if _ENABLED:
        _INVOICE_PAID.inc()  # type: ignore[union-attr]
        if latency_seconds is not None:
            _PAYMENT_CONFIRM_LATENCY.observe(latency_seconds)  # type: ignore[union-attr]
    else:
        logger.debug("metric invoice_paid_total += 1")
        if latency_seconds is not None:
            logger.debug("observe payment_confirmation_latency_seconds=%s", latency_seconds)


def parse_unknown():
    if _ENABLED:
        _WHATSAPP_PARSE_UNKNOWN.inc()  # type: ignore[union-attr]
    else:
        logger.debug("metric whatsapp_parse_unknown_total += 1")


class PaymentLatencyTimer:
    def __init__(self):
        self.start = time.perf_counter()

    def stop(self) -> float:
        dur = time.perf_counter() - self.start
        invoice_paid(latency_seconds=dur)
        return dur

__all__ = [
    "invoice_created",
    "invoice_paid",
    "parse_unknown",
    "PaymentLatencyTimer",
]
