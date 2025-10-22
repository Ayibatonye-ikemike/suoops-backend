"""add_paystack_credentials

Revision ID: 0006
Revises: 0005
Create Date: 2025-10-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add Paystack API credentials (business's own keys)
    op.add_column('user', sa.Column(
        'paystack_secret_key',
        sa.String(255),
        nullable=True
    ))
    
    op.add_column('user', sa.Column(
        'paystack_public_key',
        sa.String(255),
        nullable=True
    ))
    
    # Add business bank account info (for reference/display)
    op.add_column('user', sa.Column(
        'business_name',
        sa.String(255),
        nullable=True
    ))
    
    op.add_column('user', sa.Column(
        'bank_name',
        sa.String(100),
        nullable=True
    ))
    
    op.add_column('user', sa.Column(
        'account_number',
        sa.String(20),
        nullable=True
    ))


def downgrade() -> None:
    op.drop_column('user', 'account_number')
    op.drop_column('user', 'bank_name')
    op.drop_column('user', 'business_name')
    op.drop_column('user', 'paystack_public_key')
    op.drop_column('user', 'paystack_secret_key')
