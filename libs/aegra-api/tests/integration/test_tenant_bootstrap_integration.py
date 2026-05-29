"""Integration tests for Auth0-secured tenant API on slack_app."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slack_app.auth0 import require_auth0_claims
from slack_app.tenant_routes import router as tenant_router

from aegra_api.core.orm import get_session


@pytest.fixture
def tenant_api_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("slack_app.config.slack_settings.AUTH0_DOMAIN", "dev-example.us.auth0.com")
    monkeypatch.setattr("slack_app.config.slack_settings.AUTH0_CLIENT_ID", "test-client-id")

    app = FastAPI()
    app.include_router(tenant_router)

    async def override_session() -> AsyncMock:
        session = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=execute_result)
        session.commit = AsyncMock()
        session.refresh = AsyncMock(side_effect=lambda tenant: setattr(tenant, "id", "tenant-new"))
        session.add = MagicMock()
        yield session

    async def override_claims() -> dict[str, str]:
        return {
            "sub": "auth0|123",
            "email": "owner@example.com",
            "name": "Owner",
        }

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_auth0_claims] = override_claims
    return TestClient(app)


@pytest.mark.integration
def test_get_my_tenant_requires_auth() -> None:
    client = FastAPI()
    client.include_router(tenant_router)
    unauthenticated = TestClient(client)
    response = unauthenticated.get("/tenants/me")
    assert response.status_code == 401


@pytest.mark.integration
def test_get_my_tenant_provisions_tenant(tenant_api_client: TestClient) -> None:
    response = tenant_api_client.get("/tenants/me")
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "tenant-new"
    assert payload["name"] == "Owner"
    assert payload["email"] == "owner@example.com"


@pytest.mark.integration
def test_get_my_app_integrations_requires_auth() -> None:
    client = FastAPI()
    client.include_router(tenant_router)
    unauthenticated = TestClient(client)
    response = unauthenticated.get("/tenants/me/integrations")
    assert response.status_code == 401


@pytest.mark.integration
def test_get_my_app_integrations_returns_slack_integration(
    tenant_api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_integrations.github.models import AppIntegration, Tenant

    tenant = Tenant(id="tenant-new", name="Owner", email="owner@example.com", auth0_sub="auth0|123")
    integration = AppIntegration(
        id="int-1",
        tenant_id="tenant-new",
        app_name="slack",
        config={"team_id": "T01234567"},
    )

    async def fake_get_or_create(**kwargs: object) -> Tenant:
        return tenant

    async def fake_list(**kwargs: object) -> list[AppIntegration]:
        return [integration]

    monkeypatch.setattr("slack_app.tenant_routes.get_or_create_tenant_for_auth_user", fake_get_or_create)
    monkeypatch.setattr("slack_app.tenant_routes.list_app_integrations_for_tenant", fake_list)

    response = tenant_api_client.get("/tenants/me/integrations")
    assert response.status_code == 200
    payload = response.json()
    assert payload == [
        {
            "id": "int-1",
            "app_name": "slack",
            "config": {"team_id": "T01234567"},
        }
    ]
