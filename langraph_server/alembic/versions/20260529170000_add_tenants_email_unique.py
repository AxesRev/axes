"""Unique email constraint for tenant lookup by Auth0 user."""

import sqlalchemy as sa

from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE tenants
            SET email = lower(trim(email))
            WHERE email IS NOT NULL
            """
        )
    )
    op.create_index(
        "idx_tenants_email_unique",
        "tenants",
        ["email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_tenants_email_unique", table_name="tenants")
