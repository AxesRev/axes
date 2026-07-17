"""drop_doc_embedding_chunk_source_url

Revision ID: 20260711180000
Revises: 20260710180000
Create Date: 2026-07-11 18:00:00.000000

Remove unused ``source_url`` and ``chunk_index`` from ``doc_embedding_chunks``.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260711180000"
down_revision: str | Sequence[str] | None = "20260710180000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("idx_doc_embedding_chunks_app_collection_url", table_name="doc_embedding_chunks")
    op.drop_index("uq_doc_embedding_chunks_natural_key", table_name="doc_embedding_chunks")
    op.drop_column("doc_embedding_chunks", "chunk_index")
    op.drop_column("doc_embedding_chunks", "source_url")


def downgrade() -> None:
    import sqlalchemy as sa

    op.add_column("doc_embedding_chunks", sa.Column("source_url", sa.Text(), nullable=False, server_default=""))
    op.add_column("doc_embedding_chunks", sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"))
    op.alter_column("doc_embedding_chunks", "source_url", server_default=None)
    op.alter_column("doc_embedding_chunks", "chunk_index", server_default=None)
    op.create_index(
        "uq_doc_embedding_chunks_natural_key",
        "doc_embedding_chunks",
        ["application", "collection_key", "source_url", "chunk_index"],
        unique=True,
    )
    op.create_index(
        "idx_doc_embedding_chunks_app_collection_url",
        "doc_embedding_chunks",
        ["application", "collection_key", "source_url"],
        unique=False,
    )
