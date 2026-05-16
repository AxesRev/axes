"""Unit tests for documentation corpus helpers."""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock

import pytest

from aegra_api.services import doc_corpus_service as doc_corpus_service_module
from aegra_api.services.doc_corpus_service import (
    cosine_distance_row,
    ingest_documentation_source,
    parse_firecrawl_scrape_payload,
    split_text_into_chunks,
)
from aegra_api.settings import settings


def test_parse_firecrawl_scrape_payload_success() -> None:
    markdown, meta = parse_firecrawl_scrape_payload(
        {"success": True, "data": {"markdown": "# Hello", "metadata": {"title": "Hi"}}}
    )
    assert markdown == "# Hello"
    assert meta["title"] == "Hi"


def test_parse_firecrawl_scrape_payload_failure() -> None:
    with pytest.raises(ValueError, match="oops"):
        parse_firecrawl_scrape_payload({"success": False, "error": "oops"})


def test_split_text_into_chunks_returns_empty_for_blank() -> None:
    assert split_text_into_chunks("", max_chars=100, overlap_chars=10) == []
    assert split_text_into_chunks("   \n", max_chars=100, overlap_chars=10) == []


def test_split_text_into_chunks_splits_with_overlap() -> None:
    text = "abcdefgh" * 50
    chunks = split_text_into_chunks(text, max_chars=40, overlap_chars=8)
    assert len(chunks) >= 2
    assert all(len(c) <= 40 for c in chunks)
    # Overlapping windows duplicate boundary text; ensure every chunk is a substring of the source.
    for chunk in chunks:
        assert chunk in text


def test_split_text_into_chunks_clamps_overlap_when_invalid() -> None:
    text = "word " * 30
    chunks = split_text_into_chunks(text, max_chars=20, overlap_chars=50)
    assert chunks
    assert all(len(c) <= 20 for c in chunks)


def test_cosine_distance_row_identical_vectors_is_zero() -> None:
    v = [1.0, 0.0, 0.0]
    assert cosine_distance_row(v, v) == pytest.approx(0.0)


def test_cosine_distance_row_orthogonal_vectors_is_one() -> None:
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert cosine_distance_row(a, b) == pytest.approx(1.0)


def test_cosine_distance_row_length_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="dimension mismatch"):
        cosine_distance_row([1.0], [1.0, 0.0])


def test_cosine_distance_row_zero_vector_handled() -> None:
    assert cosine_distance_row([0.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert math.isfinite(cosine_distance_row([0.0, 0.0], [0.0, 0.0]))


@pytest.mark.asyncio
async def test_ingest_documentation_source_persists_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.doc_corpus, "FIRECRAWL_API_KEY", "fc", raising=False)
    monkeypatch.setattr(settings.doc_corpus, "OPENAI_API_KEY", "oa", raising=False)
    monkeypatch.setattr(settings.doc_corpus, "FIRECRAWL_BASE_URL", "https://api.firecrawl.dev/v2", raising=False)
    monkeypatch.setattr(settings.doc_corpus, "DOCS_EMBED_MODEL", "text-embedding-3-small", raising=False)
    monkeypatch.setattr(settings.doc_corpus, "DOCS_EMBED_DIMENSIONS", 1536, raising=False)
    monkeypatch.setattr(settings.doc_corpus, "DOCS_CHUNK_MAX_CHARS", 100, raising=False)
    monkeypatch.setattr(settings.doc_corpus, "DOCS_CHUNK_OVERLAP_CHARS", 10, raising=False)

    async def fake_start(  # noqa: ARG001
        client: object,
        *,
        api_key: str,
        base_url: str,
        start_url: str,
        limit: int,
    ) -> str:
        return "job-1"

    async def fake_iter(  # noqa: ARG001
        client: object,
        *,
        api_key: str,
        base_url: str,
        crawl_id: str,
        poll_interval: float,
        max_wait: float,
    ):
        yield ("https://example.com/doc", "# Hi\n\n" + "word " * 80, {"title": "T"})

    async def fake_embed(  # noqa: ARG001
        *,
        texts: list[str],
        model: str,
        api_key: str,
    ) -> list[list[float]]:
        return [[0.01] * 1536 for _ in texts]

    monkeypatch.setattr(doc_corpus_service_module, "_firecrawl_start_crawl", fake_start)
    monkeypatch.setattr(doc_corpus_service_module, "_firecrawl_iter_crawl_pages", fake_iter)
    monkeypatch.setattr(doc_corpus_service_module, "embed_texts_openai", fake_embed)

    session = MagicMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    pages, nchunks, row_titles = await ingest_documentation_source(session, source_url="https://example.com/doc")

    assert pages == 1
    assert nchunks >= 1
    assert len(row_titles) == nchunks
    assert all(t == "T" for t in row_titles)
    assert session.commit.await_count == 2
    assert session.add.call_count == nchunks
