"""Add invoice_balance column to user table.

NEW BILLING MODEL:
- Users purchase invoice packs (100 invoices = ₦2,500)
- invoice_balance tracks available invoices
- Decremented on revenue invoice creation
- Default 5 for new users (free starter pack)

Revision ID: 20251219_add_invoice_balance
Revises: 20251218_whatsapp_optin
Create Date: 2025-12-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20251219_add_invoice_balance'
down_revision: Union[str, None] = '20251218_whatsapp_optin'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add invoice_balance column with default 5 (free starter invoices)
    op.add_column(
        'user',
        sa.Column('invoice_balance', sa.Integer(), nullable=False, server_default='5')
    )
    
    # Migrate existing users: give them invoices based on their current plan
    # - FREE users: 5 invoices
    # - STARTER: 100 invoices (equivalent to 1 pack)
    # - PRO: 200 invoices (equivalent to 2 packs)
    # - BUSINESS: 300 invoices (equivalent to 3 packs)
    op.execute("""
        UPDATE "user" SET invoice_balance = CASE
            WHEN plan = 'free' THEN 5
            WHEN plan = 'starter' THEN 100
            WHEN plan = 'pro' THEN 200
            WHEN plan = 'business' THEN 300
            ELSE 5
        END
    """)


def downgrade() -> None:
    op.drop_column('user', 'invoice_balance')
