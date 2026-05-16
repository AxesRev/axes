"""Types for documentation corpus search results (internal service use, not HTTP API)."""

from pydantic import BaseModel


class DocCorpusSearchHit(BaseModel):
    application: str
    source_url: str
    page_title: str | None
    chunk_index: int
    content: str
    score: float
