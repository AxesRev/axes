"""Move Paddle billing state off tenants onto billing_accounts.

Revision ID: 20260815180000
Revises: 20260711180000
Create Date: 2026-08-15 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260815180000"
down_revision: str | Sequence[str] | None = "20260711180000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "billing_accounts",
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("paddle_customer_id", sa.Text(), nullable=True),
        sa.Column("paddle_subscription_id", sa.Text(), nullable=True),
        sa.Column("paddle_subscription_status", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id"),
    )
    op.create_index(
        "idx_billing_accounts_paddle_subscription_id",
        "billing_accounts",
        ["paddle_subscription_id"],
    )
    op.drop_column("tenants", "paddle_subscription_status")
    op.drop_column("tenants", "paddle_subscription_id")
    op.drop_column("tenants", "paddle_customer_id")


def downgrade() -> None:
    op.add_column("tenants", sa.Column("paddle_customer_id", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("paddle_subscription_id", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("paddle_subscription_status", sa.Text(), nullable=True))
    op.drop_index("idx_billing_accounts_paddle_subscription_id", table_name="billing_accounts")
    op.drop_table("billing_accounts")
