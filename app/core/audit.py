"""Audit logging utilities.

Writes structured JSON lines to a dedicated audit log file and standard logger.
Each event should describe a security- or compliance-relevant action.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

_AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_FILE", "storage/audit.log")
_logger = logging.getLogger("audit")


def log_audit_event(action: str, user_id: int | None = None, status: str = "success", **metadata: Any) -> None:
    """Record an audit event.

    Parameters:
        action: A machine-readable action key (e.g. 'admin.users.count', 'user.login').
        user_id: The acting user's ID (if available).
        status: 'success' | 'failure' | 'denied'.
        **metadata: Additional context fields (ids, counts, etc.).
    """
    event = {
        "ts": int(time.time()),
        "action": action,
        "user_id": user_id,
        "status": status,
        **metadata,
    }
    line = json.dumps(event, separators=(",", ":"))
    # Append to file (best effort)
    try:
        os.makedirs(os.path.dirname(_AUDIT_LOG_PATH), exist_ok=True)
        with open(_AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:  # noqa: BLE001
        _logger.debug("Failed to write audit event to file: %s", event)
    # Emit via logger for aggregation
    _logger.info(line)


def log_denied(action: str, user_id: int | None = None, reason: str | None = None, **extra: Any) -> None:
    log_audit_event(action, user_id=user_id, status="denied", reason=reason, **extra)


def log_failure(action: str, user_id: int | None = None, error: str | None = None, **extra: Any) -> None:
    log_audit_event(action, user_id=user_id, status="failure", error=error, **extra)
