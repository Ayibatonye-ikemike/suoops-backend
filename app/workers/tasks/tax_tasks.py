"""
Tax and Fiscalization Tasks.

Celery tasks for tax report generation and invoice fiscalization.
"""
from __future__ import annotations

import gc
import logging

try:
    import resource
except Exception:
    resource = None  # type: ignore

from celery import Task

from app.db.session import session_scope
from app.models.models import Invoice, User
from app.models.tax_models import FiscalInvoice
from app.services.pdf_service import PDFService
from app.services.tax_reporting_service import TaxReportingService
from app.services.tax_service import TaxProfileService
from app.storage.s3_client import s3_client
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _rss_mb() -> float:
    """Get current RSS memory in MB."""
    if resource is None:
        return -1.0
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


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

    Memory-conscious implementation using streaming and periodic GC.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    prev_month = now.month - 1 or 12
    year = now.year - 1 if prev_month == 12 and now.month == 1 else now.year

    with session_scope() as db:
        tax_service = TaxProfileService(db)
        reporting = TaxReportingService(db)
        pdf_service = PDFService(s3_client)

        user_id_iter = db.query(User.id).yield_per(100)
        total = 0
        failures = 0

        for (user_id,) in user_id_iter:
            total += 1
            try:
                report = reporting.generate_monthly_report(
                    user_id, year, prev_month, basis=basis, force_regenerate=False
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
                            total, rss,
                        )

                logger.info(
                    "Generated monthly tax report for user=%s period=%s-%02d",
                    user_id, year, prev_month,
                )
            except Exception as e:
                failures += 1
                logger.exception("Failed generating report for user %s: %s", user_id, e)
                tax_service.record_alert(
                    category="tax.report",
                    message=f"Monthly report generation failed for user {user_id}: {e}",
                    severity="error",
                )
            db.expire_all()

        if failures:
            tax_service.record_alert(
                category="tax.report.summary",
                message=f"Monthly report generation completed with {failures} failures",
                severity="warning" if failures < total else "error",
            )

        rss_final = _rss_mb()
        if rss_final > 0:
            logger.info(
                "[tax.generate_previous_month_reports] completed users=%s rss_final=%.1fMB failures=%s",
                total, rss_final, failures,
            )
    gc.collect()


@celery_app.task(name="fiscalization.transmit_invoice", bind=True)
def transmit_invoice(self: Task, fiscal_code: str) -> None:
    """Background transmission of a fiscalized invoice to external gateway."""
    import asyncio

    from app.services.fiscalization_service import FiscalTransmitter

    with session_scope() as db:
        fi: FiscalInvoice | None = (
            db.query(FiscalInvoice)
            .filter(FiscalInvoice.fiscal_code == fiscal_code)
            .first()
        )
        if not fi:
            logger.warning("Transmit skip: fiscal invoice not found | fiscal_code=%s", fiscal_code)
            return

        inv: Invoice | None = db.query(Invoice).filter(Invoice.id == fi.invoice_id).first()
        if not inv:
            logger.warning(
                "Transmit skip: invoice missing | fiscal_code=%s invoice_id=%s",
                fiscal_code, fi.invoice_id,
            )
            return

        transmitter = FiscalTransmitter()
        try:
            tx_result = asyncio.run(transmitter.transmit(inv, fi))
            _update_fiscal_invoice(db, fi, tx_result)
            logger.info(
                "Fiscal invoice transmitted | fiscal_code=%s status=%s",
                fiscal_code, fi.firs_validation_status,
            )
        except Exception as e:
            logger.exception(
                "Fiscal invoice transmission failed | fiscal_code=%s error=%s",
                fiscal_code, e,
            )
            _record_transmission_failure(db, fiscal_code, e)


def _update_fiscal_invoice(db, fi: FiscalInvoice, tx_result: dict) -> None:
    """Update fiscal invoice with transmission result."""
    from datetime import datetime, timezone

    fi.firs_validation_status = tx_result.get("status", fi.firs_validation_status)
    if tx_result.get("transaction_id"):
        fi.firs_transaction_id = tx_result["transaction_id"]

    existing = fi.firs_response or {}
    existing["transmission"] = tx_result
    fi.firs_response = existing

    if tx_result.get("status") == "validated" and not fi.transmitted_at:
        fi.transmitted_at = datetime.now(timezone.utc)

    db.commit()


def _record_transmission_failure(db, fiscal_code: str, error: Exception) -> None:
    """Record transmission failure as alert."""
    try:
        from app.models.alert_models import AlertEvent
        evt = AlertEvent(
            category="fiscal.transmit",
            message=f"Transmit failed {fiscal_code}: {error}",
            severity="error",
        )
        db.add(evt)
        db.commit()
    except Exception:
        db.rollback()
