"""add_app_integrations_app_name

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-29 15:00:00.000000

Adds ``app_name`` to ``app_integrations``.
"""

import sqlalchemy as sa

from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_integrations", sa.Column("app_name", sa.Text(), nullable=False))


def downgrade() -> None:
    op.drop_column("app_integrations", "app_name")
