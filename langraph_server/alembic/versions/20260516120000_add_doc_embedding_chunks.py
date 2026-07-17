"""add_doc_embedding_chunks_pgvector

Revision ID: f4a8c1e2d0b3
Revises: c7d4e2f3b1a8
Create Date: 2026-05-16 12:00:00.000000

Stores crawled documentation chunks with pgvector embeddings for RAG / semantic search.
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "f4a8c1e2d0b3"
down_revision = "c7d4e2f3b1a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    op.create_table(
        "doc_embedding_chunks",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("collection_key", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("page_title", sa.Text(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
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
    op.create_index(
        "uq_doc_embedding_chunks_natural_key",
        "doc_embedding_chunks",
        ["collection_key", "source_url", "chunk_index"],
        unique=True,
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_doc_embedding_chunks_embedding_hnsw "
            "ON doc_embedding_chunks USING hnsw (embedding vector_cosine_ops)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_doc_embedding_chunks_embedding_hnsw"))
    op.drop_index("uq_doc_embedding_chunks_natural_key", table_name="doc_embedding_chunks")
    op.drop_index("idx_doc_embedding_chunks_source_url", table_name="doc_embedding_chunks")
    op.drop_index("idx_doc_embedding_chunks_collection", table_name="doc_embedding_chunks")
    op.drop_table("doc_embedding_chunks")
