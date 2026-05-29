"""Unit tests for Slack workspace app_integration persistence."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app_integrations.github.models import Tenant
from app_integrations.slack.constants import SLACK_APP_NAME
from app_integrations.slack.service import (
    find_slack_app_integration,
    slack_integration_config,
    upsert_slack_app_integration,
)


@pytest.mark.unit
def test_slack_integration_config_contains_team_id() -> None:
    assert slack_integration_config(team_id="T01234567") == {"team_id": "T01234567"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upsert_slack_app_integration_links_workspace_to_existing_tenant() -> None:
    tenant = Tenant(id="tenant-1", name="Acme Corp")
    session = AsyncMock()
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    integration_result = MagicMock()
    integration_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(side_effect=[tenant_result, integration_result])
    session.commit = AsyncMock()
    session.add = MagicMock()

    saved_tenant, integration = await upsert_slack_app_integration(
        tenant_id="tenant-1",
        team_id="T01234567",
        team_name="Acme Slack",
        session=session,
    )

    assert saved_tenant is tenant
    assert integration.app_name == SLACK_APP_NAME
    assert integration.config == {"team_id": "T01234567"}
    assert integration.tenant_id == "tenant-1"
    session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upsert_slack_app_integration_rejects_unknown_tenant() -> None:
    session = AsyncMock()
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=tenant_result)

    with pytest.raises(ValueError, match="tenant not found"):
        await upsert_slack_app_integration(
            tenant_id="missing-tenant",
            team_id="T01234567",
            team_name="Acme Slack",
            session=session,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_slack_app_integration_queries_by_team_id_in_config() -> None:
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=execute_result)

    result = await find_slack_app_integration(team_id="T01234567", session=session)

    assert result is None
    session.execute.assert_awaited_once()
