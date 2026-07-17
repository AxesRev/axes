"""Unit tests for documentation corpus helpers."""

from __future__ import annotations

import math
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import APIConnectionError, RateLimitError

from aegra_api.models.doc_corpus import DocCorpusSearchHit
from aegra_api.services import doc_corpus_service as doc_corpus_service_module
from aegra_api.services.doc_corpus_service import (
    _openai_retry_wait_seconds,
    cosine_distance_row,
    embed_texts_openai,
    format_doc_corpus_hits_for_prompt,
    split_text_into_chunks,
)
from aegra_api.settings import settings
from app_integrations.github.doc_generation import zip_embedder as github_zip_embedder_module
from app_integrations.github.doc_generation.zip_embedder import (
    ingest_github_documentation_from_zip,
    iter_github_docs_zip_markdown_members,
    split_github_docs_zip_markdown_into_chunks,
)


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
    monkeypatch.setattr(github_zip_embedder_module, "_GITHUB_DOCS_SMALL_FILE_MAX_CHARS", 40)
    monkeypatch.setattr(github_zip_embedder_module, "_GITHUB_DOCS_HEADER_STRATEGY_UPPER_MAX_CHARS", 50_000)
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
    monkeypatch.setattr(github_zip_embedder_module, "_GITHUB_DOCS_SMALL_FILE_MAX_CHARS", 80)
    monkeypatch.setattr(github_zip_embedder_module, "_GITHUB_DOCS_HEADER_STRATEGY_UPPER_MAX_CHARS", 50_000)
    monkeypatch.setattr(github_zip_embedder_module, "_GITHUB_DOCS_H2_BLOCK_SUBDIVIDE_CHARS", 150)
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
    monkeypatch.setattr(github_zip_embedder_module, "_GITHUB_DOCS_SMALL_FILE_MAX_CHARS", 20)
    monkeypatch.setattr(github_zip_embedder_module, "_GITHUB_DOCS_HEADER_STRATEGY_UPPER_MAX_CHARS", 80)
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


def test_github_docs_chunking_body_synthesizes_empty_content_from_frontmatter() -> None:
    md = """---
title: Concepts for account and profile
intro: Learn the core concepts.
children:
  - /personal-profile
  - /account-management
---

"""
    post = github_zip_embedder_module._github_docs_frontmatter_post(md, member="x/index.md")
    doc_title = github_zip_embedder_module._github_docs_document_title_from_post(post, member="x/index.md")
    body = github_zip_embedder_module._github_docs_chunking_body_from_post(post, document_title=doc_title)
    assert "# Concepts for account and profile" in body
    assert "Learn the core concepts." in body
    assert "- /personal-profile" in body


def test_github_docs_chunking_body_fallback_heading_when_stub_metadata_empty() -> None:
    md = "---\nplaceholder: true\n---\n\n"
    post = github_zip_embedder_module._github_docs_frontmatter_post(md, member="only/stub.md")
    body = github_zip_embedder_module._github_docs_chunking_body_from_post(post, document_title="Stub Title")
    assert body.strip() == "# Stub Title"


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


def test_format_doc_corpus_hits_for_prompt_omits_source_url() -> None:
    block = format_doc_corpus_hits_for_prompt(
        [
            DocCorpusSearchHit(
                application="github",
                page_title="Get a List of Objects",
                content="Use the Describe Global resource.",
                score=0.91,
            )
        ]
    )

    assert "URL:" not in block
    assert "Get a List of Objects" in block
    assert "Use the Describe Global resource." in block


def test_openai_retry_wait_seconds_uses_retry_after_header() -> None:
    response = MagicMock()
    response.headers = {"retry-after": "2.5"}
    err = RateLimitError("rate limit", response=response, body=None)
    assert _openai_retry_wait_seconds(error=err, attempt=1) == pytest.approx(2.5)


def test_openai_retry_wait_seconds_parses_try_again_in_ms_from_message() -> None:
    response = MagicMock()
    response.headers = {}
    err = RateLimitError(
        "Rate limit reached ... Please try again in 207ms.",
        response=response,
        body=None,
    )
    assert _openai_retry_wait_seconds(error=err, attempt=1) == pytest.approx(0.207)


def test_openai_retry_wait_seconds_exponential_backoff_without_hints() -> None:
    err = APIConnectionError(request=MagicMock())
    assert _openai_retry_wait_seconds(error=err, attempt=1) == pytest.approx(1.0)
    assert _openai_retry_wait_seconds(error=err, attempt=3) == pytest.approx(4.0)


@pytest.mark.asyncio
async def test_embed_texts_openai_retries_on_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    sleep = AsyncMock()
    monkeypatch.setattr(doc_corpus_service_module.asyncio, "sleep", sleep)

    call_count = 0
    response = MagicMock()
    response.headers = {"retry-after": "0.01"}

    async def create_side_effect(*_args: object, **_kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RateLimitError("429", response=response, body=None)
        return MagicMock(data=[MagicMock(index=0, embedding=[0.1, 0.2, 0.3])])

    client = MagicMock()
    client.embeddings.create = AsyncMock(side_effect=create_side_effect)
    monkeypatch.setattr(doc_corpus_service_module, "AsyncOpenAI", lambda **_: client)

    vectors = await embed_texts_openai(texts=["hello"], model="text-embedding-3-small", api_key="test")

    assert vectors == [[0.1, 0.2, 0.3]]
    assert call_count == 2
    sleep.assert_awaited_once_with(0.1)


@pytest.mark.asyncio
async def test_embed_texts_openai_raises_after_max_rate_limit_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    sleep = AsyncMock()
    monkeypatch.setattr(doc_corpus_service_module.asyncio, "sleep", sleep)
    monkeypatch.setattr(doc_corpus_service_module, "_EMBED_MAX_ATTEMPTS", 2)

    response = MagicMock()
    response.headers = {}

    async def create_side_effect(*_args: object, **_kwargs: object) -> MagicMock:
        raise RateLimitError("429", response=response, body=None)

    client = MagicMock()
    client.embeddings.create = AsyncMock(side_effect=create_side_effect)
    monkeypatch.setattr(doc_corpus_service_module, "AsyncOpenAI", lambda **_: client)

    with pytest.raises(RateLimitError):
        await embed_texts_openai(texts=["hello"], model="text-embedding-3-small", api_key="test")

    assert sleep.await_count == 1


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


def test_github_docs_zip_document_title_prefers_yaml_then_h1_then_filename() -> None:
    assert (
        github_zip_embedder_module._github_docs_zip_document_title(
            "---\ntitle: From Yaml\n---\n\n# Ignore\n",
            member="x.md",
        )
        == "From Yaml"
    )
    assert (
        github_zip_embedder_module._github_docs_zip_document_title(
            "# Content <!-- omit in toc -->\n\nHi\n",
            member="content/README.md",
        )
        == "Content"
    )
    assert (
        github_zip_embedder_module._github_docs_zip_document_title(
            "no heading here\n",
            member="plain/stuff.md",
        )
        == "stuff"
    )


@pytest.mark.asyncio
async def test_ingest_github_documentation_from_zip_plain_markdown_uses_filename_document_title(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    zip_path = tmp_path / "docs.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("plain.md", "just text\n")

    monkeypatch.setattr(settings.doc_corpus, "GITHUB_DOCS_ZIP_PATH", str(zip_path), raising=False)
    monkeypatch.setattr(settings.doc_corpus, "OPENAI_API_KEY", "oa", raising=False)
    monkeypatch.setattr(settings.doc_corpus, "DOCS_CHUNK_MAX_CHARS", 500, raising=False)
    monkeypatch.setattr(settings.doc_corpus, "DOCS_CHUNK_OVERLAP_CHARS", 50, raising=False)

    async def fake_embed(  # noqa: ARG001
        *,
        texts: list[str],
        model: str,
        api_key: str,
        progress_bar: object | None = None,
    ) -> list[list[float]]:
        return [[0.01] * 1536 for _ in texts]

    monkeypatch.setattr(github_zip_embedder_module, "embed_texts_openai", fake_embed)

    session = MagicMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    await ingest_github_documentation_from_zip(session, show_progress=False)

    added = session.add.call_args_list[0][0][0]
    assert added.metadata_dict["github_docs_zip"]["document_title"] == "plain"


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
        progress_bar: object | None = None,
    ) -> list[list[float]]:
        return [[0.01] * 1536 for _ in texts]

    monkeypatch.setattr(github_zip_embedder_module, "embed_texts_openai", fake_embed)

    session = MagicMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    files_seen, nchunks, row_titles = await ingest_github_documentation_from_zip(session, show_progress=False)

    assert files_seen == 1
    assert nchunks >= 1
    assert len(row_titles) == nchunks
    assert all(t == "Section one" for t in row_titles)
    assert session.commit.await_count == 2
    assert session.add.call_count == nchunks
