"""doc_embedding_chunks_application

Revision ID: a9c8e7f6d5b4
Revises: f4a8c1e2d0b3
Create Date: 2026-05-22 12:00:00.000000

Adds ``application`` to partition doc chunks by product/integration; extends unique key and indexes.
"""

import sqlalchemy as sa

from alembic import op

revision: str = "a9c8e7f6d5b4"
down_revision: str | None = "f4a8c1e2d0b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "doc_embedding_chunks",
        sa.Column("application", sa.Text(), nullable=False, server_default=sa.text("''")),
    )
    op.alter_column("doc_embedding_chunks", "application", server_default=None)

    op.drop_index("uq_doc_embedding_chunks_natural_key", table_name="doc_embedding_chunks")
    op.drop_index("idx_doc_embedding_chunks_collection", table_name="doc_embedding_chunks")
    op.drop_index("idx_doc_embedding_chunks_source_url", table_name="doc_embedding_chunks")

    op.create_index(
        "uq_doc_embedding_chunks_natural_key",
        "doc_embedding_chunks",
        ["application", "collection_key", "source_url", "chunk_index"],
        unique=True,
    )
    op.create_index(
        "idx_doc_embedding_chunks_app_collection",
        "doc_embedding_chunks",
        ["application", "collection_key"],
        unique=False,
    )
    op.create_index(
        "idx_doc_embedding_chunks_app_collection_url",
        "doc_embedding_chunks",
        ["application", "collection_key", "source_url"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_doc_embedding_chunks_app_collection_url", table_name="doc_embedding_chunks")
    op.drop_index("idx_doc_embedding_chunks_app_collection", table_name="doc_embedding_chunks")
    op.drop_index("uq_doc_embedding_chunks_natural_key", table_name="doc_embedding_chunks")

    op.create_index(
        "uq_doc_embedding_chunks_natural_key",
        "doc_embedding_chunks",
        ["collection_key", "source_url", "chunk_index"],
        unique=True,
    )
    op.create_index(
        "idx_doc_embedding_chunks_collection",
        "doc_embedding_chunks",
        ["collection_key"],
        unique=False,
    )
    op.create_index(
        "idx_doc_embedding_chunks_source_url",
        "doc_embedding_chunks",
        ["collection_key", "source_url"],
        unique=False,
    )
    op.drop_column("doc_embedding_chunks", "application")
