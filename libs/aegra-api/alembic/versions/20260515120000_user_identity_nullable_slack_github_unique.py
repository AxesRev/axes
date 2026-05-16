"""user_identity_nullable_slack_github_unique

Revision ID: c7d4e2f3b1a8
Revises: b8e3c1f2a5d9
Create Date: 2026-05-15 12:00:00.000000

Decouples the ``user_identities`` table from Slack so that a row can be
created from a GitHub App installation alone:

* Makes ``slack_user_id`` nullable — a row no longer requires a Slack user.
* Adds a unique index on ``github_user_id`` so it can serve as the identity
  key for install-only users (Postgres allows multiple NULLs in a unique
  index, so this only enforces uniqueness among non-null values).
"""

from alembic import op

revision = "c7d4e2f3b1a8"
down_revision = "b8e3c1f2a5d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("user_identities", "slack_user_id", nullable=True)
    op.create_index(
        "idx_user_identities_github_user_id",
        "user_identities",
        ["github_user_id"],
        unique=True,
    )
    op.create_index(
        "idx_user_identities_github_installation_id",
        "user_identities",
        ["github_installation_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_user_identities_github_installation_id", table_name="user_identities")
    op.drop_index("idx_user_identities_github_user_id", table_name="user_identities")
    op.alter_column("user_identities", "slack_user_id", nullable=False)
