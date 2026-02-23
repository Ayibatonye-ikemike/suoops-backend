"""Add preferred_currency column to users table

Stores the user's display currency preference (NGN or USD).
Used by the WhatsApp bot and synced with the frontend toggle.

Revision ID: user_currency_pref_20260223
Revises: user_pro_override_20260220
Create Date: 2026-02-23
"""
import sqlalchemy as sa
from alembic import op

revision = "user_currency_pref_20260223"
down_revision = "user_pro_override_20260220"


def upgrade():
    op.add_column(
        "user",
        sa.Column(
            "preferred_currency",
            sa.String(3),
            server_default="NGN",
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("user", "preferred_currency")
