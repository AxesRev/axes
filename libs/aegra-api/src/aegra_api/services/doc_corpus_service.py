"""Search ingested documentation using OpenAI embeddings and pgvector.

App-specific ingest CLIs live under ``app_integrations`` (e.g. GitHub zip, Salesforce PDF).
There is no public HTTP API for corpus ingest or search helpers.
"""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import Sequence

import structlog
from openai import APIConnectionError, AsyncOpenAI, InternalServerError, OpenAIError, RateLimitError
from sqlalchemy import select
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
