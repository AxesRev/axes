"""Pydantic models for documentation corpus ingest and search APIs."""

from pydantic import BaseModel, Field


class DocCorpusIngestRequest(BaseModel):
    """Request body for crawling URLs into a named documentation collection."""

    application: str = Field(min_length=1, max_length=256)
    collection_key: str = Field(min_length=1, max_length=256)
    urls: list[str] = Field(min_length=1, max_length=50)


class DocCorpusIngestResponse(BaseModel):
    urls_processed: int
    chunks_written: int


class DocCorpusSearchRequest(BaseModel):
    """Semantic search over an embedded documentation collection."""

    application: str = Field(min_length=1, max_length=256)
    collection_key: str = Field(min_length=1, max_length=256)
    query: str = Field(min_length=1, max_length=8000)
    limit: int = Field(default=8, ge=1, le=50)


class DocCorpusSearchHit(BaseModel):
    application: str
    source_url: str
    page_title: str | None
    chunk_index: int
    content: str
    score: float


class DocCorpusSearchResponse(BaseModel):
    hits: list[DocCorpusSearchHit]
