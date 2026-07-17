"""add_app_integrations_table

Revision ID: a1b2c3d4e5f6
Revises: f2a3b4c5d6e7
Create Date: 2026-05-29 14:00:00.000000

Creates ``app_integrations`` for tenant-scoped integration configuration.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_integrations",
        sa.Column(
            "id",
            sa.Text(),
            server_default=sa.text("public.uuid_generate_v4()::text"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_app_integrations_tenant_id",
        "app_integrations",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_app_integrations_tenant_id", table_name="app_integrations")
    op.drop_table("app_integrations")
