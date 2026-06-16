"""Repair missing referral_code.commission_perpetual_pct column.

Some environments have app code that expects `commission_perpetual_pct`
but the database schema is missing the column. This migration is idempotent
and safely adds the column only when absent.

Revision ID: fix_missing_commission_perpetual_pct_20260616
Revises: db_scaling_fixes_20260614
Create Date: 2026-06-16
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fix_missing_commission_perpetual_pct_20260616"
down_revision: Union[str, None] = "db_scaling_fixes_20260614"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres-compatible idempotent repair for missing column.
    op.execute(
        """
        ALTER TABLE referral_code
        ADD COLUMN IF NOT EXISTS commission_perpetual_pct INTEGER
        """
    )
    op.execute(
        """
        UPDATE referral_code
        SET commission_perpetual_pct = 5
        WHERE commission_perpetual_pct IS NULL
        """
    )
    op.execute(
        """
        ALTER TABLE referral_code
        ALTER COLUMN commission_perpetual_pct SET DEFAULT 5
        """
    )
    op.execute(
        """
        ALTER TABLE referral_code
        ALTER COLUMN commission_perpetual_pct SET NOT NULL
        """
    )


def downgrade() -> None:
    # Keep downgrade simple/safe.
    op.execute(
        """
        ALTER TABLE referral_code
        DROP COLUMN IF EXISTS commission_perpetual_pct
        """
    )
