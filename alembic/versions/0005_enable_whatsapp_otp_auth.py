"""Switch authentication to WhatsApp OTP

Revision ID: 0005_enable_whatsapp_otp_auth
Revises: 0004_tz_aware
Create Date: 2025-10-28 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0005_enable_whatsapp_otp_auth"
down_revision = "0004_tz_aware"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("hashed_password")
        batch_op.add_column(
            sa.Column(
                "phone_verified",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "last_login",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("last_login")
        batch_op.drop_column("phone_verified")
        batch_op.add_column(sa.Column("hashed_password", sa.String(), nullable=True))