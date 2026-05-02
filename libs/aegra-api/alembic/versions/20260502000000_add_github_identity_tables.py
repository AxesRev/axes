"""add_github_identity_tables

Revision ID: a3f9b2c1d4e7
Revises: d042a0ca1cb5
Create Date: 2026-05-02 00:00:00.000000

Creates the tables required for Slack → GitHub identity linking:

* ``user_identities`` – persists the verified Slack user ↔ GitHub user mapping.
* ``oauth_states``     – short-lived tokens used to initiate the GitHub OAuth flow
                         from a Slack message.

A trigger on ``user_identities`` automatically keeps ``updated_at`` in sync
with the current timestamp on every UPDATE.
"""

import sqlalchemy as sa

from alembic import op

revision = "a3f9b2c1d4e7"
down_revision = "d042a0ca1cb5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_identities",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("slack_user_id", sa.Text(), nullable=False),
        sa.Column("github_user_id", sa.Text(), nullable=True),
        sa.Column("github_username", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slack_user_id", name="uq_user_identities_slack_user_id"),
    )
    op.create_index(
        "idx_user_identities_slack_user_id",
        "user_identities",
        ["slack_user_id"],
        unique=True,
    )

    # Trigger to auto-refresh updated_at on every UPDATE
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION set_updated_at()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = now();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_user_identities_updated_at
            BEFORE UPDATE ON user_identities
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
            """
        )
    )

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
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_user_identities_updated_at ON user_identities"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS set_updated_at"))
    op.drop_index("idx_oauth_states_slack_user_id", table_name="oauth_states")
    op.drop_table("oauth_states")
    op.drop_index("idx_user_identities_slack_user_id", table_name="user_identities")
    op.drop_table("user_identities")
