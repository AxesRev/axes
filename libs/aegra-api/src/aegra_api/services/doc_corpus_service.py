"""Ingest and search crawled documentation using Firecrawl, OpenAI embeddings, and pgvector.

Use ``ingest_documentation_source`` to crawl a site (Firecrawl v2 ``/crawl``), embed chunks, and write ``doc_embedding_chunks``.
GitHub zip ingestion lives in ``app_integrations.github.doc_generation.zip_embedder``.
There is no public HTTP API for corpus ingest or search helpers.
"""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx
import structlog
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
