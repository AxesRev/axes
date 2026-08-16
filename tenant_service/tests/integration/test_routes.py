"""Integration tests for tenant Lambda HTTP handler."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from common.models import AppIntegration, Tenant, TenantAgentContext
from tenants.app import handler
from tenants.errors import HttpError

CLAIMS = {"sub": "auth0|123", "email": "owner@example.com", "name": "Owner"}


def _event(*, method: str, path: str, headers: dict[str, str] | None = None, body: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "rawPath": path,
        "requestContext": {"http": {"method": method}},
        "headers": headers or {},
        "isBase64Encoded": False,
    }
    if body is not None:
        payload["body"] = body
    return payload


def _invoke(**kwargs: Any) -> tuple[int, object]:
    response = handler(_event(**kwargs), None)
    return int(response["statusCode"]), json.loads(str(response["body"]))


@pytest.fixture
def tenant_session(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    session = AsyncMock()

    @asynccontextmanager
    async def fake_session() -> Any:
        yield session

    async def fake_with_session() -> Any:
        return fake_session()

    monkeypatch.setattr("tenants.app._with_session", fake_with_session)
    monkeypatch.setattr("tenants.app.claims_from_bearer", lambda _auth: CLAIMS)
    return session


@pytest.mark.integration
def test_health() -> None:
    status_code, payload = _invoke(method="GET", path="/health")
    assert status_code == 200
    assert payload == {"status": "healthy", "service": "tenant"}


@pytest.mark.integration
def test_get_my_tenant_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(_auth: str | None) -> dict[str, object]:
        raise HttpError(401, "Missing bearer token")

    monkeypatch.setattr("tenants.app.claims_from_bearer", reject)
    status_code, payload = _invoke(method="GET", path="/tenants/me")
    assert status_code == 401
    assert payload["detail"] == "Missing bearer token"


@pytest.mark.integration
def test_get_my_tenant_returns_tenant(tenant_session: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
    tenant = Tenant(id="tenant-new", name="Owner", email="owner@example.com", auth0_sub="auth0|123")

    async def fake_get_or_create(**kwargs: object) -> Tenant:
        return tenant

    monkeypatch.setattr("tenants.routes.tenant_from_claims", fake_get_or_create)
    status_code, payload = _invoke(method="GET", path="/tenants/me", headers={"Authorization": "Bearer token"})
    assert status_code == 200
    assert payload == {"id": "tenant-new", "name": "Owner", "email": "owner@example.com"}


@pytest.mark.integration
def test_get_my_integrations_returns_slack(tenant_session: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
    tenant = Tenant(id="tenant-new", name="Owner", email="owner@example.com", auth0_sub="auth0|123")
    integration = AppIntegration(
        id="int-1",
        tenant_id="tenant-new",
        app_name="slack",
        config={"team_id": "T01234567"},
    )

    async def fake_get_or_create(**kwargs: object) -> Tenant:
        return tenant

    execute_result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = [integration]
    execute_result.scalars.return_value = scalars
    tenant_session.execute = AsyncMock(return_value=execute_result)
    monkeypatch.setattr("tenants.routes.tenant_from_claims", fake_get_or_create)

    status_code, payload = _invoke(
        method="GET",
        path="/tenants/me/integrations",
        headers={"Authorization": "Bearer token"},
    )
    assert status_code == 200
    assert payload == [{"id": "int-1", "app_name": "slack", "config": {"team_id": "T01234567"}}]


@pytest.mark.integration
def test_get_my_agent_context_returns_empty_when_missing(
    tenant_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = Tenant(id="tenant-new", name="Owner", email="owner@example.com", auth0_sub="auth0|123")

    async def fake_get_or_create(**kwargs: object) -> Tenant:
        return tenant

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    tenant_session.execute = AsyncMock(return_value=execute_result)
    monkeypatch.setattr("tenants.routes.tenant_from_claims", fake_get_or_create)

    status_code, payload = _invoke(
        method="GET",
        path="/tenants/me/agent-context",
        headers={"Authorization": "Bearer token"},
    )
    assert status_code == 200
    assert payload == {"content": "", "updated_at": None}


@pytest.mark.integration
def test_update_my_agent_context_saves_content(tenant_session: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
    tenant = Tenant(id="tenant-new", name="Owner", email="owner@example.com", auth0_sub="auth0|123")
    saved = TenantAgentContext(
        tenant_id="tenant-new",
        content="Saved instructions",
        updated_at=datetime(2026, 7, 10, 12, 30, tzinfo=UTC),
    )

    async def fake_get_or_create(**kwargs: object) -> Tenant:
        return tenant

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    tenant_session.execute = AsyncMock(return_value=execute_result)
    tenant_session.add = MagicMock()
    tenant_session.commit = AsyncMock()

    async def fake_refresh(row: TenantAgentContext) -> None:
        row.content = saved.content
        row.updated_at = saved.updated_at

    tenant_session.refresh = AsyncMock(side_effect=fake_refresh)
    monkeypatch.setattr("tenants.routes.tenant_from_claims", fake_get_or_create)

    status_code, payload = _invoke(
        method="PUT",
        path="/tenants/me/agent-context",
        headers={"Authorization": "Bearer token"},
        body=json.dumps({"content": "Saved instructions"}),
    )
    assert status_code == 200
    assert payload["content"] == "Saved instructions"
    assert payload["updated_at"] is not None
