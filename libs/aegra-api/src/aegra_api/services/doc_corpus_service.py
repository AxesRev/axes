"""Ingest and search crawled documentation using Firecrawl, OpenAI embeddings, and pgvector.

Call ``ingest_doc_urls_for_collection`` and ``search_doc_chunks`` (plus ``embed_texts_openai``
when embedding a query string) from application code — there is no public HTTP API for this.
"""

from __future__ import annotations

import math
from typing import Any

import httpx
import structlog
from openai import AsyncOpenAI, OpenAIError
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.core.orm import DocEmbeddingChunk, get_metadata_session_maker
from aegra_api.models.doc_corpus import DocCorpusSearchHit
from aegra_api.settings import settings

logger = structlog.get_logger(__name__)

_DEFAULT_EMBED_BATCH = 64


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
    timeout_seconds: float = 120.0,
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
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return parse_firecrawl_scrape_payload(response.json())


async def embed_texts_openai(*, texts: list[str], model: str, api_key: str) -> list[list[float]]:
    """Return embedding vectors for each input string using the OpenAI API."""
    if not texts:
        return []

    client = AsyncOpenAI(api_key=api_key)
    out: list[list[float]] = []
    for start in range(0, len(texts), _DEFAULT_EMBED_BATCH):
        batch = texts[start : start + _DEFAULT_EMBED_BATCH]
        result = await client.embeddings.create(model=model, input=batch)
        for item in result.data:
            out.append(list(item.embedding))
    return out


async def search_doc_chunks(
    session: AsyncSession,
    *,
    collection_key: str,
    query_embedding: list[float],
    limit: int,
) -> list[DocCorpusSearchHit]:
    """Cosine-distance search over stored documentation chunks (all ``application`` values)."""
    stmt = (
        select(DocEmbeddingChunk)
        .where(DocEmbeddingChunk.collection_key == collection_key)
        .order_by(DocEmbeddingChunk.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
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
) -> str:
    """Embed ``query``, cosine-search ``doc_embedding_chunks``, return formatted text."""
    cfg = settings.doc_corpus
    if not cfg.OPENAI_API_KEY:
        logger.warning("doc_corpus_retrieval_skipped", reason="OPENAI_API_KEY unset")
        return ""
    q = query.strip()
    if not q:
        return ""
    try:
        async with get_metadata_session_maker()() as session:
            vectors = await embed_texts_openai(
                texts=[q],
                model=cfg.DOCS_EMBED_MODEL,
                api_key=cfg.OPENAI_API_KEY,
            )
            if not vectors or len(vectors[0]) != cfg.DOCS_EMBED_DIMENSIONS:
                logger.warning("doc_corpus_retrieval_bad_embedding_shape")
                return ""
            hits = await search_doc_chunks(
                session,
                collection_key=collection_key,
                query_embedding=vectors[0],
                limit=limit,
            )
    except (RuntimeError, SQLAlchemyError, OSError, ValueError, OpenAIError) as e:
        logger.warning("doc_corpus_retrieval_failed", error=str(e))
        return ""

    block = format_doc_corpus_hits_for_prompt(hits)
    logger.info("doc_corpus_retrieval_ok", hit_count=len(hits), char_count=len(block))
    return block


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


async def ingest_doc_urls_for_collection(
    session: AsyncSession,
    *,
    application: str,
    collection_key: str,
    urls: list[str],
) -> tuple[int, int]:
    """Crawl URLs, chunk, embed, and persist rows for ``application`` + ``collection_key``.

    Returns:
        Tuple of (number of URLs processed, number of chunk rows inserted).
    """
    cfg = settings.doc_corpus
    if not cfg.FIRECRAWL_API_KEY:
        raise ValueError("FIRECRAWL_API_KEY is not configured")
    if not cfg.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured")
    if cfg.DOCS_EMBED_DIMENSIONS != 1536:
        raise ValueError("DOCS_EMBED_DIMENSIONS must be 1536 for the current schema")

    urls_seen = 0
    chunks_written = 0

    async with httpx.AsyncClient() as http_client:
        for source_url in urls:
            markdown, fire_meta = await scrape_url_markdown(
                http_client,
                api_key=cfg.FIRECRAWL_API_KEY,
                base_url=cfg.FIRECRAWL_BASE_URL,
                url=source_url,
            )
            title_val = fire_meta.get("title")
            page_title = str(title_val) if title_val is not None else None

            chunks = split_text_into_chunks(
                markdown,
                max_chars=cfg.DOCS_CHUNK_MAX_CHARS,
                overlap_chars=cfg.DOCS_CHUNK_OVERLAP_CHARS,
            )
            if not chunks:
                logger.warning(
                    "docs_corpus_empty_page",
                    url=source_url,
                    application=application,
                    collection_key=collection_key,
                )
                await session.execute(
                    delete(DocEmbeddingChunk).where(
                        DocEmbeddingChunk.application == application,
                        DocEmbeddingChunk.collection_key == collection_key,
                        DocEmbeddingChunk.source_url == source_url,
                    )
                )
                urls_seen += 1
                continue

            embeddings = await embed_texts_openai(
                texts=chunks,
                model=cfg.DOCS_EMBED_MODEL,
                api_key=cfg.OPENAI_API_KEY,
            )
            if len(embeddings) != len(chunks):
                raise RuntimeError("embedding count does not match chunk count")

            await session.execute(
                delete(DocEmbeddingChunk).where(
                    DocEmbeddingChunk.application == application,
                    DocEmbeddingChunk.collection_key == collection_key,
                    DocEmbeddingChunk.source_url == source_url,
                )
            )

            for idx, (text_chunk, vector) in enumerate(zip(chunks, embeddings, strict=True)):
                if len(vector) != cfg.DOCS_EMBED_DIMENSIONS:
                    raise ValueError("unexpected embedding size from OpenAI")
                metadata = {
                    "firecrawl_metadata": fire_meta,
                }
                session.add(
                    DocEmbeddingChunk(
                        application=application,
                        collection_key=collection_key,
                        source_url=source_url,
                        page_title=page_title,
                        chunk_index=idx,
                        content=text_chunk,
                        metadata_dict=metadata,
                        embedding=vector,
                    )
                )
                chunks_written += 1

            urls_seen += 1

    await session.commit()
    return urls_seen, chunks_written
