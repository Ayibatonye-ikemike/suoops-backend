"""Remove BUSINESS plan - focus on small/medium businesses only

Revision ID: 20251224_remove_business
Revises: 20251221_add_cit
Create Date: 2024-12-24

Changes:
- Downgrade any BUSINESS plan users to PRO
- BUSINESS plan features (voice, OCR, API) now available on PRO
- Target market: businesses under ₦100M annual revenue
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251224_remove_business'
down_revision = '20251221_add_cit'
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: Update any users on BUSINESS plan to PRO
    # The BUSINESS enum value will remain in PostgreSQL but won't be used
    op.execute("""
        UPDATE "user"
        SET plan = 'pro'
        WHERE plan = 'business'
    """)
    
    # Note: We don't remove the enum value from PostgreSQL
    # because it requires recreating the column which is risky
    # The application code will simply not use 'business' anymore


def downgrade():
    # No downgrade - users stay on PRO which is equivalent or better
    pass
