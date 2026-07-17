"""Add auth0_sub to tenants for Auth0 user linkage."""

import sqlalchemy as sa

from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("auth0_sub", sa.Text(), nullable=True))
    op.create_index(
        "idx_tenants_auth0_sub_unique",
        "tenants",
        ["auth0_sub"],
        unique=True,
        postgresql_where=sa.text("auth0_sub IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_tenants_auth0_sub_unique", table_name="tenants")
    op.drop_column("tenants", "auth0_sub")
