"""Firecrawl-backed scraper for GitHub Docs (delegates to ``doc_corpus_service``)."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from aegra_api.services.doc_corpus_service import scrape_url_markdown
from app_integrations.github.settings import github_settings

logger = structlog.get_logger(__name__)

# English docs root — Firecrawl scrape target (fixed).
GITHUB_DOCS_SCRAPE_URL = "https://docs.github.com/en"


async def scrape_github_docs(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout_seconds: float = 120.0,
) -> tuple[str, dict[str, Any]]:
    """Scrape ``GITHUB_DOCS_SCRAPE_URL`` as markdown via Firecrawl."""
    key = api_key if api_key is not None else github_settings.FIRECRAWL_API_KEY
    if not key.strip():
        raise ValueError("FIRECRAWL_API_KEY is not configured")

    api_base = (base_url if base_url is not None else github_settings.FIRECRAWL_BASE_URL).rstrip("/")

    async with httpx.AsyncClient() as client:
        markdown, metadata = await scrape_url_markdown(
            client,
            api_key=key.strip(),
            base_url=api_base,
            url=GITHUB_DOCS_SCRAPE_URL,
            timeout_seconds=timeout_seconds,
        )

    logger.info(
        "github_docs_scrape_ok",
        url=GITHUB_DOCS_SCRAPE_URL,
        markdown_chars=len(markdown),
        title=metadata.get("title"),
    )
    return markdown, metadata
