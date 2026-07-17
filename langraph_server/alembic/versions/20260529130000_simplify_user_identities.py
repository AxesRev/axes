"""simplify_user_identities_add_tenant_fk

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-05-29 13:00:00.000000

``user_identities`` holds Slack users scoped to a tenant only:

* ``id``
* ``slack_user_id``
* ``tenant_id`` → ``tenants.id``

Removes GitHub and timestamp columns previously stored on this table.
Existing rows are assigned to a default tenant created for backfill.
"""

import sqlalchemy as sa

from alembic import op

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None

_DEFAULT_TENANT_ID = "00000000-0000-4000-8000-000000000001"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO tenants (id, name)
            VALUES (:id, :name)
            ON CONFLICT (id) DO NOTHING
            """
        ).bindparams(id=_DEFAULT_TENANT_ID, name="Default")
    )

    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_user_identities_updated_at ON user_identities"))

    op.execute(sa.text("DROP INDEX IF EXISTS idx_user_identities_github_installation_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_user_identities_github_user_id"))
    op.drop_constraint("uq_user_identities_slack_user_id", "user_identities", type_="unique")
    op.drop_index("idx_user_identities_slack_user_id", table_name="user_identities")

    op.add_column("user_identities", sa.Column("tenant_id", sa.Text(), nullable=True))
    op.execute(sa.text("UPDATE user_identities SET tenant_id = :tenant_id").bindparams(tenant_id=_DEFAULT_TENANT_ID))
    op.alter_column("user_identities", "tenant_id", nullable=False)

    op.drop_column("user_identities", "github_installation_id")
    op.drop_column("user_identities", "github_username")
    op.drop_column("user_identities", "github_user_id")
    op.drop_column("user_identities", "created_at")
    op.drop_column("user_identities", "updated_at")

    op.execute(sa.text("DELETE FROM user_identities WHERE slack_user_id IS NULL"))
    op.alter_column("user_identities", "slack_user_id", nullable=False)

    op.create_foreign_key(
        "fk_user_identities_tenant_id",
        "user_identities",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "idx_user_identities_slack_user_id",
        "user_identities",
        ["slack_user_id"],
        unique=True,
    )
    op.create_index(
        "idx_user_identities_tenant_id",
        "user_identities",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_user_identities_tenant_id", table_name="user_identities")
    op.drop_index("idx_user_identities_slack_user_id", table_name="user_identities")
    op.drop_constraint("fk_user_identities_tenant_id", "user_identities", type_="foreignkey")

    op.add_column(
        "user_identities",
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "user_identities",
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column("user_identities", sa.Column("github_user_id", sa.Text(), nullable=True))
    op.add_column("user_identities", sa.Column("github_username", sa.Text(), nullable=True))
    op.add_column("user_identities", sa.Column("github_installation_id", sa.Text(), nullable=True))

    op.alter_column("user_identities", "slack_user_id", nullable=True)
    op.drop_column("user_identities", "tenant_id")

    op.create_index(
        "idx_user_identities_slack_user_id",
        "user_identities",
        ["slack_user_id"],
        unique=True,
    )
    op.create_unique_constraint("uq_user_identities_slack_user_id", "user_identities", ["slack_user_id"])
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

    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_user_identities_updated_at
            BEFORE UPDATE ON user_identities
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
            """
        )
    )

    op.execute(sa.text("DELETE FROM tenants WHERE id = :id").bindparams(id=_DEFAULT_TENANT_ID))
