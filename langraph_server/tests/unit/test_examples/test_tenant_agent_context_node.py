"""Tests for load_tenant_agent_context node."""

from unittest.mock import AsyncMock, MagicMock, patch

from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.nodes.tenant_agent_context import load_tenant_agent_context
from examples.react_agent.state import State
from tenant.models import TenantAgentContext


async def test_load_tenant_agent_context_stores_db_content() -> None:
    runtime = Runtime(context=Context(tenant_id="tenant-1"))
    row = TenantAgentContext(
        tenant_id="tenant-1",
        content="Always deny production admin.",
        updated_at=MagicMock(),
    )

    async def fake_get_session() -> AsyncMock:
        session = AsyncMock()
        yield session

    with (
        patch("examples.react_agent.nodes.tenant_agent_context.get_session", fake_get_session),
        patch(
            "examples.react_agent.nodes.tenant_agent_context.get_agent_context_for_tenant",
            new=AsyncMock(return_value=row),
        ),
    ):
        result = await load_tenant_agent_context(State(), runtime)

    assert result == {"tenant_agent_context": "Always deny production admin."}


async def test_load_tenant_agent_context_skips_without_tenant_id() -> None:
    runtime = Runtime(context=Context())

    result = await load_tenant_agent_context(State(), runtime)

    assert result == {}


async def test_load_tenant_agent_context_returns_empty_when_row_missing() -> None:
    runtime = Runtime(context=Context(tenant_id="tenant-1"))

    async def fake_get_session() -> AsyncMock:
        session = AsyncMock()
        yield session

    with (
        patch("examples.react_agent.nodes.tenant_agent_context.get_session", fake_get_session),
        patch(
            "examples.react_agent.nodes.tenant_agent_context.get_agent_context_for_tenant",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await load_tenant_agent_context(State(), runtime)

    assert result == {"tenant_agent_context": ""}
