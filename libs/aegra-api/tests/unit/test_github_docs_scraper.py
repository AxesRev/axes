"""Unit tests for GitHub docs scraper (delegates to ``scrape_url_markdown``)."""

import pytest

from app_integrations.github.scraper import GITHUB_DOCS_SCRAPE_URL, scrape_github_docs


@pytest.mark.asyncio
async def test_scrape_github_docs_calls_shared_scraper(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_scrape(
        client: object,
        *,
        api_key: str,
        base_url: str,
        url: str,
        timeout_seconds: float = 120.0,
    ) -> tuple[str, dict[str, str]]:
        captured["api_key"] = api_key
        captured["base_url"] = base_url
        captured["url"] = url
        captured["timeout_seconds"] = timeout_seconds
        return ("# md", {"title": "t"})

    monkeypatch.setattr(
        "app_integrations.github.scraper.scrape_url_markdown",
        fake_scrape,
    )

    markdown, meta = await scrape_github_docs(
        api_key="k", base_url="https://api.firecrawl.dev/v2", timeout_seconds=30.0
    )

    assert markdown == "# md"
    assert meta["title"] == "t"
    assert captured["url"] == GITHUB_DOCS_SCRAPE_URL
    assert captured["api_key"] == "k"
    assert captured["base_url"] == "https://api.firecrawl.dev/v2"
    assert captured["timeout_seconds"] == 30.0


def test_github_docs_scrape_url_is_fixed() -> None:
    assert GITHUB_DOCS_SCRAPE_URL == "https://docs.github.com/en"
