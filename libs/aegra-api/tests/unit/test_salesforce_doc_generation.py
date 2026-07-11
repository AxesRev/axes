"""Unit tests for Salesforce PDF documentation extraction, chunking, and ingest."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pymupdf
import pytest

from aegra_api.settings import settings
from app_integrations.salesforce.constants import SALESFORCE_APP_NAME
from app_integrations.salesforce.doc_generation import pdf_embedder as salesforce_pdf_embedder_module
from app_integrations.salesforce.doc_generation.pdf_embedder import (
    PdfLine,
    SalesforcePdfChunk,
    SalesforcePdfPageText,
    _sanitize_metadata_for_postgres,
    _sanitize_text_for_postgres,
    build_pdf_sections,
    chunk_pdf_sections,
    extract_page_lines,
    extract_page_text,
    extract_pdf_pages,
    ingest_salesforce_documentation_from_pdf,
    is_toc_page,
    split_salesforce_pdf_into_chunks,
    split_salesforce_pdf_pages_into_chunks,
)


def _write_sample_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "CHAPTER 1", fontsize=21)
    page.insert_text((72, 110), "Introduction to REST API", fontsize=11)
    page.insert_text(
        (72, 150),
        "REST API provides programmatic access to your data in Salesforce.",
        fontsize=10,
    )
    document.save(path)
    document.close()


def _write_multi_section_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "About REST API", fontsize=11)
    page.insert_text((72, 100), "REST API is one of several web interfaces for Salesforce data.", fontsize=10)
    page.insert_text((72, 180), "Release Notes", fontsize=11)
    page.insert_text((72, 210), "Use the Salesforce Release Notes to learn about updates.", fontsize=10)
    document.save(path)
    document.close()


def _write_json_section_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Get a List of Objects", fontsize=11)
    page.insert_text((72, 100), "Use the Describe Global resource to list objects.", fontsize=10)
    page.insert_text((72, 140), "Example response body", fontsize=10)
    page.insert_text((72, 160), "{", fontsize=10)
    page.insert_text((72, 180), '"encoding": "UTF-8",', fontsize=10)
    page.insert_text((72, 200), '"maxBatchSize": 200', fontsize=10)
    page.insert_text((72, 220), "}", fontsize=10)
    document.save(path)
    document.close()


def test_extract_page_text_preserves_reading_order_and_heading() -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 200), "Body paragraph appears lower on the page.", fontsize=10)
    page.insert_text((72, 72), "Section Heading", fontsize=16)

    extracted = extract_page_text(page, page_number=1)
    document.close()

    assert extracted.page_number == 1
    assert extracted.heading == "Section Heading"
    assert extracted.text.index("Section Heading") < extracted.text.index("Body paragraph")


def test_extract_pdf_pages_reads_file(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    _write_sample_pdf(pdf_path)

    pages = extract_pdf_pages(pdf_path)

    assert len(pages) == 1
    assert pages[0].heading == "CHAPTER 1"
    assert "Introduction to REST API" in pages[0].text


def test_is_toc_page_detects_contents() -> None:
    lines = [
        PdfLine(page_number=3, text="CONTENTS", font_size=16.0, y0=72.0),
        PdfLine(
            page_number=3,
            text="Chapter 1: Intro . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 1",
            font_size=10.0,
            y0=100.0,
        ),
    ]
    assert is_toc_page(lines) is True


def test_is_toc_page_detects_spaced_dot_leaders() -> None:
    lines = [
        PdfLine(page_number=4, text="Contents", font_size=10.0, y0=72.0),
        PdfLine(
            page_number=4,
            text="Get Field and Other Metadata for an Object . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 42",
            font_size=10.0,
            y0=100.0,
        ),
        PdfLine(
            page_number=4,
            text="Working with Records . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 44",
            font_size=10.0,
            y0=120.0,
        ),
    ]
    assert is_toc_page(lines) is True


def test_build_pdf_sections_splits_by_heading(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sections.pdf"
    _write_multi_section_pdf(pdf_path)

    with pymupdf.open(pdf_path) as document:
        page_lines = [extract_page_lines(document[0], page_number=1)]

    sections = build_pdf_sections(page_lines, running_headers=set())

    assert len(sections) == 2
    assert sections[0].title == "About REST API"
    assert "web interfaces" in sections[0].body
    assert sections[1].title == "Release Notes"
    assert "Release Notes" in sections[1].body


def test_chunk_pdf_sections_adds_breadcrumb_prefix() -> None:
    sections = build_pdf_sections(
        [
            [
                PdfLine(page_number=12, text="About REST API", font_size=11.0, y0=72.0),
                PdfLine(
                    page_number=12,
                    text="REST API is one of several web interfaces.",
                    font_size=10.0,
                    y0=100.0,
                ),
            ]
        ],
        running_headers=set(),
    )

    chunks = chunk_pdf_sections(
        sections,
        document_title="REST API Developer Guide",
        max_chars=2000,
        overlap_chars=200,
    )

    assert len(chunks) == 1
    assert chunks[0].content.startswith("# REST API Developer Guide > About REST API")
    assert chunks[0].chunk_title == "About REST API"


def test_split_salesforce_pdf_into_chunks_keeps_json_together(tmp_path: Path) -> None:
    pdf_path = tmp_path / "json.pdf"
    _write_json_section_pdf(pdf_path)

    chunks = split_salesforce_pdf_into_chunks(
        pdf_path,
        max_chars=2000,
        overlap_chars=200,
        document_title="REST API Developer Guide",
    )

    assert len(chunks) == 1
    assert '"encoding": "UTF-8"' in chunks[0].content
    assert '"maxBatchSize": 200' in chunks[0].content
    assert chunks[0].content.index("{") < chunks[0].content.index("}")


def test_split_salesforce_pdf_pages_into_chunks_splits_long_pages() -> None:
    long_text = "word " * 500
    pages = [
        SalesforcePdfPageText(
            page_number=7,
            text=long_text,
            heading="Query Records",
            char_count=len(long_text),
        )
    ]

    chunks = split_salesforce_pdf_pages_into_chunks(pages, max_chars=120, overlap_chars=20)

    assert len(chunks) >= 2
    assert all(chunk.page_number == 7 for chunk in chunks)
    assert all(chunk.chunk_title == "Query Records" for chunk in chunks)
    assert all(len(chunk.content) <= 220 for chunk in chunks)


def test_extract_pdf_pages_raises_when_missing(tmp_path: Path) -> None:
    missing = tmp_path / "missing.pdf"
    with pytest.raises(FileNotFoundError, match="Salesforce docs PDF not found"):
        extract_pdf_pages(missing)


def test_sanitize_text_for_postgres_strips_null_bytes() -> None:
    assert _sanitize_text_for_postgres("REST\x00API") == "RESTAPI"
    assert _sanitize_metadata_for_postgres({"title": "a\x00b", "count": 1}) == {"title": "ab", "count": 1}


@pytest.mark.asyncio
async def test_ingest_salesforce_documentation_from_pdf_strips_null_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "sf_docs.pdf"
    _write_sample_pdf(pdf_path)
    monkeypatch.setattr(settings.doc_corpus, "OPENAI_API_KEY", "oa", raising=False)

    dirty_chunk = SalesforcePdfChunk(
        page_number=1,
        content="# Guide > Section\x00\n\nBody\x00text",
        chunk_title="Section\x00",
        metadata={"document_title": "Guide\x00", "section_title": "Section\x00", "source_format": "pdf"},
    )

    monkeypatch.setattr(
        salesforce_pdf_embedder_module,
        "split_salesforce_pdf_into_chunks",
        lambda *_args, **_kwargs: [dirty_chunk],
    )

    async def fake_embed(  # noqa: ARG001
        *,
        texts: list[str],
        model: str,
        api_key: str,
        progress_bar: object | None = None,
    ) -> list[list[float]]:
        return [[0.01] * 1536 for _ in texts]

    monkeypatch.setattr(salesforce_pdf_embedder_module, "embed_texts_openai", fake_embed)

    session = MagicMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    await ingest_salesforce_documentation_from_pdf(session, pdf_path, show_progress=False)

    added = session.add.call_args_list[0][0][0]
    assert "\x00" not in added.content
    assert "\x00" not in added.page_title
    assert "\x00" not in added.metadata_dict["salesforce_pdf"]["document_title"]


@pytest.mark.asyncio
async def test_ingest_salesforce_documentation_from_pdf_persists_chunks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "sf_docs.pdf"
    _write_sample_pdf(pdf_path)

    monkeypatch.setattr(settings.doc_corpus, "OPENAI_API_KEY", "oa", raising=False)

    async def fake_embed(  # noqa: ARG001
        *,
        texts: list[str],
        model: str,
        api_key: str,
        progress_bar: object | None = None,
    ) -> list[list[float]]:
        return [[0.01] * 1536 for _ in texts]

    monkeypatch.setattr(salesforce_pdf_embedder_module, "embed_texts_openai", fake_embed)

    session = MagicMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    pdfs_seen, chunks_written, row_titles = await ingest_salesforce_documentation_from_pdf(
        session,
        pdf_path,
        show_progress=False,
    )

    assert pdfs_seen == 1
    assert chunks_written >= 1
    assert len(row_titles) == chunks_written

    added = session.add.call_args_list[0][0][0]
    assert added.application == SALESFORCE_APP_NAME
    assert added.collection_key == "default"
    assert added.metadata_dict["salesforce_pdf"]["source_format"] == "pdf"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_ingest_salesforce_documentation_from_pdf_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "sf_docs.pdf"
    _write_sample_pdf(pdf_path)
    monkeypatch.setattr(settings.doc_corpus, "OPENAI_API_KEY", "", raising=False)

    session = MagicMock()
    with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
        await ingest_salesforce_documentation_from_pdf(session, pdf_path, show_progress=False)
