"""Unit tests for documentation corpus helpers."""

from __future__ import annotations

import math
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from aegra_api.services import doc_corpus_service as doc_corpus_service_module
from aegra_api.services.doc_corpus_service import (
    cosine_distance_row,
    ingest_documentation_source,
    ingest_github_documentation_from_zip,
    iter_github_docs_zip_markdown_members,
    parse_firecrawl_scrape_payload,
    split_github_docs_zip_markdown_into_chunks,
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


def test_split_github_docs_zip_small_file_one_chunk() -> None:
    body = "intro\n\n## Not split\n\nbecause whole body is small."
    pairs = split_github_docs_zip_markdown_into_chunks(
        body,
        zip_member_path="content/chapter/guide.md",
        max_chars=50,
        overlap_chars=5,
    )
    assert len(pairs) == 1
    text, title = pairs[0]
    assert text == body.strip()
    assert title == "Not split"


def test_split_github_docs_zip_splits_on_h2_when_over_small_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doc_corpus_service_module, "_GITHUB_DOCS_SMALL_FILE_MAX_CHARS", 40)
    monkeypatch.setattr(doc_corpus_service_module, "_GITHUB_DOCS_HEADER_STRATEGY_UPPER_MAX_CHARS", 50_000)
    body = "preamble text here\n\n## First\n\naaa body\n\n## Second\n\nbbb body\n"
    pairs = split_github_docs_zip_markdown_into_chunks(
        body,
        zip_member_path="page.md",
        max_chars=30,
        overlap_chars=5,
    )
    assert len(pairs) >= 2
    joined = "\n".join(p[0] for p in pairs)
    section_titles = {p[1] for p in pairs}
    assert "## First" in joined
    assert "## Second" in joined
    assert "First" in section_titles
    assert "Second" in section_titles


def test_split_github_docs_zip_subdivides_large_h2_with_h3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doc_corpus_service_module, "_GITHUB_DOCS_SMALL_FILE_MAX_CHARS", 80)
    monkeypatch.setattr(doc_corpus_service_module, "_GITHUB_DOCS_HEADER_STRATEGY_UPPER_MAX_CHARS", 50_000)
    monkeypatch.setattr(doc_corpus_service_module, "_GITHUB_DOCS_H2_BLOCK_SUBDIVIDE_CHARS", 150)
    filler = "word " * 40
    body = f"## Section\n\n{filler}\n\n### Sub A\n\n{filler}\n\n### Sub B\n\n{filler}\n"
    pairs = split_github_docs_zip_markdown_into_chunks(
        body,
        zip_member_path="x/y.md",
        max_chars=60,
        overlap_chars=8,
    )
    titles_sub_a = sum(1 for c, _t in pairs if "### Sub A" in c)
    titles_sub_b = sum(1 for c, _t in pairs if "### Sub B" in c)
    assert titles_sub_a >= 1
    assert titles_sub_b >= 1
    chunk_titles = {t for _c, t in pairs}
    assert "Section — Sub A" in chunk_titles
    assert "Section — Sub B" in chunk_titles


def test_split_github_docs_zip_over_upper_max_uses_sliding_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doc_corpus_service_module, "_GITHUB_DOCS_SMALL_FILE_MAX_CHARS", 20)
    monkeypatch.setattr(doc_corpus_service_module, "_GITHUB_DOCS_HEADER_STRATEGY_UPPER_MAX_CHARS", 80)
    body = "q" * 120
    pairs = split_github_docs_zip_markdown_into_chunks(
        body,
        zip_member_path="prefix/big-file.md",
        max_chars=35,
        overlap_chars=5,
    )
    assert len(pairs) >= 3
    assert all(t == "big-file" for _c, t in pairs)


def test_split_github_docs_zip_small_file_uses_filename_when_no_h2() -> None:
    body = ("paragraph without heading.\n\n" * 15).strip()
    assert len(body) <= 2048
    pairs = split_github_docs_zip_markdown_into_chunks(
        body,
        zip_member_path="content/my-article.md",
        max_chars=50,
        overlap_chars=5,
    )
    assert len(pairs) == 1
    assert pairs[0][1] == "my-article"


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


def test_iter_github_docs_zip_markdown_members_raises_when_no_md(tmp_path: Path) -> None:
    zip_path = tmp_path / "empty.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("note.txt", "hello")

    with pytest.raises(ValueError, match="no \\.md files"):
        iter_github_docs_zip_markdown_members(zip_path)


def test_iter_github_docs_zip_markdown_members_raises_on_unsafe_member(tmp_path: Path) -> None:
    zip_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("../escape.md", "# Escaped\n\nbody")

    with pytest.raises(ValueError, match="unsafe zip member path"):
        iter_github_docs_zip_markdown_members(zip_path)


@pytest.mark.asyncio
async def test_ingest_github_documentation_from_zip_requires_yaml_title(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    zip_path = tmp_path / "docs.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("plain.md", "just text\n")

    monkeypatch.setattr(settings.doc_corpus, "GITHUB_DOCS_ZIP_PATH", str(zip_path), raising=False)
    monkeypatch.setattr(settings.doc_corpus, "OPENAI_API_KEY", "oa", raising=False)

    session = MagicMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    with pytest.raises(ValueError, match="YAML frontmatter"):
        await ingest_github_documentation_from_zip(session)


@pytest.mark.asyncio
async def test_ingest_github_documentation_from_zip_persists_chunks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    zip_path = tmp_path / "docs.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(
            "chapter/guide.md",
            "---\ntitle: Labeled\n---\n\nIntro.\n\n## Section one\n\n" + "word " * 80,
        )

    monkeypatch.setattr(settings.doc_corpus, "GITHUB_DOCS_ZIP_PATH", str(zip_path), raising=False)
    monkeypatch.setattr(settings.doc_corpus, "OPENAI_API_KEY", "oa", raising=False)
    monkeypatch.setattr(settings.doc_corpus, "DOCS_EMBED_MODEL", "text-embedding-3-small", raising=False)
    monkeypatch.setattr(settings.doc_corpus, "DOCS_EMBED_DIMENSIONS", 1536, raising=False)
    monkeypatch.setattr(settings.doc_corpus, "DOCS_CHUNK_MAX_CHARS", 100, raising=False)
    monkeypatch.setattr(settings.doc_corpus, "DOCS_CHUNK_OVERLAP_CHARS", 10, raising=False)

    async def fake_embed(  # noqa: ARG001
        *,
        texts: list[str],
        model: str,
        api_key: str,
    ) -> list[list[float]]:
        return [[0.01] * 1536 for _ in texts]

    monkeypatch.setattr(doc_corpus_service_module, "embed_texts_openai", fake_embed)

    session = MagicMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    files_seen, nchunks, row_titles = await ingest_github_documentation_from_zip(session)

    assert files_seen == 1
    assert nchunks >= 1
    assert len(row_titles) == nchunks
    assert all(t == "Section one" for t in row_titles)
    assert session.commit.await_count == 2
    assert session.add.call_count == nchunks
