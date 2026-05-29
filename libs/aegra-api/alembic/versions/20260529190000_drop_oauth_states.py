"""drop_oauth_states

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-29 19:00:00.000000

Removes the ``oauth_states`` table used by the retired Slack → GitHub OAuth
identity-linking flow.
"""

from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_oauth_states_slack_user_id", table_name="oauth_states")
    op.drop_table("oauth_states")


def downgrade() -> None:
    import sqlalchemy as sa

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
