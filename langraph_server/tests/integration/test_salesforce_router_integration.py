"""Integration tests for Salesforce package install routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aegra_api.core.orm import get_session
from app_integrations.salesforce.router import router as salesforce_router
from tenant.models import Tenant


@pytest.fixture
def salesforce_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        "app_integrations.salesforce.settings.salesforce_settings.SALESFORCE_PACKAGE_VERSION_ID",
        "04tg50000008CgjAAE",
    )
    monkeypatch.setattr(
        "app_integrations.salesforce.settings.salesforce_settings.SALESFORCE_INSTALL_STATE_SECRET",
        "integration-test-secret",
    )
    monkeypatch.setattr(
        "app_integrations.salesforce.settings.salesforce_settings.SERVER_URL",
        "http://localhost:8000",
    )

    app = FastAPI()
    app.include_router(salesforce_router)

    async def override_session() -> AsyncMock:
        session = AsyncMock()
        tenant = Tenant(id="tenant-1", name="Acme")
        tenant_result = MagicMock()
        tenant_result.scalar_one_or_none.return_value = tenant
        session.execute = AsyncMock(return_value=tenant_result)
        yield session

    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


@pytest.mark.integration
def test_salesforce_install_redirects_to_package_url(salesforce_client: TestClient) -> None:
    response = salesforce_client.get("/auth/salesforce/install?tenant_id=tenant-1", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    assert "login.salesforce.com/packaging/installPackage.apexp" in location
    assert "p0=04tg50000008CgjAAE" in location
    assert "retURL=" not in location


@pytest.mark.integration
def test_salesforce_connect_redirects_to_complete_form(salesforce_client: TestClient) -> None:
    response = salesforce_client.get("/auth/salesforce/connect?tenant_id=tenant-1", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    assert "/auth/salesforce/complete?state=" in location


@pytest.mark.integration
def test_salesforce_install_returns_404_for_unknown_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app_integrations.salesforce.settings.salesforce_settings.SALESFORCE_PACKAGE_VERSION_ID",
        "04tg50000008CgjAAE",
    )
    monkeypatch.setattr(
        "app_integrations.salesforce.settings.salesforce_settings.SALESFORCE_INSTALL_STATE_SECRET",
        "integration-test-secret",
    )

    app = FastAPI()
    app.include_router(salesforce_router)

    async def override_session() -> AsyncMock:
        session = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=execute_result)
        yield session

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)

    response = client.get("/auth/salesforce/install?tenant_id=missing")
    assert response.status_code == 404


@pytest.mark.integration
def test_salesforce_complete_form_renders(salesforce_client: TestClient) -> None:
    connect_response = salesforce_client.get("/auth/salesforce/connect?tenant_id=tenant-1", follow_redirects=False)
    complete_path = connect_response.headers["location"].split("http://localhost:8000", 1)[1]
    response = salesforce_client.get(complete_path)
    assert response.status_code == 200
    assert "integration_username" in response.text
