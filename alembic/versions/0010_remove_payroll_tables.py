"""Remove legacy payroll tables

Revision ID: 0010_remove_payroll
Revises: 0009_add_customer_email
Create Date: 2025-10-23
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0010_remove_payroll"
down_revision = "0009_add_customer_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use IF EXISTS to avoid errors if cleanup already happened manually.
    op.execute("DROP TABLE IF EXISTS payrollrecord CASCADE")
    op.execute("DROP TABLE IF EXISTS payrollrun CASCADE")
    op.execute("DROP TABLE IF EXISTS worker CASCADE")


def downgrade() -> None:
    # Recreate minimal schema for downgrade fidelity.
    op.execute(
        """
        CREATE TABLE worker (
            id SERIAL PRIMARY KEY,
            issuer_id INTEGER NOT NULL,
            name VARCHAR NOT NULL,
            daily_rate NUMERIC(10, 2) NOT NULL,
            active BOOLEAN DEFAULT TRUE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE payrollrun (
            id SERIAL PRIMARY KEY,
            issuer_id INTEGER NOT NULL,
            period_label VARCHAR NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE,
            total_gross NUMERIC(10, 2) DEFAULT 0
        )
        """
    )
    op.execute(
        """
        CREATE TABLE payrollrecord (
            id SERIAL PRIMARY KEY,
            run_id INTEGER REFERENCES payrollrun(id),
            worker_id INTEGER NOT NULL,
            days_worked INTEGER DEFAULT 0,
            gross_pay NUMERIC(10, 2),
            net_pay NUMERIC(10, 2)
        )
        """
    )
