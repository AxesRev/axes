"""Integration tests for GitHub App installation routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aegra_api.core.orm import get_session
from app_integrations.github.models import Tenant
from app_integrations.github.router import router as github_app_router


@pytest.fixture
def github_app_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("app_integrations.github.settings.github_settings.GITHUB_APP_SLUG", "axes-test-app")
    monkeypatch.setattr(
        "app_integrations.github.settings.github_settings.GITHUB_INSTALL_STATE_SECRET",
        "integration-test-secret",
    )
    monkeypatch.setattr("app_integrations.github.settings.github_settings.WEBAPP_URL", "http://localhost:3000")

    app = FastAPI()
    app.include_router(github_app_router)

    async def override_session() -> AsyncMock:
        session = AsyncMock()
        tenant = Tenant(id="tenant-1", name="Acme")
        tenant_result = MagicMock()
        tenant_result.scalar_one_or_none.return_value = tenant
        empty_result = MagicMock()
        empty_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(side_effect=[tenant_result, empty_result, empty_result])
        session.commit = AsyncMock()
        session.add = MagicMock()
        yield session

    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


@pytest.mark.integration
def test_github_app_install_redirects_to_github(github_app_client: TestClient) -> None:
    response = github_app_client.get("/auth/github/install?tenant_id=tenant-1", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("https://github.com/apps/axes-test-app/installations/new?state=")


@pytest.mark.integration
def test_github_app_install_returns_404_for_unknown_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    app.include_router(github_app_router)

    async def override_session() -> AsyncMock:
        session = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=execute_result)
        yield session

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)

    response = client.get("/auth/github/install?tenant_id=missing")
    assert response.status_code == 404


@pytest.mark.integration
def test_github_app_callback_persists_installation(github_app_client: TestClient) -> None:
    install_response = github_app_client.get("/auth/github/install?tenant_id=tenant-1", follow_redirects=False)
    state = install_response.headers["location"].split("state=", 1)[1]

    callback_response = github_app_client.get(
        f"/auth/github/callback?installation_id=98765&setup_action=install&state={state}"
    )

    assert callback_response.status_code == 200
    assert "98765" in callback_response.text
    assert "Return to Axes" in callback_response.text


@pytest.mark.integration
def test_github_app_callback_requires_state(github_app_client: TestClient) -> None:
    response = github_app_client.get("/auth/github/callback?installation_id=98765&setup_action=install")
    assert response.status_code == 400
