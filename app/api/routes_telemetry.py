from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.rbac import staff_or_admin_required  # optional future use
from app.core.config import settings
from app.api.rate_limit import limiter

try:  # pragma: no cover
    from prometheus_client import Counter
    _TELEMETRY_COUNTER = Counter(
        "suoops_telemetry_events_total",
        "Total telemetry events received",
        labelnames=["type"],
    )
except Exception:  # noqa: BLE001
    _TELEMETRY_COUNTER = None


class TelemetryIn(BaseModel):
    """Telemetry event payload from frontend."""
    type: str = Field(min_length=1, max_length=100)
    ts: str
    trace_id: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None


router = APIRouter(prefix="/telemetry", tags=["telemetry"])


LOG_PATH = Path("telemetry.log")


def _append_log(event: TelemetryIn) -> None:
    record = {
        "received_ts": time.time(),
        "type": event.type,
        "client_ts": event.ts,
        "trace_id": event.trace_id,
        "detail": event.detail,
    }
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:  # noqa: BLE001
        # Swallow to avoid impacting ingestion path
        pass


@router.post("/frontend")
@limiter.limit("120/minute")  # IP-based limit to mitigate abuse
async def ingest_frontend(event: TelemetryIn, request: Request):  # noqa: D401
    """Ingest a frontend telemetry event.

    Validates basic structure; increments Prometheus counter; persists to log.
    Returns 202 on success.
    """
    if not event.type:
        raise HTTPException(status_code=400, detail="Missing event type")
    # Enforce API key in production
    if settings.ENV.lower() == "prod":
        header_key = request.headers.get("X-Telemetry-Key")
        if not header_key or header_key != settings.TELEMETRY_INGEST_KEY:
            raise HTTPException(status_code=401, detail="Unauthorized")
    if _TELEMETRY_COUNTER:
        try:
            _TELEMETRY_COUNTER.labels(type=event.type).inc()
        except Exception:  # noqa: BLE001
            pass
    _append_log(event)
    return {"status": "accepted"}
