from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Customer(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None]
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    invoices: Mapped[list[Invoice]] = relationship("Invoice", back_populates="customer")  # type: ignore


class Invoice(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    issuer_id: Mapped[int]
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"))  # type: ignore
    amount: Mapped[Decimal] = mapped_column(Numeric(scale=2))
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(scale=2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    due_date: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )
    payment_ref: Mapped[str | None]
    payment_url: Mapped[str | None]
    pdf_url: Mapped[str | None]
    customer: Mapped[Customer] = relationship("Customer", back_populates="invoices")  # type: ignore
    lines: Mapped[list[InvoiceLine]] = relationship(
        "InvoiceLine",
        back_populates="invoice",
        cascade="all, delete-orphan",
    )  # type: ignore


class InvoiceLine(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoice.id"))  # type: ignore
    description: Mapped[str]
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(scale=2))
    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="lines")  # type: ignore


class Worker(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    issuer_id: Mapped[int]
    name: Mapped[str]
    daily_rate: Mapped[Decimal] = mapped_column(Numeric(scale=2))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class PayrollRun(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    issuer_id: Mapped[int]
    period_label: Mapped[str]
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )
    total_gross: Mapped[Decimal] = mapped_column(Numeric(scale=2), default=Decimal("0"))
    records: Mapped[list[PayrollRecord]] = relationship(
        "PayrollRecord",
        back_populates="run",
        cascade="all, delete-orphan",
    )  # type: ignore


class PayrollRecord(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("payrollrun.id"))  # type: ignore
    worker_id: Mapped[int]
    days_worked: Mapped[int] = mapped_column(Integer, default=0)
    gross_pay: Mapped[Decimal] = mapped_column(Numeric(scale=2))
    net_pay: Mapped[Decimal] = mapped_column(Numeric(scale=2))
    run: Mapped[PayrollRun] = relationship("PayrollRun", back_populates="records")  # type: ignore


class User(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str]
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )


class WebhookEvent(Base):
    """Idempotency record for processed webhooks.

    Unique constraint on (provider, external_id) prevents duplicate processing.
    """

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    external_id: Mapped[str] = mapped_column(String(120))
    signature: Mapped[str | None]
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )
