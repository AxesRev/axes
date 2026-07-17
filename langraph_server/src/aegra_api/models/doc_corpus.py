"""Types for documentation corpus search results (internal service use, not HTTP API)."""

from pydantic import BaseModel


class DocCorpusSearchHit(BaseModel):
    application: str
    page_title: str | None
    content: str
    score: float
