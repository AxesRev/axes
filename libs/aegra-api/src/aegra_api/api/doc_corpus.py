"""HTTP routes for documentation corpus ingest and semantic search."""

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAIError
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.core.auth_deps import require_auth
from aegra_api.core.orm import get_session
from aegra_api.models.auth import User
from aegra_api.models.doc_corpus import (
    DocCorpusIngestRequest,
    DocCorpusIngestResponse,
    DocCorpusSearchRequest,
    DocCorpusSearchResponse,
)
from aegra_api.services.doc_corpus_service import (
    embed_texts_openai,
    ingest_doc_urls_for_collection,
    search_doc_chunks,
)
from aegra_api.settings import settings

router = APIRouter(prefix="/docs-corpus", tags=["docs-corpus"])


@router.post("/ingest", response_model=DocCorpusIngestResponse)
async def ingest_documentation_corpus(
    body: DocCorpusIngestRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_auth)],
) -> DocCorpusIngestResponse:
    """Scrape ``urls`` with Firecrawl, embed with OpenAI, and upsert pgvector rows."""
    try:
        urls_processed, chunks_written = await ingest_doc_urls_for_collection(
            session,
            application=body.application,
            collection_key=body.collection_key,
            urls=body.urls,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OpenAIError as e:
        raise HTTPException(status_code=502, detail=f"Embedding request failed: {e!s}") from e
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Firecrawl request failed: {e!s}",
        ) from e

    return DocCorpusIngestResponse(urls_processed=urls_processed, chunks_written=chunks_written)


@router.post("/search", response_model=DocCorpusSearchResponse)
async def search_documentation_corpus(
    body: DocCorpusSearchRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_auth)],
) -> DocCorpusSearchResponse:
    """Semantic search over one documentation collection (cosine similarity)."""
    cfg = settings.doc_corpus
    if not cfg.OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured")

    try:
        vectors = await embed_texts_openai(
            texts=[body.query],
            model=cfg.DOCS_EMBED_MODEL,
            api_key=cfg.OPENAI_API_KEY,
        )
    except OpenAIError as e:
        raise HTTPException(status_code=502, detail=f"Embedding request failed: {e!s}") from e

    if not vectors or len(vectors[0]) != cfg.DOCS_EMBED_DIMENSIONS:
        raise HTTPException(status_code=502, detail="Unexpected embedding response size")

    hits = await search_doc_chunks(
        session,
        application=body.application,
        collection_key=body.collection_key,
        query_embedding=vectors[0],
        limit=body.limit,
    )
    return DocCorpusSearchResponse(hits=hits)
