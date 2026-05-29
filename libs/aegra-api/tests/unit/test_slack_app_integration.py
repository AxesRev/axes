"""Unit tests for Slack workspace app_integration persistence."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

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
async def test_upsert_slack_app_integration_creates_tenant_and_integration() -> None:
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=execute_result)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()

    tenant, integration = await upsert_slack_app_integration(
        team_id="T01234567",
        team_name="Acme Corp",
        session=session,
    )

    assert tenant.name == "Acme Corp"
    assert integration.app_name == SLACK_APP_NAME
    assert integration.config == {"team_id": "T01234567"}
    assert integration.tenant_id == tenant.id
    session.commit.assert_awaited_once()


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
