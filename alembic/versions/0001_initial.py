from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=True),
    )
    op.create_table(
        "invoice",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.String(length=40), nullable=False, unique=True),
        sa.Column("issuer_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customer.id")),
        sa.Column("amount", sa.Numeric(scale=2), nullable=False),
        sa.Column("status", sa.String(length=20), default="pending"),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("payment_ref", sa.String(), nullable=True),
        sa.Column("pdf_url", sa.String(), nullable=True),
    )
    op.create_index("ix_invoice_invoice_id", "invoice", ["invoice_id"], unique=True)
    op.create_table(
        "invoiceline",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoice.id")),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), default=1),
        sa.Column("unit_price", sa.Numeric(scale=2)),
    )
    op.create_table(
        "worker",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("issuer_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("daily_rate", sa.Numeric(scale=2), nullable=False),
        sa.Column("active", sa.Boolean(), default=True),
    )
    op.create_table(
        "payrollrun",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("issuer_id", sa.Integer(), nullable=False),
        sa.Column("period_label", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("total_gross", sa.Numeric(scale=2), default=0),
    )
    op.create_table(
        "payrollrecord",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("payrollrun.id")),
        sa.Column("worker_id", sa.Integer(), nullable=False),
        sa.Column("days_worked", sa.Integer(), default=0),
        sa.Column("gross_pay", sa.Numeric(scale=2)),
        sa.Column("net_pay", sa.Numeric(scale=2)),
    )
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("phone", sa.String(length=32), nullable=False, unique=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_user_phone", "user", ["phone"], unique=True)


def downgrade() -> None:
    op.drop_table("payrollrecord")
    op.drop_table("payrollrun")
    op.drop_table("worker")
    op.drop_table("invoiceline")
    op.drop_index("ix_invoice_invoice_id", table_name="invoice")
    op.drop_table("invoice")
    op.drop_table("customer")
    op.drop_index("ix_user_phone", table_name="user")
    op.drop_table("user")
