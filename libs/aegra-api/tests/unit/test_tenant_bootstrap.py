"""Unit tests for Auth0 tenant provisioning."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from slack_app.tenant_service import get_or_create_tenant_for_auth_user


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_or_create_tenant_for_auth_user_creates_tenant_on_signup() -> None:
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=execute_result)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()

    tenant = await get_or_create_tenant_for_auth_user(
        auth0_sub="auth0|123",
        email="owner@example.com",
        name="Owner Name",
        session=session,
    )

    assert tenant.auth0_sub == "auth0|123"
    assert tenant.name == "Owner Name"
    assert tenant.email == "owner@example.com"
    session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_or_create_tenant_for_auth_user_returns_existing_tenant_on_login() -> None:
    from app_integrations.github.models import Tenant

    existing = Tenant(id="tenant-1", name="Acme", email="owner@example.com", auth0_sub="auth0|123")
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = existing
    session.execute = AsyncMock(return_value=execute_result)

    tenant = await get_or_create_tenant_for_auth_user(
        auth0_sub="auth0|123",
        email="owner@example.com",
        name="Ignored",
        session=session,
    )

    assert tenant is existing
    session.commit.assert_not_called()
