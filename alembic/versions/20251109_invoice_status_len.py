from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20251109_invoice_status_len"
down_revision = "20251107_tax_profile_verify"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Increase status column length from VARCHAR(20) to VARCHAR(30)
    # to accommodate 'awaiting_confirmation' (22 chars)
    op.alter_column(
        "invoice",
        "status",
        type_=sa.String(30),
        existing_type=sa.String(20),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "invoice",
        "status",
        type_=sa.String(20),
        existing_type=sa.String(30),
        existing_nullable=False,
    )
