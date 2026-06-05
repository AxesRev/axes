"""Integration tests for Slack → GitHub OAuth linking routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aegra_api.core.orm import get_session
from app_integrations.github.models import OAuthState
from app_integrations.github.router import router as github_app_router


@pytest.fixture
def oauth_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("app_integrations.github.settings.github_settings.GITHUB_CLIENT_ID", "client-id")
    monkeypatch.setattr("app_integrations.github.settings.github_settings.GITHUB_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(
        "app_integrations.github.settings.github_settings.GITHUB_OAUTH_STATE_SECRET",
        "oauth-state-secret",
    )
    monkeypatch.setattr("app_integrations.github.settings.github_settings.SERVER_URL", "http://localhost:8000")

    app = FastAPI()
    app.include_router(github_app_router)

    oauth_state = OAuthState(
        token="link-token",
        slack_user_id="U123",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    async def override_session() -> AsyncMock:
        session = AsyncMock()
        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = oauth_state
        session.execute = AsyncMock(return_value=state_result)
        session.commit = AsyncMock()
        yield session

    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


@pytest.mark.integration
def test_github_oauth_start_redirects_to_github(oauth_client: TestClient) -> None:
    response = oauth_client.get("/auth/github/start?token=link-token", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    assert "github.com/login/oauth/authorize" in location
    assert "client_id=client-id" in location
    assert "state=" in location


@pytest.mark.integration
def test_github_oauth_start_rejects_unknown_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app_integrations.github.settings.github_settings.GITHUB_CLIENT_ID", "client-id")
    monkeypatch.setattr(
        "app_integrations.github.settings.github_settings.GITHUB_OAUTH_STATE_SECRET",
        "oauth-state-secret",
    )

    app = FastAPI()
    app.include_router(github_app_router)

    async def override_session() -> AsyncMock:
        session = AsyncMock()
        empty = MagicMock()
        empty.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=empty)
        yield session

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)

    response = client.get("/auth/github/start?token=bad")
    assert response.status_code == 400
