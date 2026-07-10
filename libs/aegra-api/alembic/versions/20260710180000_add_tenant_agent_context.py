"""add_tenant_agent_context

Revision ID: 20260710180000
Revises: 20260605180000
Create Date: 2026-07-10 18:00:00.000000

Creates ``tenant_agent_context`` for per-tenant editable agent configuration text.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260710180000"
down_revision: str | Sequence[str] | None = "20260605180000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_agent_context",
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id"),
    )


def downgrade() -> None:
    op.drop_table("tenant_agent_context")
