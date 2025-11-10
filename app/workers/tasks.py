from __future__ import annotations

import asyncio
import gc
import logging
from typing import Any

try:
    import resource  # POSIX-only; used for memory diagnostics
except Exception:  # pragma: no cover
    resource = None  # type: ignore

from celery import Task

from app.core.config import settings
from app.db.session import session_scope
from app.models.models import Invoice, User
from app.models.tax_models import FiscalInvoice
from app.services.pdf_service import PDFService
from app.services.tax_reporting_service import TaxReportingService
from app.services.tax_service import TaxProfileService
from app.storage.s3_client import s3_client
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="whatsapp.process_inbound",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def process_whatsapp_inbound(self: Task, payload: dict[str, Any]) -> None:
    """Process inbound WhatsApp message.

    Heavy NLP / adapter imports are done lazily to keep baseline worker RSS low.
    """
    # Lazy imports (these may pull in ML models / regex corpora)
    from app.bot.nlp_service import NLPService  # local import
    from app.bot.whatsapp_adapter import WhatsAppClient, WhatsAppHandler  # local import
    with session_scope() as db:
        handler = WhatsAppHandler(
            client=WhatsAppClient(settings.WHATSAPP_API_KEY),
            nlp=NLPService(),
            db=db,
        )
        asyncio.run(handler.handle_incoming(payload))
    # Encourage garbage collection (large NLP objects) after task completes
    gc.collect()


@celery_app.task(
    name="maintenance.send_overdue_reminders",
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def send_overdue_reminders() -> None:
    try:
        logger.info("(stub) scanning for overdue invoices")
        # Simulate potential transient failure placeholder
    except Exception as exc:  # noqa: BLE001
        logger.warning("Reminder task transient failure: %s", exc)
        raise


@celery_app.task(
    bind=True,
    name="payments.sync_provider_status",
    autoretry_for=(Exception,),
    retry_backoff=10,
    retry_jitter=True,
    retry_kwargs={"max_retries": 4},
)
def sync_provider_status(self: Task, provider: str, reference: str) -> None:
    """Sync payment provider status with retries on transient errors."""
    logger.info("Syncing provider status | provider=%s reference=%s", provider, reference)


@celery_app.task(
    bind=True,
    name="ocr.parse_image",
    autoretry_for=(Exception,),
    retry_backoff=15,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def ocr_parse_image(self: Task, image_bytes_b64: str, context: str | None = None) -> dict[str, Any]:
    """Run OCR parse with retries (handles rate limits/timeouts)."""
    import base64

    from app.services.ocr_service import OCRService
    raw = base64.b64decode(image_bytes_b64)
    service = OCRService()
    result = asyncio.run(service.parse_receipt(raw, context))
    if not result.get("success"):
        # Escalate failure for retry if transient network issues (heuristic)
        if "timeout" in str(result.get("error", "")).lower():
            raise Exception(result["error"])  # noqa: TRY002
    return result


@celery_app.task(
    bind=True,
    name="tax.generate_previous_month_reports",
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def generate_previous_month_reports(self: Task, basis: str = "paid") -> None:
    """Generate monthly tax reports (PDF) for all users for the previous month.

    Memory-conscious implementation:
    - Stream user IDs instead of loading full objects
    - Periodic GC + optional RSS logging to mitigate R14 on Heroku
    """
    from datetime import datetime, timezone

    def _rss_mb() -> float:
        if resource is None:  # platform fallback
            return -1.0
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0  # KB -> MB approximation

    now = datetime.now(timezone.utc)
    prev_month = now.month - 1 or 12
    # If rolling from January to December, decrement year; else current year
    if prev_month == 12 and now.month == 1:
        year = now.year - 1
    else:
        year = now.year
    with session_scope() as db:
        tax_service = TaxProfileService(db)  # profile/classification
        reporting = TaxReportingService(db)
        pdf_service = PDFService(s3_client)
        # Stream just IDs to keep ORM identity map small
        user_id_iter = db.query(User.id).yield_per(100)
        total = 0
        failures = 0
        for (user_id,) in user_id_iter:
            total += 1
            try:
                report = reporting.generate_monthly_report(
                    user_id,
                    year,
                    prev_month,
                    basis=basis,
                    force_regenerate=False,
                )
                if not report.pdf_url:
                    pdf_url = pdf_service.generate_monthly_tax_report_pdf(report, basis=basis)
                    reporting.attach_report_pdf(report, pdf_url)
                if total % 25 == 0:
                    gc.collect()
                    rss = _rss_mb()
                    if rss > 0:
                        logger.info(
                            "[tax.generate_previous_month_reports] progress=%s users rss=%.1fMB",
                            total,
                            rss,
                        )
                logger.info(
                    "Generated monthly tax report for user=%s period=%s-%02d",
                    user_id,
                    year,
                    prev_month,
                )
            except Exception as e:  # noqa: BLE001
                failures += 1
                logger.exception("Failed generating report for user %s: %s", user_id, e)
                tax_service.record_alert(
                    category="tax.report",
                    message=f"Monthly report generation failed for user {user_id}: {e}",
                    severity="error",
                )
            # Expire ORM state aggressively to release memory
            db.expire_all()
        if failures:
            tax_service.record_alert(
                category="tax.report.summary",
                message=f"Monthly report generation completed with {failures} failures",
                severity="warning" if failures < total else "error",
            )
        # Final memory log
        rss_final = _rss_mb()
        if rss_final > 0:
            logger.info(
                "[tax.generate_previous_month_reports] completed users=%s rss_final=%.1fMB failures=%s",
                total,
                rss_final,
                failures,
            )
    gc.collect()


@celery_app.task(name="fiscalization.transmit_invoice", bind=True)
def transmit_invoice(self: Task, fiscal_code: str) -> None:
    """Background transmission of a fiscalized invoice to external gateway.

    Looks up FiscalInvoice by fiscal_code then attempts external transmit using FiscalTransmitter.
    Safe no-op if accreditation or credentials are missing.
    """
    from app.services.fiscalization_service import FiscalTransmitter  # local import
    with session_scope() as db:
        fi: FiscalInvoice | None = (
            db.query(FiscalInvoice)
            .filter(FiscalInvoice.fiscal_code == fiscal_code)
            .first()
        )
        if not fi:
            logger.warning("Transmit skip: fiscal invoice not found | fiscal_code=%s", fiscal_code)
            return
        inv: Invoice | None = (
            db.query(Invoice)
            .filter(Invoice.id == fi.invoice_id)
            .first()
        )
        if not inv:
            logger.warning("Transmit skip: invoice missing | fiscal_code=%s invoice_id=%s", fiscal_code, fi.invoice_id)
            return
        transmitter = FiscalTransmitter()
        try:
            import asyncio
            tx_result = asyncio.run(transmitter.transmit(inv, fi))
            fi.firs_validation_status = tx_result.get("status", fi.firs_validation_status)
            if tx_result.get("transaction_id"):
                fi.firs_transaction_id = tx_result["transaction_id"]
            # Merge/new response data
            existing = fi.firs_response or {}
            existing["transmission"] = tx_result
            fi.firs_response = existing
            if tx_result.get("status") == "validated" and not fi.transmitted_at:
                from datetime import datetime
                from datetime import timezone as _tz
                fi.transmitted_at = datetime.now(_tz.utc)
            db.commit()
            logger.info(
                "Fiscal invoice transmitted | fiscal_code=%s status=%s",
                fiscal_code,
                fi.firs_validation_status,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception(
                "Fiscal invoice transmission failed | fiscal_code=%s error=%s",
                fiscal_code,
                e,
            )
            # Record alert best-effort
            try:
                from app.models.alert_models import AlertEvent  # type: ignore
                evt = AlertEvent(
                    category="fiscal.transmit",
                    message=f"Transmit failed {fiscal_code}: {e}",
                    severity="error",
                )
                db.add(evt)
                db.commit()
            except Exception:
                db.rollback()


# ========== EXPENSE TRACKING AUTOMATION ==========


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
    from datetime import date, timedelta
    from decimal import Decimal
    from sqlalchemy import func
    
    from app.bot.whatsapp_client import WhatsAppClient
    from app.models.expense import Expense
    from app.models.models import Invoice
    from app.services.tax_reporting_service import (
        compute_revenue_by_date_range,
        compute_expenses_by_date_range,
        compute_actual_profit_by_date_range,
    )
    
    with session_scope() as db:
        # Get user
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error(f"User {user_id} not found for expense summary")
            return {"success": False, "error": "User not found"}
        
        # Calculate period
        today = date.today()
        if period == "daily":
            start_date = today
            end_date = today
        elif period == "weekly":
            start_date = today - timedelta(days=7)
            end_date = today
        elif period == "monthly":
            start_date = today.replace(day=1)
            end_date = today
        else:
            start_date = today - timedelta(days=30)
            end_date = today
        
        # Get expenses
        expenses = db.query(Expense).filter(
            Expense.user_id == user_id,
            Expense.date >= start_date,
            Expense.date <= end_date,
        ).all()
        
        # Aggregate by category
        by_category: dict[str, Decimal] = {}
        total_expenses = Decimal("0")
        
        for expense in expenses:
            cat = expense.category
            by_category[cat] = by_category.get(cat, Decimal("0")) + expense.amount
            total_expenses += expense.amount
        
        # Get revenue and profit
        revenue = compute_revenue_by_date_range(db, user_id, start_date, end_date, "paid")
        profit = compute_actual_profit_by_date_range(db, user_id, start_date, end_date, "paid")
        
        # Estimate PIT band (simplified)
        annual_profit = profit * 12 if period == "monthly" else profit * 52 if period == "weekly" else profit * 365
        
        if annual_profit <= 800_000:
            pit_band = "0%"
        elif annual_profit <= 3_000_000:
            pit_band = "15%"
        elif annual_profit <= 12_000_000:
            pit_band = "18%"
        elif annual_profit <= 25_000_000:
            pit_band = "21%"
        elif annual_profit <= 50_000_000:
            pit_band = "23%"
        else:
            pit_band = "25%"
        
        # Format message
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
        if period == "monthly":
            message += f" (based on ₦{annual_profit:,.0f} annual projection)"
        
        # Send via WhatsApp
        if user.phone:
            try:
                client = WhatsAppClient(settings.WHATSAPP_API_KEY)
                client.send_text(user.phone, message)
                logger.info(f"Sent {period} expense summary to user {user_id}")
            except Exception as e:
                logger.error(f"Failed to send WhatsApp summary to {user_id}: {e}")
        
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
    from datetime import date, timedelta
    from sqlalchemy import and_, not_
    
    from app.bot.whatsapp_client import WhatsAppClient
    from app.models.expense import Expense
    
    with session_scope() as db:
        # Find users with no expenses in past 7 days
        seven_days_ago = date.today() - timedelta(days=7)
        
        # Get users who have expenses but not recently
        users_with_old_expenses = (
            db.query(User.id)
            .join(Expense)
            .group_by(User.id)
            .having(func.max(Expense.date) < seven_days_ago)
        ).subquery()
        
        users = db.query(User).filter(
            User.id.in_(users_with_old_expenses)
        ).all()
        
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
                    logger.info(f"Sent expense reminder to user {user.id}")
                except Exception as e:
                    logger.error(f"Failed to send reminder to user {user.id}: {e}")
        
        return {
            "success": True,
            "reminders_sent": sent_count,
            "users_targeted": len(users),
        }
