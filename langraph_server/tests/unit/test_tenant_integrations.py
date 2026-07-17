"""Unit tests for tenant app integration queries."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tenant.integration_service import list_app_integrations_for_tenant
from tenant.models import AppIntegration


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_app_integrations_for_tenant_returns_tenant_rows() -> None:
    slack = AppIntegration(id="int-1", tenant_id="tenant-1", app_name="slack", config={"team_id": "T1"})
    session = AsyncMock()
    scalars = MagicMock()
    scalars.all.return_value = [slack]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars
    session.execute = AsyncMock(return_value=execute_result)

    integrations = await list_app_integrations_for_tenant(tenant_id="tenant-1", session=session)

    assert integrations == [slack]
    session.execute.assert_awaited_once()
