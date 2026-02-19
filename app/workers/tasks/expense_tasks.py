"""
Expense Tracking Tasks.

Celery tasks for expense summaries and reminders.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from celery import Task
from sqlalchemy import func

from app.core.config import settings
from app.db.session import session_scope
from app.models.models import User
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="expense.send_summary",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_expense_summary(
    self: Task,
    user_id: int,
    period: str = "weekly",
) -> dict[str, Any]:
    """
    Send expense summary to user via WhatsApp/email.

    Args:
        user_id: User ID
        period: 'daily', 'weekly', or 'monthly'

    Returns:
        Summary statistics
    """
    from app.models.expense import Expense
    from app.services.tax_reporting_service import (
        compute_actual_profit_by_date_range,
        compute_revenue_by_date_range,
    )

    with session_scope() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error("User %s not found for expense summary", user_id)
            return {"success": False, "error": "User not found"}

        start_date, end_date = _calculate_period_range(period)

        expenses = db.query(Expense).filter(
            Expense.user_id == user_id,
            Expense.date >= start_date,
            Expense.date <= end_date,
        ).all()

        by_category, total_expenses = _aggregate_expenses(expenses)
        revenue = compute_revenue_by_date_range(db, user_id, start_date, end_date, "paid")
        profit = compute_actual_profit_by_date_range(db, user_id, start_date, end_date, "paid")
        pit_band = _get_pit_band(profit, period)

        message = _format_summary_message(
            period, revenue, total_expenses, profit, by_category, pit_band
        )

        if user.phone:
            _send_whatsapp_message(user.phone, message, user_id, period)

        return {
            "success": True,
            "user_id": user_id,
            "period": period,
            "total_expenses": float(total_expenses),
            "revenue": float(revenue),
            "profit": float(profit),
            "categories": len(by_category),
        }


@celery_app.task(
    bind=True,
    name="expense.send_reminders",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
)
def send_expense_reminders(self: Task) -> dict[str, Any]:
    """
    Send reminders to users who haven't recorded expenses recently.

    Targets users with no expenses in past 7 days.

    Returns:
        Statistics on reminders sent
    """
    from app.bot.whatsapp_client import WhatsAppClient
    from app.models.expense import Expense

    with session_scope() as db:
        seven_days_ago = date.today() - timedelta(days=7)

        users_with_old_expenses = (
            db.query(User.id)
            .join(Expense)
            .group_by(User.id)
            .having(func.max(Expense.date) < seven_days_ago)
        ).subquery()

        users = db.query(User).filter(User.id.in_(users_with_old_expenses)).all()

        message = (
            "👋 Hi! Don't forget to send your weekly expenses to stay compliant "
            "and maximize your deductions!\n\n"
            "You can:\n"
            "📸 Snap a photo of receipts\n"
            "🎤 Send a voice note\n"
            "✍️ Or type: 'Expense ₦1000 for data'\n\n"
            "Tracking expenses helps you pay less tax legally! 💰"
        )

        sent_count = 0
        client = WhatsAppClient(settings.WHATSAPP_API_KEY)

        for user in users:
            if user.phone:
                try:
                    client.send_text(user.phone, message)
                    sent_count += 1
                    logger.info("Sent expense reminder to user %s", user.id)
                except Exception as e:
                    logger.error("Failed to send reminder to user %s: %s", user.id, e)

        return {
            "success": True,
            "reminders_sent": sent_count,
            "users_targeted": len(users),
        }


# ============================================================================
# Private Helper Functions
# ============================================================================


def _calculate_period_range(period: str) -> tuple[date, date]:
    """Calculate date range for period."""
    today = date.today()
    if period == "daily":
        return today, today
    elif period == "weekly":
        return today - timedelta(days=7), today
    elif period == "monthly":
        return today.replace(day=1), today
    return today - timedelta(days=30), today


def _aggregate_expenses(expenses) -> tuple[dict[str, Decimal], Decimal]:
    """Aggregate expenses by category."""
    by_category: dict[str, Decimal] = {}
    total_expenses = Decimal("0")

    for expense in expenses:
        cat = expense.category
        by_category[cat] = by_category.get(cat, Decimal("0")) + expense.amount
        total_expenses += expense.amount

    return by_category, total_expenses


def _get_pit_band(profit: Decimal, period: str) -> str:
    """Determine PIT band based on annualized profit."""
    multiplier = 12 if period == "monthly" else 52 if period == "weekly" else 365
    annual_profit = profit * multiplier

    if annual_profit <= 800_000:
        return "0%"
    elif annual_profit <= 3_000_000:
        return "15%"
    elif annual_profit <= 12_000_000:
        return "18%"
    elif annual_profit <= 25_000_000:
        return "21%"
    elif annual_profit <= 50_000_000:
        return "23%"
    return "25%"


def _format_summary_message(
    period: str,
    revenue: Decimal,
    total_expenses: Decimal,
    profit: Decimal,
    by_category: dict[str, Decimal],
    pit_band: str,
) -> str:
    """Format expense summary message."""
    period_display = period.title()
    message = f"📊 {period_display} Financial Summary\n\n"
    message += f"💰 Total Income: ₦{revenue:,.0f}\n"
    message += f"💸 Total Expenses: ₦{total_expenses:,.0f}\n"
    message += f"✅ Profit: ₦{profit:,.0f}\n\n"

    if by_category:
        message += "📂 Expenses by Category:\n"
        for category, amount in sorted(by_category.items(), key=lambda x: x[1], reverse=True):
            cat_display = category.replace("_", " ").title()
            message += f"  • {cat_display}: ₦{amount:,.0f}\n"
        message += "\n"

    message += f"💡 Expected PIT band: {pit_band}"
    return message


def _send_whatsapp_message(phone: str, message: str, user_id: int, period: str) -> None:
    """Send WhatsApp message."""
    from app.bot.whatsapp_client import WhatsAppClient

    try:
        client = WhatsAppClient(settings.WHATSAPP_API_KEY)
        client.send_text(phone, message)
        logger.info("Sent %s expense summary to user %s", period, user_id)
    except Exception as e:
        logger.error("Failed to send WhatsApp summary to %s: %s", user_id, e)
