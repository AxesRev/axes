"""Salesforce documentation embedding and ingestion."""

from __future__ import annotations

from app_integrations.salesforce.doc_generation.pdf_embedder import (
    build_pdf_sections,
    chunk_pdf_sections,
    detect_running_headers,
    extract_pdf_pages,
    split_salesforce_pdf_into_chunks,
    split_salesforce_pdf_pages_into_chunks,
)

__all__ = [
    "build_pdf_sections",
    "chunk_pdf_sections",
    "detect_running_headers",
    "extract_pdf_pages",
    "split_salesforce_pdf_into_chunks",
    "split_salesforce_pdf_pages_into_chunks",
]
