"""Unit tests for GitHub App integration persistence."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app_integrations.github.constants import GITHUB_APP_NAME
from app_integrations.github.service import (
    find_github_app_integration_for_tenant,
    github_integration_config,
    upsert_github_app_integration,
)
from tenant.models import AppIntegration, Tenant


@pytest.mark.unit
def test_github_integration_config_contains_installation_id() -> None:
    assert github_integration_config(installation_id="12345") == {"installation_id": "12345"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upsert_github_app_integration_links_installation_to_existing_tenant() -> None:
    tenant = Tenant(id="tenant-1", name="Acme Corp")
    session = AsyncMock()
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    integration_result = MagicMock()
    integration_result.scalar_one_or_none.side_effect = [None, None]
    session.execute = AsyncMock(side_effect=[tenant_result, integration_result, integration_result])
    session.commit = AsyncMock()
    session.add = MagicMock()

    saved_tenant, integration = await upsert_github_app_integration(
        tenant_id="tenant-1",
        installation_id="12345",
        session=session,
    )

    assert saved_tenant is tenant
    assert integration.app_name == GITHUB_APP_NAME
    assert integration.config == {"installation_id": "12345"}
    assert integration.tenant_id == "tenant-1"
    session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upsert_github_app_integration_updates_existing_tenant_integration() -> None:
    tenant = Tenant(id="tenant-1", name="Acme Corp")
    existing = AppIntegration(
        id="int-1",
        tenant_id="tenant-1",
        app_name=GITHUB_APP_NAME,
        config={"installation_id": "11111"},
    )
    session = AsyncMock()
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    installation_lookup = MagicMock()
    installation_lookup.scalar_one_or_none.return_value = None
    tenant_lookup = MagicMock()
    tenant_lookup.scalar_one_or_none.return_value = existing
    session.execute = AsyncMock(side_effect=[tenant_result, installation_lookup, tenant_lookup])
    session.commit = AsyncMock()

    _, integration = await upsert_github_app_integration(
        tenant_id="tenant-1",
        installation_id="22222",
        session=session,
    )

    assert integration is existing
    assert integration.config == {"installation_id": "22222"}
    session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upsert_github_app_integration_rejects_unknown_tenant() -> None:
    session = AsyncMock()
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=tenant_result)

    with pytest.raises(ValueError, match="tenant not found"):
        await upsert_github_app_integration(
            tenant_id="missing-tenant",
            installation_id="12345",
            session=session,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upsert_github_app_integration_rejects_installation_linked_to_other_tenant() -> None:
    tenant = Tenant(id="tenant-1", name="Acme Corp")
    other_integration = AppIntegration(
        id="int-2",
        tenant_id="tenant-2",
        app_name=GITHUB_APP_NAME,
        config={"installation_id": "12345"},
    )
    session = AsyncMock()
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    installation_result = MagicMock()
    installation_result.scalar_one_or_none.return_value = other_integration
    session.execute = AsyncMock(side_effect=[tenant_result, installation_result])

    with pytest.raises(ValueError, match="already linked to tenant"):
        await upsert_github_app_integration(
            tenant_id="tenant-1",
            installation_id="12345",
            session=session,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_github_app_integration_for_tenant_queries_by_tenant_and_app_name() -> None:
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=execute_result)

    result = await find_github_app_integration_for_tenant(tenant_id="tenant-1", session=session)

    assert result is None
    session.execute.assert_awaited_once()
