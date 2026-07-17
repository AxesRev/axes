"""GitHub documentation embedding and ingestion."""

from __future__ import annotations

from app_integrations.github.doc_generation.zip_embedder import (
    ingest_github_documentation_from_zip,
    iter_github_docs_zip_markdown_members,
    split_github_docs_zip_markdown_into_chunks,
)

__all__ = [
    "ingest_github_documentation_from_zip",
    "iter_github_docs_zip_markdown_members",
    "split_github_docs_zip_markdown_into_chunks",
]
