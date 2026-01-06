"""add payout bank fields to user

Revision ID: add_payout_bank_fields
Revises: 
Create Date: 2026-01-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_payout_bank_fields'
down_revision: Union[str, None] = None  # Update this to your latest migration
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add payout bank fields for referral commissions."""
    op.add_column('user', sa.Column('payout_bank_name', sa.String(100), nullable=True))
    op.add_column('user', sa.Column('payout_account_number', sa.String(20), nullable=True))
    op.add_column('user', sa.Column('payout_account_name', sa.String(255), nullable=True))


def downgrade() -> None:
    """Remove payout bank fields."""
    op.drop_column('user', 'payout_account_name')
    op.drop_column('user', 'payout_account_number')
    op.drop_column('user', 'payout_bank_name')
