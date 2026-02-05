"""Add Paystack subscription fields to User model.

Supports auto-recurring Paystack subscriptions for Pro/Business plans.

Revision ID: 20260205_paystack_subscription
Revises: add_payout_bank_fields
Create Date: 2026-02-05
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260205_paystack_subscription'
down_revision = 'add_payout_bank_fields'  # Update this to your latest migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add Paystack subscription tracking fields
    op.add_column(
        'users',
        sa.Column('paystack_subscription_code', sa.String(100), nullable=True)
    )
    op.add_column(
        'users',
        sa.Column('paystack_customer_code', sa.String(100), nullable=True)
    )
    
    # Index for efficient subscription lookup
    op.create_index(
        'ix_users_paystack_subscription_code',
        'users',
        ['paystack_subscription_code'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_users_paystack_subscription_code', table_name='users')
    op.drop_column('users', 'paystack_customer_code')
    op.drop_column('users', 'paystack_subscription_code')
