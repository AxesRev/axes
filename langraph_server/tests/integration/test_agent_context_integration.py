"""Integration tests for tenant agent context API."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slack_app.auth0 import require_auth0_claims

from aegra_api.core.orm import get_session
from tenant.models import Tenant, TenantAgentContext
from tenant.routes import router as tenant_router


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
def test_get_my_agent_context_requires_auth() -> None:
    client = FastAPI()
    client.include_router(tenant_router)
    unauthenticated = TestClient(client)
    response = unauthenticated.get("/tenants/me/agent-context")
    assert response.status_code == 401


@pytest.mark.integration
def test_get_my_agent_context_returns_empty_when_missing(tenant_api_client: TestClient) -> None:
    response = tenant_api_client.get("/tenants/me/agent-context")
    assert response.status_code == 200
    assert response.json() == {"content": "", "updated_at": None}


@pytest.mark.integration
def test_get_my_agent_context_returns_saved_content(
    tenant_api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = Tenant(id="tenant-new", name="Owner", email="owner@example.com", auth0_sub="auth0|123")
    updated_at = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
    context = TenantAgentContext(
        tenant_id="tenant-new",
        content="Always greet users by name.",
        updated_at=updated_at,
    )

    async def fake_get_or_create(**kwargs: object) -> Tenant:
        return tenant

    async def fake_get_context(**kwargs: object) -> TenantAgentContext:
        return context

    monkeypatch.setattr("tenant.routes.get_or_create_tenant_for_auth_user", fake_get_or_create)
    monkeypatch.setattr("tenant.routes.get_agent_context_for_tenant", fake_get_context)

    response = tenant_api_client.get("/tenants/me/agent-context")
    assert response.status_code == 200
    payload = response.json()
    assert payload["content"] == "Always greet users by name."
    assert payload["updated_at"] is not None


@pytest.mark.integration
def test_update_my_agent_context_requires_auth() -> None:
    client = FastAPI()
    client.include_router(tenant_router)
    unauthenticated = TestClient(client)
    response = unauthenticated.put("/tenants/me/agent-context", json={"content": "Hello"})
    assert response.status_code == 401


@pytest.mark.integration
def test_update_my_agent_context_saves_content(
    tenant_api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = Tenant(id="tenant-new", name="Owner", email="owner@example.com", auth0_sub="auth0|123")
    updated_at = datetime(2026, 7, 10, 12, 30, tzinfo=UTC)
    saved = TenantAgentContext(
        tenant_id="tenant-new",
        content="Saved instructions",
        updated_at=updated_at,
    )

    async def fake_get_or_create(**kwargs: object) -> Tenant:
        return tenant

    async def fake_upsert(**kwargs: object) -> TenantAgentContext:
        return saved

    monkeypatch.setattr("tenant.routes.get_or_create_tenant_for_auth_user", fake_get_or_create)
    monkeypatch.setattr("tenant.routes.upsert_agent_context_for_tenant", fake_upsert)

    response = tenant_api_client.put("/tenants/me/agent-context", json={"content": "Saved instructions"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["content"] == "Saved instructions"
    assert payload["updated_at"] is not None
