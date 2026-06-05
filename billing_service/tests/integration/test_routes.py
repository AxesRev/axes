"""Integration tests for tenant billing routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aegra_api.core.orm import get_session
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slack_app.auth0 import require_auth0_claims

from billing.routes import router as billing_router


@pytest.fixture
def billing_api_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("slack_app.config.slack_settings.AUTH0_DOMAIN", "dev-example.us.auth0.com")
    monkeypatch.setattr("slack_app.config.slack_settings.AUTH0_CLIENT_ID", "test-client-id")
    monkeypatch.setattr("billing.config.billing_settings.PADDLE_API_KEY", "test_sdbx_key")

    app = FastAPI()
    app.include_router(billing_router)

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
def test_get_my_tenant_billing_requires_auth() -> None:
    app = FastAPI()
    app.include_router(billing_router)
    response = TestClient(app).get("/tenants/me/billing")
    assert response.status_code == 401


@pytest.mark.integration
def test_get_my_tenant_billing_returns_not_setup(
    billing_api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app_integrations.github.models import Tenant

    from billing.schemas import TenantBillingStatusResponse

    tenant = Tenant(
        id="tenant-new",
        name="Owner",
        email="owner@example.com",
        auth0_sub="auth0|123",
    )

    async def fake_get_or_create(**kwargs: object) -> Tenant:
        return tenant

    async def fake_status(**kwargs: object) -> TenantBillingStatusResponse:
        return TenantBillingStatusResponse(
            billing_setup=False,
            paddle_customer_id=None,
            paddle_subscription_id=None,
            subscription_status=None,
        )

    monkeypatch.setattr("billing.routes.get_or_create_tenant_for_auth_user", fake_get_or_create)
    monkeypatch.setattr("billing.routes.get_tenant_billing_status", fake_status)

    response = billing_api_client.get("/tenants/me/billing")
    assert response.status_code == 200
    assert response.json() == {
        "billing_setup": False,
        "paddle_customer_id": None,
        "paddle_subscription_id": None,
        "subscription_status": None,
    }
