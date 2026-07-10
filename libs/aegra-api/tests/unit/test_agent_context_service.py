"""Unit tests for tenant agent context service."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from tenant.agent_context_service import (
    AGENT_CONTEXT_MAX_LENGTH,
    get_agent_context_for_tenant,
    upsert_agent_context_for_tenant,
)
from tenant.models import TenantAgentContext


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_agent_context_for_tenant_returns_none_when_missing() -> None:
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=execute_result)

    context = await get_agent_context_for_tenant(tenant_id="tenant-1", session=session)

    assert context is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upsert_agent_context_for_tenant_creates_row() -> None:
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=execute_result)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()

    row = await upsert_agent_context_for_tenant(
        tenant_id="tenant-1",
        content="Use a friendly tone.",
        session=session,
    )

    assert row.tenant_id == "tenant-1"
    assert row.content == "Use a friendly tone."
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upsert_agent_context_for_tenant_updates_existing_row() -> None:
    existing = TenantAgentContext(
        tenant_id="tenant-1",
        content="Old text",
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = existing
    session.execute = AsyncMock(return_value=execute_result)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()

    row = await upsert_agent_context_for_tenant(
        tenant_id="tenant-1",
        content="Updated text",
        session=session,
    )

    assert row is existing
    assert existing.content == "Updated text"
    session.add.assert_not_called()
    session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upsert_agent_context_for_tenant_rejects_oversized_content() -> None:
    session = AsyncMock()

    with pytest.raises(ValueError, match=str(AGENT_CONTEXT_MAX_LENGTH)):
        await upsert_agent_context_for_tenant(
            tenant_id="tenant-1",
            content="x" * (AGENT_CONTEXT_MAX_LENGTH + 1),
            session=session,
        )

    session.execute.assert_not_called()
