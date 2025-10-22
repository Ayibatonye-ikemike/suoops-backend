"""Make timestamps timezone aware

Revision ID: 0004_tz_aware
Revises: 0003_add_webhook_event
Create Date: 2025-10-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_tz_aware"
down_revision = "0003_add_webhook_event"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "invoice",
        "created_at",
        type_=sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
        existing_nullable=False,
    )
    op.alter_column(
        "invoice",
        "due_date",
        type_=sa.DateTime(timezone=True),
        postgresql_using="due_date AT TIME ZONE 'UTC'",
        existing_nullable=True,
    )
    op.alter_column(
        "payrollrun",
        "created_at",
        type_=sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
        existing_nullable=False,
    )
    op.alter_column(
        "user",
        "created_at",
        type_=sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
        existing_nullable=False,
    )
    op.alter_column(
        "webhookevent",
        "created_at",
        type_=sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "webhookevent",
        "created_at",
        type_=sa.DateTime(timezone=False),
        server_default=None,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
        existing_nullable=False,
    )
    op.alter_column(
        "user",
        "created_at",
        type_=sa.DateTime(timezone=False),
        server_default=None,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
        existing_nullable=False,
    )
    op.alter_column(
        "payrollrun",
        "created_at",
        type_=sa.DateTime(timezone=False),
        server_default=None,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
        existing_nullable=False,
    )
    op.alter_column(
        "invoice",
        "due_date",
        type_=sa.DateTime(timezone=False),
        postgresql_using="due_date AT TIME ZONE 'UTC'",
        existing_nullable=True,
    )
    op.alter_column(
        "invoice",
        "created_at",
        type_=sa.DateTime(timezone=False),
        server_default=None,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
        existing_nullable=False,
    )
