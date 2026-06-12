"""Admin security helpers: client IP extraction, IP allowlist, login audit.

These utilities back two admin-protection features:

* An optional IP allowlist that restricts every ``/admin*`` route to a set of
  configured addresses/CIDR ranges (``settings.ADMIN_IP_ALLOWLIST``).
* A persisted audit trail of admin authentication events so suspicious logins
  (e.g. from unexpected IPs) are visible in the admin panel.
"""
from __future__ import annotations

import ipaddress
import logging
from functools import lru_cache

from sqlalchemy.orm import Session
from starlette.requests import Request

from app.core.config import settings
from app.models.admin_models import AdminLoginAudit

logger = logging.getLogger(__name__)


def get_client_ip(request: Request) -> str | None:
    """Return the originating client IP.

    Render (and most reverse proxies) put the real client IP in the
    ``X-Forwarded-For`` header. We use the first hop in that list and fall back
    to the direct peer address.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return None


@lru_cache(maxsize=1)
def _parse_allowlist(raw: str) -> tuple[ipaddress._BaseNetwork, ...]:
    """Parse the comma-separated allowlist into network objects (cached)."""
    networks: list[ipaddress._BaseNetwork] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            # strict=False lets a bare host (e.g. "203.0.113.4") parse as a /32.
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            logger.warning("Ignoring invalid ADMIN_IP_ALLOWLIST entry: %r", entry)
    return tuple(networks)


def admin_ip_allowlist_enabled() -> bool:
    return bool(settings.ADMIN_IP_ALLOWLIST and settings.ADMIN_IP_ALLOWLIST.strip())


def is_admin_ip_allowed(ip: str | None) -> bool:
    """Return True if ``ip`` may access admin routes.

    When no allowlist is configured, all IPs are allowed (feature off).
    """
    if not admin_ip_allowlist_enabled():
        return True
    networks = _parse_allowlist(settings.ADMIN_IP_ALLOWLIST or "")
    if not networks:
        # Misconfigured (all entries invalid) — fail open rather than lock out.
        return True
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in networks)


def record_admin_login_event(
    db: Session,
    *,
    request: Request | None = None,
    status: str,
    event: str = "login",
    admin_id: int | None = None,
    email: str | None = None,
    reason: str | None = None,
) -> None:
    """Persist an admin authentication event. Best-effort: never raises."""
    try:
        ip = get_client_ip(request) if request is not None else None
        user_agent = None
        if request is not None:
            user_agent = (request.headers.get("user-agent") or "")[:512] or None
        entry = AdminLoginAudit(
            admin_id=admin_id,
            email=(email or None),
            ip=ip,
            user_agent=user_agent,
            status=status,
            event=event,
            reason=reason,
        )
        db.add(entry)
        db.commit()
    except Exception:  # noqa: BLE001
        logger.debug("Failed to record admin login audit event", exc_info=True)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
