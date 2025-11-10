"""add user role column

Revision ID: 20251110_03
Revises: 20251110_02
Create Date: 2025-11-10 10:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251110_03'
down_revision = '20251110_02'
branch_labels = None
depends_on = None


def upgrade():
    # Add role column with default value 'user'
    op.add_column('user', sa.Column('role', sa.String(length=20), server_default='user', nullable=False))
    op.create_index(op.f('ix_user_role'), 'user', ['role'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_user_role'), table_name='user')
    op.drop_column('user', 'role')
