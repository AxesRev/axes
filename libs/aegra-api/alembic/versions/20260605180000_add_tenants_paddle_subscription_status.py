"""Add paddle_subscription_status to tenants.

Revision ID: 20260605180000
Revises: d5e6f7a8b9c0
Create Date: 2026-06-05 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260605180000"
down_revision: str | Sequence[str] | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("paddle_subscription_status", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "paddle_subscription_status")
