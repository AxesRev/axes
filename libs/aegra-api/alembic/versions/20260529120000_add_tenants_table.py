"""add_tenants_table

Revision ID: e1f2a3b4c5d6
Revises: a9c8e7f6d5b4
Create Date: 2026-05-29 12:00:00.000000

Creates ``tenants`` for top-level organisational boundaries.
"""

import sqlalchemy as sa

from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "a9c8e7f6d5b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column(
            "id",
            sa.Text(),
            server_default=sa.text("public.uuid_generate_v4()::text"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("tenants")
