"""Add trigram GIN indexes for substring search on doc_embedding_chunks.

Revision ID: 20260904220000
Revises: 20260815180000
Create Date: 2026-09-04 22:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260904220000"
down_revision: str | Sequence[str] | None = "20260815180000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_doc_embedding_chunks_content_trgm "
            "ON doc_embedding_chunks USING gin (content gin_trgm_ops)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_doc_embedding_chunks_page_title_trgm "
            "ON doc_embedding_chunks USING gin (page_title gin_trgm_ops)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_doc_embedding_chunks_page_title_trgm"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_doc_embedding_chunks_content_trgm"))
