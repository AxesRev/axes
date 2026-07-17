"""Add Paddle billing reference IDs to tenants

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-06-05 14:00:00.000000

Stores opaque Paddle customer/subscription IDs per tenant. Card data stays at Paddle.
"""

import sqlalchemy as sa

from alembic import op

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("paddle_customer_id", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("paddle_subscription_id", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "paddle_subscription_id")
    op.drop_column("tenants", "paddle_customer_id")
