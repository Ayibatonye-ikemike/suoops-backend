"""Replace Paystack credentials with bank account details

Revision ID: 0007
Revises: 0006
Create Date: 2025-10-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade():
    """Replace Paystack API keys with bank account details.
    
    New model: Businesses provide their bank account, customers pay via bank transfer,
    businesses manually confirm payment, system sends receipt.
    
    Changes:
    - Remove: paystack_secret_key, paystack_public_key (from user table)
    - Remove: payment_ref, payment_url (from invoice table)
    - Remove: webhookevent table (no longer needed)
    - Add: account_name (to user table)
    """
    # Drop Paystack API key columns from user table
    op.drop_column('user', 'paystack_secret_key')
    op.drop_column('user', 'paystack_public_key')
    
    # Add account_name column to user table
    op.add_column('user', sa.Column('account_name', sa.String(255), nullable=True))
    
    # Drop payment columns from invoice table
    op.drop_column('invoice', 'payment_ref')
    op.drop_column('invoice', 'payment_url')
    
    # Drop webhookevent table (no longer needed without payment platforms)
    op.drop_table('webhookevent')


def downgrade():
    """Revert to Paystack integration model."""
    # Recreate webhookevent table
    op.create_table(
        'webhookevent',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(40), nullable=False),
        sa.Column('external_id', sa.String(120), nullable=False),
        sa.Column('signature', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_webhookevent_provider'), 'webhookevent', ['provider'])
    
    # Add back payment columns to invoice table
    op.add_column('invoice', sa.Column('payment_ref', sa.String(), nullable=True))
    op.add_column('invoice', sa.Column('payment_url', sa.String(), nullable=True))
    
    # Add back Paystack columns to user table
    op.add_column('user', sa.Column('paystack_secret_key', sa.String(255), nullable=True))
    op.add_column('user', sa.Column('paystack_public_key', sa.String(255), nullable=True))
    
    # Drop account_name column
    op.drop_column('user', 'account_name')
