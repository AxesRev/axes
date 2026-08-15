"""Unit tests for billing → tenant HTTP client."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from billing.tenant_client import resolve_tenant_for_auth_user


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_tenant_for_auth_user_posts_internal_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("billing.tenant_client.billing_settings.TENANT_API_URL", "http://tenant.example")
    monkeypatch.setattr("billing.tenant_client.billing_settings.INTERNAL_API_SECRET", "secret")

    response = httpx.Response(
        200,
        json={"id": "tenant-1", "name": "Owner", "email": "owner@example.com"},
        request=httpx.Request("POST", "http://tenant.example/internal/tenants/resolve"),
    )
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("billing.tenant_client.httpx.AsyncClient", return_value=client):
        ref = await resolve_tenant_for_auth_user(
            auth0_sub="auth0|123",
            email="owner@example.com",
            name="Owner",
        )

    assert ref.id == "tenant-1"
    assert ref.name == "Owner"
    assert ref.email == "owner@example.com"
    client.post.assert_awaited_once_with(
        "http://tenant.example/internal/tenants/resolve",
        headers={"X-Internal-Secret": "secret"},
        json={"auth0_sub": "auth0|123", "email": "owner@example.com", "name": "Owner"},
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_tenant_for_auth_user_raises_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("billing.tenant_client.billing_settings.TENANT_API_URL", "http://tenant.example")
    monkeypatch.setattr("billing.tenant_client.billing_settings.INTERNAL_API_SECRET", "secret")

    response = httpx.Response(
        401,
        json={"detail": "Invalid internal secret"},
        request=httpx.Request("POST", "http://tenant.example/internal/tenants/resolve"),
    )
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("billing.tenant_client.httpx.AsyncClient", return_value=client), pytest.raises(PermissionError):
        await resolve_tenant_for_auth_user(auth0_sub="auth0|123", email=None, name=None)
