"""Quota/plan helpers extracted from InvoiceService."""
from __future__ import annotations

import datetime as dt
import logging
from typing import TYPE_CHECKING

from app.core.exceptions import InvoiceLimitExceededError, UserNotFoundError
from app.models import models

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class InvoiceQuotaMixin:
    """Provides plan/quota related utilities for invoice flows."""

    db: "Session"

    def check_invoice_quota(self, issuer_id: int) -> dict[str, object]:
        user = self.db.query(models.User).filter(models.User.id == issuer_id).one_or_none()
        if not user:
            raise UserNotFoundError()

        self._reset_usage_if_needed(user)
        plan_limit = user.plan.invoice_limit

        if user.invoices_this_month >= plan_limit:
            upgrade_message = self._get_upgrade_message(user.plan)
            return {
                "can_create": False,
                "plan": user.plan.value,
                "used": user.invoices_this_month,
                "limit": plan_limit,
                "message": upgrade_message,
            }

        remaining = plan_limit - user.invoices_this_month
        message = f"{remaining} invoices remaining this month"
        if remaining <= 5:
            upgrade_message = self._get_upgrade_message(user.plan)
            message = f"⚠️ Only {remaining} invoices left! {upgrade_message}"

        return {
            "can_create": True,
            "plan": user.plan.value,
            "used": user.invoices_this_month,
            "limit": plan_limit,
            "message": message,
        }

    def enforce_quota(self, issuer_id: int, invoice_type: str) -> None:
        """Raise if the issuer cannot create more invoices."""
        if invoice_type != "revenue":
            return
        quota = self.check_invoice_quota(issuer_id)
        if not quota["can_create"]:
            raise InvoiceLimitExceededError(
                plan=quota["plan"],
                limit=quota["limit"],
                used=quota["used"],
            )

    def _reset_usage_if_needed(self, user: models.User) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        last_reset = user.usage_reset_at.replace(tzinfo=dt.timezone.utc)
        if now.year > last_reset.year or (now.year == last_reset.year and now.month > last_reset.month):
            user.invoices_this_month = 0
            user.usage_reset_at = now
            self.db.commit()
            logger.info("Reset invoice usage for user %s (new month)", user.id)

    @staticmethod
    def _get_upgrade_message(current_plan: models.SubscriptionPlan) -> str:
        messages = {
            models.SubscriptionPlan.FREE: "Upgrade to Starter (₦4,500/month) for 100 invoices!",
            models.SubscriptionPlan.STARTER: "Upgrade to Pro (₦8,000/month) for 200 invoices!",
            models.SubscriptionPlan.PRO: "Upgrade to Business (₦16,000/month) for 300 invoices!",
            models.SubscriptionPlan.BUSINESS: "You're on the highest plan with 300 invoices/month.",
        }
        return messages.get(current_plan, "Upgrade to increase your invoice limit!")
