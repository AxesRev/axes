"""restore_oauth_states

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-05-29 21:00:00.000000

Restores ``oauth_states`` for Slack → GitHub OAuth identity linking.
"""

import sqlalchemy as sa

from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_states",
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("slack_user_id", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("token"),
    )
    op.create_index(
        "idx_oauth_states_slack_user_id",
        "oauth_states",
        ["slack_user_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_oauth_states_slack_user_id", table_name="oauth_states")
    op.drop_table("oauth_states")
