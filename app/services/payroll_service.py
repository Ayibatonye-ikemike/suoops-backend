from __future__ import annotations

import logging
from decimal import Decimal
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import models, schemas

logger = logging.getLogger(__name__)


class PayrollService:
    def __init__(self, db: Session):
        self.db = db

    def get_workers(self, issuer_id: int) -> list[models.Worker]:
        """Get all workers for a given issuer."""
        return (
            self.db.query(models.Worker)
            .filter(models.Worker.issuer_id == issuer_id)
            .order_by(models.Worker.name)
            .all()
        )

    def add_worker(self, issuer_id: int, payload: schemas.WorkerCreate) -> models.Worker:
        worker = models.Worker(
            issuer_id=issuer_id,
            name=payload.name,
            daily_rate=payload.daily_rate,
        )
        self.db.add(worker)
        self.db.commit()
        self.db.refresh(worker)
        return worker

    def create_payroll_run(
        self,
        issuer_id: int,
        payload: schemas.PayrollRunCreate,
    ) -> models.PayrollRun:
        run = models.PayrollRun(issuer_id=issuer_id, period_label=payload.period_label)
        total = Decimal("0")
        for worker_id, days in payload.days.items():
            worker = (
                self.db.query(models.Worker)
                .filter(models.Worker.id == worker_id)
                .one_or_none()
            )
            if not worker:
                logger.warning("Worker %s not found", worker_id)
                continue
            gross = worker.daily_rate * days
            rec = models.PayrollRecord(
                worker_id=worker.id,
                days_worked=days,
                gross_pay=gross,
                net_pay=gross,  # deductions later
            )
            run.records.append(rec)
            total += gross
        run.total_gross = total
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run


def get_payroll_service(db: Annotated[Session, Depends(get_db)]) -> PayrollService:  # type: ignore[override]
    return PayrollService(db)
