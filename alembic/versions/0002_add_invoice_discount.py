from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_add_invoice_discount"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoice", sa.Column("discount_amount", sa.Numeric(scale=2), nullable=True))


def downgrade() -> None:
    op.drop_column("invoice", "discount_amount")
