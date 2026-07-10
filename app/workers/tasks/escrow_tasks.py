"""Escrow release worker.

Periodically pays out storefront-order holds whose buyer-protection window has
elapsed with no dispute — Transferring the seller their share (gross − 3%). Each
release is idempotent (deterministic Paystack reference), and a failed release
simply stays 'held' and retries on the next run.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from celery import Task

from app.db.session import session_scope
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="escrow.release_due_orders",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
)
def release_due_escrow_orders(self: Task) -> dict[str, Any]:
    """Release all 'held' escrow orders whose window has elapsed."""
    from sqlalchemy import and_, or_

    from app.models.models import StorefrontOrderEscrow, User
    from app.services.escrow_service import release_escrow

    released = failed = 0
    with session_scope() as db:
        now = dt.datetime.now(dt.timezone.utc)
        due = (
            db.query(StorefrontOrderEscrow)
            .join(User, StorefrontOrderEscrow.seller_id == User.id)
            .filter(
                StorefrontOrderEscrow.status == "held",
                # Never auto-release collusion/anomaly-flagged orders.
                StorefrontOrderEscrow.held_for_review.is_(False),
                # Skip sellers whose payouts are frozen (post bank-change cooldown).
                (User.payout_frozen_until.is_(None)) | (User.payout_frozen_until <= now),
                or_(
                    # Cleared (protection window elapsed OR buyer confirmed early)
                    # AND settled (T+1 cadence) → pay the seller out. The settle_at
                    # gate keeps payouts on a next-morning settlement, never same
                    # day, funded by settled collections rather than float.
                    and_(
                        or_(
                            and_(
                                StorefrontOrderEscrow.release_due_at.isnot(None),
                                StorefrontOrderEscrow.release_due_at <= now,
                            ),
                            StorefrontOrderEscrow.confirmed_at.isnot(None),
                        ),
                        or_(
                            StorefrontOrderEscrow.settle_at.is_(None),  # legacy rows
                            StorefrontOrderEscrow.settle_at <= now,
                        ),
                    ),
                    # OR a payout was already initiated (e.g. an admin release) and
                    # is in flight — reconcile/confirm it now, don't wait.
                    StorefrontOrderEscrow.transfer_reference.isnot(None),
                ),
            )
            .limit(200)
            .all()
        )
        for escrow in due:
            try:
                if release_escrow(db, escrow, reason="window elapsed"):
                    released += 1
            except Exception as exc:  # noqa: BLE001 — keep going; retry next run
                failed += 1
                db.rollback()
                logger.warning("Escrow release failed for %s: %s", escrow.id, exc)

    result = {"checked": released + failed, "released": released, "failed": failed}
    logger.info("Escrow release run: %s", result)
    return result
