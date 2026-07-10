"""Ingest and search crawled documentation using Firecrawl or local zip archives, OpenAI embeddings, and pgvector.

Use ``ingest_github_documentation_from_zip`` for the GitHub docs CLI (``python-frontmatter`` for YAML, hierarchical chunking).
Use ``ingest_documentation_source`` to crawl a site (Firecrawl v2 ``/crawl``), embed chunks, and write ``doc_embedding_chunks``.
There is no public HTTP API for corpus ingest or search helpers.
"""

from __future__ import annotations

import asyncio
import math
import re
import zipfile
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import frontmatter
import httpx
import structlog
import yaml
from openai import APIConnectionError, AsyncOpenAI, InternalServerError, OpenAIError, RateLimitError
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from tqdm import tqdm

from aegra_api.core.orm import DocEmbeddingChunk, get_metadata_session_maker
from aegra_api.models.doc_corpus import DocCorpusSearchHit
from aegra_api.settings import settings

logger = structlog.get_logger(__name__)

_DEFAULT_EMBED_BATCH = 64
_EMBED_MAX_ATTEMPTS = 30
_EMBED_RETRY_BASE_DELAY_SEC = 1.0
_EMBED_RETRY_MAX_DELAY_SEC = 60.0
_FIRECRAWL_HTTP_TIMEOUT_SEC = 120.0

_DOC_INGEST_APPLICATION = "github"
_DOC_INGEST_COLLECTION_KEY = "default"


@dataclass(frozen=True, slots=True)
class _PendingGithubDocChunk:
    """One chunk row waiting for batched embedding and DB insert."""

    source_url: str
    chunk_index: int
    content: str
    chunk_display_title: str
    zip_meta: dict[str, Any]


# GitHub Docs zip: hierarchical chunk thresholds (characters, post-frontmatter body).
_GITHUB_DOCS_SMALL_FILE_MAX_CHARS = 2048
_GITHUB_DOCS_HEADER_STRATEGY_UPPER_MAX_CHARS = 98304  # 96 KiB
_GITHUB_DOCS_H2_BLOCK_SUBDIVIDE_CHARS = 4096


def split_text_into_chunks(
    text: str,
    *,
    max_chars: int,
    overlap_chars: int,
) -> list[str]:
    """Split plain text into overlapping windows by character count."""
    body = text.strip()
    if not body:
        return []

    safe_overlap = overlap_chars if overlap_chars < max_chars else max(0, max_chars // 8)
    chunks: list[str] = []
    start = 0
    length = len(body)
    while start < length:
        end = min(start + max_chars, length)
        piece = body[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= length:
            break
        start = max(end - safe_overlap, start + 1)
    return chunks


def parse_firecrawl_scrape_payload(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Parse the JSON body from a Firecrawl v2 ``POST /scrape`` response."""
    if not payload.get("success"):
        msg = payload.get("error") or payload.get("message") or "Firecrawl scrape failed"
        raise ValueError(str(msg))
    data = payload.get("data") or {}
    markdown = data.get("markdown") or ""
    meta_raw = data.get("metadata")
    metadata: dict[str, Any] = meta_raw if isinstance(meta_raw, dict) else {}
    return str(markdown), metadata


async def scrape_url_markdown(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    base_url: str,
    url: str,
) -> tuple[str, dict[str, Any]]:
    """Scrape a single URL via Firecrawl and return markdown plus metadata."""
    endpoint = f"{base_url.rstrip('/')}/scrape"
    response = await client.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"url": url, "formats": ["markdown"]},
        timeout=_FIRECRAWL_HTTP_TIMEOUT_SEC,
    )
    response.raise_for_status()
    return parse_firecrawl_scrape_payload(response.json())


async def _firecrawl_start_crawl(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    base_url: str,
    start_url: str,
    limit: int,
) -> str:
    """Start a Firecrawl v2 multi-page crawl; returns crawl job id."""
    api_base = base_url.rstrip("/")
    body: dict[str, Any] = {
        "url": start_url,
        "sitemap": "include",
        "crawlEntireDomain": True,
        "limit": limit,
        "scrapeOptions": {
            "onlyMainContent": True,
            "maxAge": 172800000,
            # No PDF/binary parsers — HTML→markdown text only (lighter; avoids PDF credits).
            "parsers": [],
            "formats": ["markdown"],
        },
    }
    response = await client.post(
        f"{api_base}/crawl",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=_FIRECRAWL_HTTP_TIMEOUT_SEC,
    )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    if payload.get("success") is False:
        msg = payload.get("error") or payload.get("message") or "firecrawl crawl start failed"
        raise ValueError(str(msg))
    crawl_id = payload.get("id")
    if not crawl_id:
        raise ValueError("firecrawl crawl start returned no job id")
    return str(crawl_id)


async def _firecrawl_iter_crawl_pages(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    base_url: str,
    crawl_id: str,
    poll_interval: float,
    max_wait: float,
) -> AsyncIterator[tuple[str, str, dict[str, Any]]]:
    """Poll a Firecrawl crawl job and yield ``(source_url, markdown, metadata_dict)`` per page."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max_wait
    api_base = base_url.rstrip("/")
    status_url = f"{api_base}/crawl/{crawl_id}"
    headers = {"Authorization": f"Bearer {api_key}"}
    pending_url: str | None = status_url

    while pending_url is not None:
        if loop.time() > deadline:
            raise TimeoutError(f"firecrawl crawl {crawl_id} exceeded {max_wait}s")

        http_response = await client.get(pending_url, headers=headers, timeout=_FIRECRAWL_HTTP_TIMEOUT_SEC)
        http_response.raise_for_status()
        payload = http_response.json()
        if payload.get("success") is False:
            msg = payload.get("error") or payload.get("message") or "firecrawl crawl failed"
            raise ValueError(str(msg))

        for item in payload.get("data") or []:
            if not isinstance(item, dict):
                continue
            markdown = item.get("markdown") or ""
            meta_raw = item.get("metadata")
            meta_d: dict[str, Any] = meta_raw if isinstance(meta_raw, dict) else {}
            src = meta_d.get("sourceURL") or meta_d.get("url") or ""
            yield (str(src), str(markdown), meta_d)

        nxt = payload.get("next")
        status = payload.get("status")

        if nxt:
            pending_url = str(nxt)
            continue

        if status == "failed":
            raise ValueError(str(payload.get("error") or "firecrawl crawl failed"))

        if status == "completed":
            break

        await asyncio.sleep(poll_interval)
        pending_url = status_url


def _metadata_page_title(fire_meta: dict[str, Any]) -> str | None:
    title_val = fire_meta.get("title")
    if isinstance(title_val, list) and title_val:
        return str(title_val[0])
    if title_val is not None:
        return str(title_val)
    return None


def _safe_zip_inner_path(name: str) -> str | None:
    """Reject zip members with absolute paths or ``..`` segments."""
    path = Path(name)
    if path.is_absolute():
        return None
    if ".." in path.parts:
        return None
    return path.as_posix()


def _github_docs_frontmatter_post(markdown: str, *, member: str) -> frontmatter.Post:
    """Parse optional YAML frontmatter and markdown body using ``python-frontmatter``."""
    text = markdown.lstrip("\ufeff")
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        found_close = False
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                found_close = True
                break
        if not found_close:
            raise ValueError(f"github docs markdown has unclosed YAML frontmatter: {member!r}")
    try:
        return frontmatter.loads(text)
    except yaml.YAMLError as exc:
        logger.warning("github_docs_frontmatter_yaml_invalid", member=member, error=str(exc))
        return frontmatter.Post(content=text)


def _strip_markdown_inline_html_comment_suffix(fragment: str) -> str:
    """Remove a trailing ``<!-- ... -->`` suffix from a heading fragment."""
    if "<!--" not in fragment:
        return fragment.strip()
    return fragment.split("<!--", maxsplit=1)[0].strip()


def _first_h1_heading_line_text(markdown: str) -> str | None:
    """Return text of the first ATX ``#`` heading line (not ``##`` / ``###``)."""
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line.startswith("#") or line.startswith("##"):
            continue
        matched = re.match(r"^#\s+(.+)$", line)
        if not matched:
            continue
        title = _strip_markdown_inline_html_comment_suffix(matched.group(1))
        if title:
            return title
    return None


def _metadata_title_string(metadata: Mapping[str, Any]) -> str | None:
    raw_title = metadata.get("title")
    if isinstance(raw_title, str):
        val = raw_title.strip()
        if val:
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                return val[1:-1]
            return val
    if raw_title is not None and not isinstance(raw_title, (dict, list)):
        val = str(raw_title).strip()
        if val:
            return val
    return None


def _github_docs_document_title_from_post(post: frontmatter.Post, *, member: str) -> str:
    """Corpus document title: YAML ``title:``, else first ``#`` heading in body, else filename stem."""
    yaml_title = _metadata_title_string(post.metadata)
    if yaml_title is not None:
        return yaml_title
    h1 = _first_h1_heading_line_text(post.content)
    if h1 is not None:
        return h1
    return _github_docs_chunk_title_from_member_path(member)


def _github_docs_synthetic_markdown_from_frontmatter(post: frontmatter.Post) -> str | None:
    """Build markdown from YAML when ``post.content`` is empty (GitHub docs index / landing stubs)."""
    meta = post.metadata
    blocks: list[str] = []
    title = _metadata_title_string(meta)
    if title:
        blocks.append(f"# {title}")
    intro = meta.get("intro")
    if isinstance(intro, str) and intro.strip():
        blocks.append(intro.strip())
    children = meta.get("children")
    if isinstance(children, list):
        lines: list[str] = []
        for item in children:
            if isinstance(item, str) and item.strip():
                lines.append(f"- {item.strip()}")
            elif item is not None and not isinstance(item, (dict, list)):
                text_item = str(item).strip()
                if text_item:
                    lines.append(f"- {text_item}")
        if lines:
            blocks.append("\n".join(lines))
    if not blocks:
        return None
    return "\n\n".join(blocks)


def _github_docs_chunking_body_from_post(post: frontmatter.Post, *, document_title: str) -> str:
    """Markdown body used for chunking; synthesize text when the file has YAML only (no body)."""
    body = post.content.strip()
    if body:
        return body
    synthetic = _github_docs_synthetic_markdown_from_frontmatter(post)
    if synthetic is not None:
        return synthetic
    return f"# {document_title}\n"


def _github_docs_zip_document_title(markdown: str, *, member: str) -> str:
    """Same as ``_github_docs_document_title_from_post`` after parsing *markdown*."""
    post = _github_docs_frontmatter_post(markdown, member=member)
    return _github_docs_document_title_from_post(post, member=member)


def _github_docs_chunk_title_from_member_path(zip_member_path: str) -> str:
    """Display title from zip entry path (filename stem without ``.md``)."""
    stem = Path(zip_member_path).stem.strip()
    return stem if stem else zip_member_path


def _section_heading_title_or_file(primary: str, *, file_title: str) -> str:
    candidate = primary.strip()
    return candidate if candidate else file_title


def _first_h2_heading_line_text(body: str) -> str | None:
    """Return the text of the first ``##`` heading line (ignores ``###`` and deeper)."""
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith("###"):
            continue
        matched = re.match(r"^##\s+(.+)$", line)
        if matched:
            title = matched.group(1).strip()
            if title:
                return title
    return None


def split_github_docs_zip_markdown_into_chunks(
    body_markdown: str,
    *,
    zip_member_path: str,
    max_chars: int,
    overlap_chars: int,
) -> list[tuple[str, str]]:
    """Split GitHub-docs-style markdown body; returns ``(chunk_text, chunk_title)`` pairs.

    Chunk titles:

    * Whole-file small docs (``len <= 2048``): one chunk; title is the first ``##`` heading if any,
      otherwise the zip entry filename stem.
    * ``##`` sections use that heading line text (without the ``##`` marker).
    * ``###`` subdivisions use ``"{h2} — {h3}"``.
    * Sliding-window splits (oversized sections or huge files) reuse the same section title when
      applicable; otherwise the zip entry filename stem.

    Rules (hardcoded size gates):

    * ``len(body) <= 2048``: one chunk (no split).
    * ``2048 < len(body) <= 98304``: split on top-level ``## `` headings; any ``##`` section longer
      than 4096 chars is subdivided on ``### `` headings.
    * ``len(body) > 98304``: sliding-window chunking over the whole body (same as
      ``split_text_into_chunks``).

    Pieces that remain oversized after ``###`` splits are further split with ``split_text_into_chunks``.
    """
    file_chunk_title = _github_docs_chunk_title_from_member_path(zip_member_path)
    body = body_markdown.strip()
    if not body:
        return []

    n = len(body)
    if n <= _GITHUB_DOCS_SMALL_FILE_MAX_CHARS:
        h2_title = _first_h2_heading_line_text(body)
        chunk_title = (
            _section_heading_title_or_file(h2_title, file_title=file_chunk_title)
            if h2_title is not None
            else file_chunk_title
        )
        return [(body, chunk_title)]

    if n > _GITHUB_DOCS_HEADER_STRATEGY_UPPER_MAX_CHARS:
        return [
            (piece, file_chunk_title)
            for piece in split_text_into_chunks(body, max_chars=max_chars, overlap_chars=overlap_chars)
        ]

    segments = re.split(r"^##\s+", body, flags=re.MULTILINE)
    preamble = segments[0].strip()
    h2_sections: list[tuple[str, str]] = []
    for raw in segments[1:]:
        raw_lines = raw.splitlines()
        h2_title = raw_lines[0].strip() if raw_lines else ""
        section_rest = "\n".join(raw_lines[1:]).strip()
        h2_sections.append((h2_title, section_rest))

    if preamble and h2_sections:
        first_title, first_body = h2_sections[0]
        merged = f"{preamble}\n\n{first_body}".strip() if first_body else preamble
        h2_sections[0] = (first_title, merged)
    elif preamble and not h2_sections:
        merged_body = preamble
        return [
            (piece, file_chunk_title)
            for piece in split_text_into_chunks(merged_body, max_chars=max_chars, overlap_chars=overlap_chars)
        ]

    if not h2_sections:
        return [
            (piece, file_chunk_title)
            for piece in split_text_into_chunks(body, max_chars=max_chars, overlap_chars=overlap_chars)
        ]

    out: list[tuple[str, str]] = []

    def append_or_window(text: str, chunk_title: str) -> None:
        piece = text.strip()
        if not piece:
            return
        resolved_title = _section_heading_title_or_file(chunk_title, file_title=file_chunk_title)
        if len(piece) <= _GITHUB_DOCS_H2_BLOCK_SUBDIVIDE_CHARS:
            out.append((piece, resolved_title))
            return
        for window in split_text_into_chunks(piece, max_chars=max_chars, overlap_chars=overlap_chars):
            out.append((window, resolved_title))

    for h2_title, section_body in h2_sections:
        h2_heading_title = _section_heading_title_or_file(h2_title, file_title=file_chunk_title)
        h2_block = f"## {h2_title}\n\n{section_body}".strip() if section_body else f"## {h2_title}".strip()
        if len(h2_block) <= _GITHUB_DOCS_H2_BLOCK_SUBDIVIDE_CHARS:
            append_or_window(h2_block, h2_heading_title)
            continue

        sub = re.split(r"^###\s+", section_body, flags=re.MULTILINE)
        before_h3 = sub[0].strip()
        head_with_intro = f"## {h2_title}\n\n{before_h3}".strip() if before_h3 else f"## {h2_title}".strip()
        append_or_window(head_with_intro, h2_heading_title)

        for raw_h3 in sub[1:]:
            h3_lines = raw_h3.splitlines()
            h3_title = h3_lines[0].strip() if h3_lines else ""
            h3_rest = "\n".join(h3_lines[1:]).strip()
            h3_block = (
                f"## {h2_title}\n\n### {h3_title}\n\n{h3_rest}".strip()
                if h3_rest
                else (f"## {h2_title}\n\n### {h3_title}".strip())
            )
            h3_heading_title = h3_title.strip()
            if h3_heading_title:
                combined = f"{h2_heading_title} — {h3_heading_title}"
            else:
                combined = h2_heading_title
            append_or_window(h3_block, combined)

    return [(c, t) for c, t in out if c.strip()]


def iter_github_docs_zip_markdown_members(zip_path: Path) -> list[str]:
    """Return sorted safe zip member paths ending in ``.md`` (non-directory).

    Raises:
        ValueError: If the archive contains no ``.md`` files, or any ``.md`` member path is unsafe.
    """
    with zipfile.ZipFile(zip_path, "r") as archive:
        md_members: list[str] = []
        for name in archive.namelist():
            if name.endswith("/"):
                continue
            if not name.lower().endswith(".md"):
                continue
            safe = _safe_zip_inner_path(name)
            if safe is None:
                raise ValueError(f"unsafe zip member path: {name!r}")
            md_members.append(safe)
        md_members.sort()
        if not md_members:
            raise ValueError("zip contains no .md files")
        return md_members


def read_github_docs_zip_markdown(zip_path: Path, inner_path: str) -> str:
    """Read one zip member as strict UTF-8 text."""
    safe = _safe_zip_inner_path(inner_path)
    if safe is None:
        raise ValueError("unsafe zip member path")
    with zipfile.ZipFile(zip_path, "r") as archive, archive.open(safe, "r") as raw:
        data = raw.read()
    return data.decode("utf-8")


async def ingest_github_documentation_from_zip(
    session: AsyncSession,
    *,
    show_progress: bool = True,
) -> tuple[int, int, list[str]]:
    """Ingest markdown files from the zip at ``GITHUB_DOCS_ZIP_PATH``.

    Pipeline: (1) chunk every file into a flat list, (2) one batched embedding pass over all chunk
    texts, (3) insert rows. OpenAI still receives up to ``_DEFAULT_EMBED_BATCH`` strings per HTTP
    request; batches are filled across files.

    Each file should have YAML frontmatter with ``title:`` when possible; otherwise the first ``#``
    heading or the zip entry filename stem is used for ``document_title`` metadata.

    Args:
        show_progress: When ``True``, render tqdm bars for chunking, embedding, and DB writes.

    Returns:
        ``(markdown files ingested, chunk rows inserted, chunk display title per row)``.
    """
    cfg = settings.doc_corpus
    configured = cfg.GITHUB_DOCS_ZIP_PATH
    if configured is None:
        raise ValueError("GITHUB_DOCS_ZIP_PATH is not configured")
    resolved = configured.strip()
    if not resolved:
        raise ValueError("GITHUB_DOCS_ZIP_PATH is empty")
    if not cfg.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured")

    archive_path = Path(resolved)
    if not archive_path.is_file():
        raise ValueError(f"github docs zip not found or not a file: {archive_path}")

    application = _DOC_INGEST_APPLICATION
    collection_key = _DOC_INGEST_COLLECTION_KEY

    await session.execute(
        delete(DocEmbeddingChunk).where(
            DocEmbeddingChunk.application == application,
            DocEmbeddingChunk.collection_key == collection_key,
        )
    )
    await session.commit()

    member_paths = iter_github_docs_zip_markdown_members(archive_path)
    file_total = len(member_paths)
    tqdm_disable = not show_progress
    tqdm_kw: dict[str, Any] = {
        "disable": tqdm_disable,
        "dynamic_ncols": True,
        "leave": True,
    }

    pending: list[_PendingGithubDocChunk] = []

    with tqdm(total=file_total, desc="Chunking", unit="file", position=0, **tqdm_kw) as chunk_bar:
        for inner in member_paths:
            markdown = read_github_docs_zip_markdown(archive_path, inner)
            post = _github_docs_frontmatter_post(markdown, member=inner)
            document_title = _github_docs_document_title_from_post(post, member=inner)
            body = _github_docs_chunking_body_from_post(post, document_title=document_title)
            source_ref = f"github-docs://{inner}"

            chunk_pairs = split_github_docs_zip_markdown_into_chunks(
                body,
                zip_member_path=inner,
                max_chars=cfg.DOCS_CHUNK_MAX_CHARS,
                overlap_chars=cfg.DOCS_CHUNK_OVERLAP_CHARS,
            )
            if not chunk_pairs:
                raise ValueError(f"github docs markdown produced no chunks after split: {inner!r}")

            zip_meta: dict[str, Any] = {"zip_member": inner, "document_title": document_title}
            for idx, (text_chunk, chunk_title) in enumerate(chunk_pairs):
                pending.append(
                    _PendingGithubDocChunk(
                        source_url=source_ref,
                        chunk_index=idx,
                        content=text_chunk,
                        chunk_display_title=chunk_title,
                        zip_meta=zip_meta,
                    )
                )

            chunk_bar.update(1)

    chunk_total = len(pending)

    with tqdm(total=chunk_total, desc="Embedding", unit="chunk", position=1, **tqdm_kw) as embed_bar:
        embeddings = await embed_texts_openai(
            texts=[row.content for row in pending],
            model=cfg.DOCS_EMBED_MODEL,
            api_key=cfg.OPENAI_API_KEY,
            progress_bar=embed_bar,
        )

    if len(embeddings) != chunk_total:
        raise RuntimeError("embedding count does not match chunk count")

    row_titles: list[str] = []

    with tqdm(total=chunk_total, desc="Storing in DB", unit="chunk", position=2, **tqdm_kw) as store_bar:
        for row, vector in zip(pending, embeddings, strict=True):
            if len(vector) != cfg.DOCS_EMBED_DIMENSIONS:
                raise ValueError("unexpected embedding size from OpenAI")
            session.add(
                DocEmbeddingChunk(
                    application=application,
                    collection_key=collection_key,
                    source_url=row.source_url,
                    page_title=row.chunk_display_title,
                    chunk_index=row.chunk_index,
                    content=row.content,
                    metadata_dict={"github_docs_zip": row.zip_meta},
                    embedding=vector,
                )
            )
            row_titles.append(row.chunk_display_title)
            store_bar.update(1)

    await session.commit()
    files_seen = file_total
    chunks_written = chunk_total
    return files_seen, chunks_written, row_titles


def _openai_retry_wait_seconds(*, error: OpenAIError, attempt: int) -> float:
    """Compute backoff before retrying an OpenAI embeddings request."""
    if isinstance(error, RateLimitError) and error.response is not None:
        retry_after = error.response.headers.get("retry-after")
        if retry_after is not None:
            try:
                return min(max(float(retry_after), 0.1), _EMBED_RETRY_MAX_DELAY_SEC)
            except ValueError:
                pass

    message = str(error)
    ms_match = re.search(r"try again in (\d+(?:\.\d+)?)\s*ms", message, flags=re.IGNORECASE)
    if ms_match is not None:
        return min(max(float(ms_match.group(1)) / 1000.0, 0.1), _EMBED_RETRY_MAX_DELAY_SEC)

    sec_match = re.search(r"try again in (\d+(?:\.\d+)?)\s*s(?:ec(?:ond)?s?)?", message, flags=re.IGNORECASE)
    if sec_match is not None:
        return min(max(float(sec_match.group(1)), 0.1), _EMBED_RETRY_MAX_DELAY_SEC)

    delay = _EMBED_RETRY_BASE_DELAY_SEC * (2 ** max(attempt - 1, 0))
    return min(delay, _EMBED_RETRY_MAX_DELAY_SEC)


async def _create_embedding_batch_with_retry(
    client: AsyncOpenAI,
    *,
    model: str,
    batch: list[str],
) -> list[list[float]]:
    """Create embeddings for one batch, retrying transient OpenAI failures."""
    last_error: OpenAIError | None = None
    for attempt in range(1, _EMBED_MAX_ATTEMPTS + 1):
        try:
            result = await client.embeddings.create(model=model, input=batch)
            sorted_items = sorted(result.data, key=lambda item: item.index)
            return [list(item.embedding) for item in sorted_items]
        except (RateLimitError, APIConnectionError, InternalServerError) as err:
            last_error = err
            if attempt >= _EMBED_MAX_ATTEMPTS:
                raise
            wait_seconds = _openai_retry_wait_seconds(error=err, attempt=attempt)
            logger.warning(
                "openai_embeddings_retry",
                attempt=attempt,
                wait_seconds=wait_seconds,
                batch_size=len(batch),
                error_type=type(err).__name__,
            )
            await asyncio.sleep(wait_seconds)

    if last_error is not None:
        raise last_error
    msg = "embedding batch failed without a captured error"
    raise RuntimeError(msg)


async def embed_texts_openai(
    *,
    texts: list[str],
    model: str,
    api_key: str,
    progress_bar: tqdm | None = None,
) -> list[list[float]]:
    """Return embedding vectors for each input string using the OpenAI API.

    Requests use batches of up to ``_DEFAULT_EMBED_BATCH`` texts each. ``progress_bar``, when set,
    advances by the batch size after each API call. Transient OpenAI rate limits and connection
    errors are retried with exponential backoff.
    """
    if not texts:
        return []

    client = AsyncOpenAI(api_key=api_key)
    out: list[list[float]] = []
    for start in range(0, len(texts), _DEFAULT_EMBED_BATCH):
        batch = texts[start : start + _DEFAULT_EMBED_BATCH]
        vectors = await _create_embedding_batch_with_retry(client, model=model, batch=batch)
        out.extend(vectors)
        if progress_bar is not None:
            progress_bar.update(len(batch))
    return out


async def search_doc_chunks(
    session: AsyncSession,
    *,
    collection_key: str,
    query_embedding: list[float],
    limit: int,
    applications: Sequence[str] | None = None,
) -> list[DocCorpusSearchHit]:
    """Cosine-distance search over stored documentation chunks."""
    stmt = select(DocEmbeddingChunk).where(DocEmbeddingChunk.collection_key == collection_key)
    if applications:
        stmt = stmt.where(DocEmbeddingChunk.application.in_(tuple(applications)))
    stmt = stmt.order_by(DocEmbeddingChunk.embedding.cosine_distance(query_embedding)).limit(limit)
    rows = list((await session.scalars(stmt)).all())
    hits: list[DocCorpusSearchHit] = []
    for row in rows:
        distance = cosine_distance_row(row.embedding, query_embedding)
        score = _distance_to_similarity(distance)
        hits.append(
            DocCorpusSearchHit(
                application=row.application,
                source_url=row.source_url,
                page_title=row.page_title,
                chunk_index=row.chunk_index,
                content=row.content,
                score=score,
            )
        )
    return hits


def format_doc_corpus_hits_for_prompt(hits: list[DocCorpusSearchHit]) -> str:
    """Turn retrieval hits into a single block suitable for system prompts."""
    if not hits:
        return ""
    parts: list[str] = []
    for i, h in enumerate(hits, start=1):
        title = h.page_title or "(no title)"
        parts.append(
            f"### Snippet {i} — {title}\n"
            f"Application: {h.application}\n"
            f"URL: {h.source_url}\n"
            f"Relevance score: {h.score:.4f}\n\n"
            f"{h.content.strip()}\n"
        )
    return "\n---\n".join(parts)


async def retrieve_doc_corpus_prompt_block(
    *,
    collection_key: str,
    query: str,
    limit: int,
    applications: Sequence[str] | None = None,
) -> tuple[str, list[str]]:
    """Embed ``query``, cosine-search ``doc_embedding_chunks``, return formatted text and titles.

    Returns:
        ``(prompt_block, hit_titles)`` — ``hit_titles`` matches rows merged into the block (empty when skipped).
    """
    cfg = settings.doc_corpus
    if not cfg.OPENAI_API_KEY:
        logger.warning("doc_corpus_retrieval_skipped", reason="OPENAI_API_KEY unset")
        return "", []
    q = query.strip()
    if not q:
        return "", []
    try:
        async with get_metadata_session_maker()() as session:
            vectors = await embed_texts_openai(
                texts=[q],
                model=cfg.DOCS_EMBED_MODEL,
                api_key=cfg.OPENAI_API_KEY,
            )
            if not vectors or len(vectors[0]) != cfg.DOCS_EMBED_DIMENSIONS:
                logger.warning("doc_corpus_retrieval_bad_embedding_shape")
                return "", []
            hits = await search_doc_chunks(
                session,
                collection_key=collection_key,
                query_embedding=vectors[0],
                limit=limit,
                applications=applications,
            )
    except (RuntimeError, SQLAlchemyError, OSError, ValueError, OpenAIError) as e:
        logger.warning("doc_corpus_retrieval_failed", error=str(e))
        return "", []

    block = format_doc_corpus_hits_for_prompt(hits)
    hit_titles = [h.page_title or "(no title)" for h in hits]
    logger.info(
        "doc_corpus_retrieval_ok",
        hit_count=len(hits),
        char_count=len(block),
        hit_titles=hit_titles,
    )
    return block, hit_titles


def cosine_distance_row(left: list[float], right: list[float]) -> float:
    """Compute cosine distance (1 - cosine similarity) for equal-length vectors."""
    if len(left) != len(right):
        raise ValueError("embedding dimension mismatch")
    dot = 0.0
    n_left = 0.0
    n_right = 0.0
    for a, b in zip(left, right, strict=True):
        dot += float(a) * float(b)
        n_left += float(a) * float(a)
        n_right += float(b) * float(b)
    denom = math.sqrt(n_left) * math.sqrt(n_right)
    if denom == 0.0:
        return 1.0
    similarity = dot / denom
    return 1.0 - similarity


def _distance_to_similarity(distance: float) -> float:
    """Map pgvector cosine distance to a bounded similarity score in (0, 1]."""
    # cosine distance is in [0, 2] for normalized embeddings; clamp for safety
    d = min(max(distance, 0.0), 2.0)
    return max(0.0, 1.0 - d / 2.0)


async def ingest_documentation_source(
    session: AsyncSession,
    *,
    source_url: str,
) -> tuple[int, int, list[str | None]]:
    """Crawl ``source_url`` with Firecrawl (multi-page), chunk, embed, and persist rows.

    All existing rows for this application and collection are removed before new data is written.

    Returns:
        ``(pages crawled, chunk rows inserted, page_title per row)``.
    """
    cfg = settings.doc_corpus
    if not cfg.FIRECRAWL_API_KEY:
        raise ValueError("FIRECRAWL_API_KEY is not configured")
    if not cfg.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured")

    application = _DOC_INGEST_APPLICATION
    collection_key = _DOC_INGEST_COLLECTION_KEY

    await session.execute(
        delete(DocEmbeddingChunk).where(
            DocEmbeddingChunk.application == application,
            DocEmbeddingChunk.collection_key == collection_key,
        )
    )
    await session.commit()

    pages_seen = 0
    chunks_written = 0
    row_titles: list[str | None] = []

    async with httpx.AsyncClient() as http_client:
        crawl_id = await _firecrawl_start_crawl(
            http_client,
            api_key=cfg.FIRECRAWL_API_KEY,
            base_url=cfg.FIRECRAWL_BASE_URL,
            start_url=source_url,
            limit=cfg.DOCS_CRAWL_PAGE_LIMIT,
        )
        async for source_page_url, markdown, fire_meta in _firecrawl_iter_crawl_pages(
            http_client,
            api_key=cfg.FIRECRAWL_API_KEY,
            base_url=cfg.FIRECRAWL_BASE_URL,
            crawl_id=crawl_id,
            poll_interval=cfg.DOCS_CRAWL_POLL_INTERVAL_SEC,
            max_wait=cfg.DOCS_CRAWL_MAX_WAIT_SEC,
        ):
            pages_seen += 1
            page_title = _metadata_page_title(fire_meta)
            key_url = source_page_url if source_page_url.strip() else source_url

            chunks = split_text_into_chunks(
                markdown,
                max_chars=cfg.DOCS_CHUNK_MAX_CHARS,
                overlap_chars=cfg.DOCS_CHUNK_OVERLAP_CHARS,
            )
            if not chunks:
                logger.warning(
                    "docs_corpus_empty_page",
                    url=key_url,
                    application=application,
                    collection_key=collection_key,
                )
                continue

            embeddings = await embed_texts_openai(
                texts=chunks,
                model=cfg.DOCS_EMBED_MODEL,
                api_key=cfg.OPENAI_API_KEY,
            )
            if len(embeddings) != len(chunks):
                raise RuntimeError("embedding count does not match chunk count")

            for idx, (text_chunk, vector) in enumerate(zip(chunks, embeddings, strict=True)):
                if len(vector) != cfg.DOCS_EMBED_DIMENSIONS:
                    raise ValueError("unexpected embedding size from OpenAI")
                metadata = {"firecrawl_metadata": fire_meta}
                session.add(
                    DocEmbeddingChunk(
                        application=application,
                        collection_key=collection_key,
                        source_url=key_url,
                        page_title=page_title,
                        chunk_index=idx,
                        content=text_chunk,
                        metadata_dict=metadata,
                        embedding=vector,
                    )
                )
                row_titles.append(page_title)

            chunks_written += len(chunks)

    await session.commit()
    return pages_seen, chunks_written, row_titles
