"""add_subscription_plans

Revision ID: 0005
Revises: 0004
Create Date: 2025-10-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum type for subscription plans
    op.execute("""
        CREATE TYPE subscriptionplan AS ENUM (
            'free', 'starter', 'pro', 'business', 'enterprise'
        )
    """)
    
    # Add plan column with default 'free'
    op.add_column('user', sa.Column(
        'plan',
        sa.Enum('free', 'starter', 'pro', 'business', 'enterprise', name='subscriptionplan'),
        nullable=False,
        server_default='free'
    ))
    
    # Add invoice usage tracking column
    op.add_column('user', sa.Column(
        'invoices_this_month',
        sa.Integer(),
        nullable=False,
        server_default='0'
    ))
    
    # Add usage reset timestamp column
    op.add_column('user', sa.Column(
        'usage_reset_at',
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text('now()')
    ))


def downgrade() -> None:
    # Remove columns
    op.drop_column('user', 'usage_reset_at')
    op.drop_column('user', 'invoices_this_month')
    op.drop_column('user', 'plan')
    
    # Drop enum type
    op.execute("DROP TYPE subscriptionplan")
