"""Tests for load_user_context node."""

from unittest.mock import AsyncMock, patch

from examples.react_agent.context import Context
from examples.react_agent.nodes.user_context import load_user_context
from examples.react_agent.state import State
from examples.react_agent.user_context_models import UserContextData, UserContextGroup
from langgraph.runtime import Runtime


async def test_load_user_context_stores_mcp_result() -> None:
    user_context = UserContextData(
        app="github",
        user_id="123",
        user_name="alice",
        groups=[UserContextGroup(external_id="g1", name="team-a")],
    )
    runtime = Runtime(context=Context(github_user_id="123"))

    with patch(
        "examples.react_agent.nodes.user_context.fetch_user_context",
        new=AsyncMock(return_value=user_context),
    ):
        result = await load_user_context(State(), runtime)

    assert result == {"user_context": user_context}


async def test_load_user_context_skips_without_user_id() -> None:
    runtime = Runtime(context=Context())

    result = await load_user_context(State(), runtime)

    assert result == {}


async def test_load_user_context_skips_when_mcp_unconfigured() -> None:
    runtime = Runtime(context=Context(github_user_id="123"))

    with patch(
        "examples.react_agent.nodes.user_context.fetch_user_context",
        new=AsyncMock(side_effect=RuntimeError("NEO4J_MCP_HOST is not configured")),
    ):
        result = await load_user_context(State(), runtime)

    assert result == {}
