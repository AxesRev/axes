"""add_github_installation_id

Revision ID: b8e3c1f2a5d9
Revises: a3f9b2c1d4e7
Create Date: 2026-05-15 00:00:00.000000

Adds ``github_installation_id`` to ``user_identities`` so that the GitHub
App installation callback can persist the installation associated with each
Slack user.
"""

import sqlalchemy as sa

from alembic import op

revision = "b8e3c1f2a5d9"
down_revision = "a3f9b2c1d4e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_identities",
        sa.Column("github_installation_id", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_identities", "github_installation_id")
