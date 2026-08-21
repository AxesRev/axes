"""Integration tests for install HTTP Lambda handler."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlparse

import pytest

from common.models import OAuthState, Tenant
from integrations.app import handler

_GITHUB_SECRET = "integration-test-secret"
_SF_SECRET = "integration-test-secret"


def _event(
    *,
    method: str,
    path: str,
    query: dict[str, str] | None = None,
    body: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "rawPath": path,
        "requestContext": {"http": {"method": method}},
        "headers": {"host": "localhost:8000", "x-forwarded-proto": "http"},
        "queryStringParameters": query or {},
        "isBase64Encoded": False,
    }
    if body is not None:
        payload["body"] = body
    return payload


def _invoke(**kwargs: Any) -> dict[str, Any]:
    return handler(_event(**kwargs), None)


def _json(response: dict[str, Any]) -> object:
    return json.loads(str(response["body"]))


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    db = AsyncMock()

    @asynccontextmanager
    async def fake_session() -> Any:
        yield db

    async def fake_with_session() -> Any:
        return fake_session()

    monkeypatch.setattr("integrations.app._with_session", fake_with_session)
    monkeypatch.setattr("integrations.config.settings.SERVER_URL", "http://localhost:8000")
    monkeypatch.setattr("integrations.config.settings.WEBAPP_URL", "http://localhost:3000")
    return db


@pytest.mark.integration
def test_github_install_redirects_to_github(session: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("integrations.config.settings.GITHUB_APP_SLUG", "axes-test-app")
    monkeypatch.setattr("integrations.config.settings.INSTALL_SECRET", _GITHUB_SECRET)

    tenant = Tenant(id="tenant-1", name="Acme")
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    session.execute = AsyncMock(return_value=tenant_result)

    response = _invoke(method="GET", path="/app_integrations/github/install", query={"tenant_id": "tenant-1"})
    assert response["statusCode"] == 302
    location = response["headers"]["location"]
    assert location.startswith("https://github.com/apps/axes-test-app/installations/new?state=")


@pytest.mark.integration
def test_github_install_returns_404_for_unknown_tenant(session: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("integrations.config.settings.GITHUB_APP_SLUG", "axes-test-app")
    monkeypatch.setattr("integrations.config.settings.INSTALL_SECRET", _GITHUB_SECRET)

    empty = MagicMock()
    empty.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=empty)

    response = _invoke(method="GET", path="/app_integrations/github/install", query={"tenant_id": "missing"})
    assert response["statusCode"] == 404
    assert _json(response)["detail"] == "tenant not found: missing"


@pytest.mark.integration
def test_github_callback_persists_installation(session: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("integrations.config.settings.GITHUB_APP_SLUG", "axes-test-app")
    monkeypatch.setattr("integrations.config.settings.INSTALL_SECRET", _GITHUB_SECRET)

    tenant = Tenant(id="tenant-1", name="Acme")
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    empty = MagicMock()
    empty.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(side_effect=[tenant_result, empty, empty])
    session.commit = AsyncMock()
    session.add = MagicMock()

    install = _invoke(method="GET", path="/app_integrations/github/install", query={"tenant_id": "tenant-1"})
    state = install["headers"]["location"].split("state=", 1)[1]
    session.execute = AsyncMock(side_effect=[tenant_result, empty, empty])

    response = _invoke(
        method="GET",
        path="/app_integrations/github/callback",
        query={"installation_id": "98765", "setup_action": "install", "state": state},
    )
    assert response["statusCode"] == 200
    assert "98765" in str(response["body"])
    assert "Return to Axes" in str(response["body"])


@pytest.mark.integration
def test_github_callback_requires_state(session: AsyncMock) -> None:
    response = _invoke(
        method="GET",
        path="/app_integrations/github/callback",
        query={"installation_id": "98765", "setup_action": "install"},
    )
    assert response["statusCode"] == 400


@pytest.mark.integration
def test_github_oauth_start_redirects_to_github(session: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("integrations.config.settings.GITHUB_CLIENT_ID", "client-id")
    monkeypatch.setattr("integrations.config.settings.GITHUB_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr("integrations.config.settings.GITHUB_OAUTH_STATE_SECRET", "oauth-state-secret")

    oauth_state = OAuthState(
        token="link-token",
        slack_user_id="U123",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    state_result = MagicMock()
    state_result.scalar_one_or_none.return_value = oauth_state
    session.execute = AsyncMock(return_value=state_result)

    response = _invoke(method="GET", path="/app_integrations/github/start", query={"token": "link-token"})
    assert response["statusCode"] == 302
    location = response["headers"]["location"]
    assert "github.com/login/oauth/authorize" in location
    assert "client_id=client-id" in location
    assert "state=" in location


@pytest.mark.integration
def test_github_oauth_start_rejects_unknown_token(session: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("integrations.config.settings.GITHUB_CLIENT_ID", "client-id")
    monkeypatch.setattr("integrations.config.settings.GITHUB_OAUTH_STATE_SECRET", "oauth-state-secret")

    empty = MagicMock()
    empty.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=empty)

    response = _invoke(method="GET", path="/app_integrations/github/start", query={"token": "bad"})
    assert response["statusCode"] == 400


@pytest.mark.integration
def test_salesforce_install_redirects_to_package_url(session: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("integrations.config.settings.SALESFORCE_PACKAGE_VERSION_ID", "04tg50000008CgjAAE")
    monkeypatch.setattr("integrations.config.settings.INSTALL_SECRET", _SF_SECRET)

    tenant = Tenant(id="tenant-1", name="Acme")
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    session.execute = AsyncMock(return_value=tenant_result)

    response = _invoke(method="GET", path="/app_integrations/salesforce/install", query={"tenant_id": "tenant-1"})
    assert response["statusCode"] == 302
    location = response["headers"]["location"]
    assert "login.salesforce.com/packaging/installPackage.apexp" in location
    assert "p0=04tg50000008CgjAAE" in location
    assert "retURL=" not in location


@pytest.mark.integration
def test_salesforce_connect_redirects_to_complete_form(session: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("integrations.config.settings.INSTALL_SECRET", _SF_SECRET)

    tenant = Tenant(id="tenant-1", name="Acme")
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    session.execute = AsyncMock(return_value=tenant_result)

    response = _invoke(method="GET", path="/app_integrations/salesforce/connect", query={"tenant_id": "tenant-1"})
    assert response["statusCode"] == 302
    location = response["headers"]["location"]
    assert "/app_integrations/salesforce/complete?state=" in location


@pytest.mark.integration
def test_salesforce_install_returns_404_for_unknown_tenant(session: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("integrations.config.settings.SALESFORCE_PACKAGE_VERSION_ID", "04tg50000008CgjAAE")
    monkeypatch.setattr("integrations.config.settings.INSTALL_SECRET", _SF_SECRET)

    empty = MagicMock()
    empty.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=empty)

    response = _invoke(method="GET", path="/app_integrations/salesforce/install", query={"tenant_id": "missing"})
    assert response["statusCode"] == 404


@pytest.mark.integration
def test_salesforce_complete_form_renders(session: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("integrations.config.settings.INSTALL_SECRET", _SF_SECRET)

    tenant = Tenant(id="tenant-1", name="Acme")
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    session.execute = AsyncMock(return_value=tenant_result)

    connect = _invoke(method="GET", path="/app_integrations/salesforce/connect", query={"tenant_id": "tenant-1"})
    parsed = urlparse(connect["headers"]["location"])
    state = parse_qs(parsed.query)["state"][0]
    response = _invoke(method="GET", path="/app_integrations/salesforce/complete", query={"state": state})
    assert response["statusCode"] == 200
    assert "integration_username" in str(response["body"])


@pytest.mark.integration
def test_slack_install_requires_tenant(session: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("integrations.config.settings.SLACK_CLIENT_ID", "slack-client")
    monkeypatch.setattr("integrations.config.settings.SLACK_CLIENT_SECRET", "slack-secret")

    response = _invoke(method="GET", path="/app_integrations/slack/install")
    assert response["statusCode"] == 400
