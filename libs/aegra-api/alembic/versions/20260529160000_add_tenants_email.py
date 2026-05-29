"""add_tenants_email

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-29 16:00:00.000000

Adds ``email`` to ``tenants``.
"""

import sqlalchemy as sa

from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("email", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "email")
