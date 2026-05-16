"""Integration-style tests for /docs-corpus routes (mocked ingestion)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.api.doc_corpus import router as doc_corpus_router
from aegra_api.core.auth_deps import require_auth
from aegra_api.core.orm import get_session
from aegra_api.models.auth import User


@pytest.fixture
def doc_corpus_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    app = FastAPI()
    mock_user = User(identity="test-user", display_name="Test User")
    app.dependency_overrides[require_auth] = lambda: mock_user

    monkeypatch.setattr(
        "aegra_api.api.doc_corpus.settings.doc_corpus",
        SimpleNamespace(
            OPENAI_API_KEY="sk-test",
            DOCS_EMBED_MODEL="text-embedding-3-small",
            DOCS_EMBED_DIMENSIONS=1536,
        ),
    )

    dummy_session = AsyncMock(spec=AsyncSession)

    async def _fake_ingest(*_args, **_kwargs) -> tuple[int, int]:
        return 1, 3

    async def _fake_search(*_args, **_kwargs):
        from aegra_api.models.doc_corpus import DocCorpusSearchHit

        return [
            DocCorpusSearchHit(
                application="axes",
                source_url="https://example.com/doc",
                page_title="Doc",
                chunk_index=0,
                content="hello",
                score=0.9,
            )
        ]

    monkeypatch.setattr(
        "aegra_api.api.doc_corpus.ingest_doc_urls_for_collection",
        _fake_ingest,
    )
    monkeypatch.setattr(
        "aegra_api.api.doc_corpus.search_doc_chunks",
        _fake_search,
    )
    monkeypatch.setattr(
        "aegra_api.api.doc_corpus.embed_texts_openai",
        AsyncMock(return_value=[[0.1] * 1536]),
    )

    async def _session_dep() -> AsyncMock:
        yield dummy_session

    app.dependency_overrides[get_session] = _session_dep
    app.include_router(doc_corpus_router)
    return TestClient(app)


def test_ingest_endpoint_returns_counts(doc_corpus_client: TestClient) -> None:
    response = doc_corpus_client.post(
        "/docs-corpus/ingest",
        json={
            "application": "axes",
            "collection_key": "langchain",
            "urls": ["https://docs.example.com/page"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["urls_processed"] == 1
    assert body["chunks_written"] == 3


def test_search_endpoint_returns_hits(doc_corpus_client: TestClient) -> None:
    response = doc_corpus_client.post(
        "/docs-corpus/search",
        json={
            "application": "axes",
            "collection_key": "langchain",
            "query": "how to use tools",
            "limit": 5,
        },
    )
    assert response.status_code == 200
    hits = response.json()["hits"]
    assert len(hits) == 1
    assert hits[0]["source_url"] == "https://example.com/doc"
