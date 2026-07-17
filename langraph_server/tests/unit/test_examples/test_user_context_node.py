"""Tests for load_user_context node."""

from unittest.mock import AsyncMock, patch

from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.nodes.user_context import load_user_context
from examples.react_agent.state import State
from examples.react_agent.user_context_models import UserContextData, UserContextGroup


async def test_load_user_context_stores_mcp_result() -> None:
    user_context = UserContextData(
        app="github",
        user_id="123",
        user_name="alice",
        groups=[UserContextGroup(external_id="g1", name="team-a")],
    )
    runtime = Runtime(context=Context(github_user_id="123"))
    state = State(selected_apps=["github"])

    with patch(
        "examples.react_agent.nodes.user_context.fetch_user_context_for_app",
        new=AsyncMock(return_value=user_context),
    ) as mock_fetch:
        result = await load_user_context(state, runtime)

    assert result == {"user_contexts": [user_context]}
    mock_fetch.assert_awaited_once_with(app="github", user_id="123", email=None)


async def test_load_user_context_returns_empty_without_selected_apps() -> None:
    runtime = Runtime(context=Context(github_user_id="123"))

    result = await load_user_context(State(), runtime)

    assert result == {"user_contexts": []}


async def test_load_user_context_skips_when_mcp_unconfigured() -> None:
    runtime = Runtime(context=Context(github_user_id="123"))
    state = State(selected_apps=["github"])

    with patch(
        "examples.react_agent.nodes.user_context.fetch_user_context_for_app",
        new=AsyncMock(side_effect=RuntimeError("NEO4J_MCP_HOST is not configured")),
    ):
        result = await load_user_context(state, runtime)

    assert result == {"user_contexts": []}


async def test_load_user_context_loads_salesforce_by_email() -> None:
    salesforce_context = UserContextData(app="salesforce", user_id="005", user_name="Kirill")
    runtime = Runtime(context=Context(github_email="kirill@example.com"))
    state = State(selected_apps=["salesforce"])

    with patch(
        "examples.react_agent.nodes.user_context.fetch_user_context_for_app",
        new=AsyncMock(return_value=salesforce_context),
    ) as mock_fetch:
        result = await load_user_context(state, runtime)

    assert result == {"user_contexts": [salesforce_context]}
    mock_fetch.assert_awaited_once_with(app="salesforce", user_id=None, email="kirill@example.com")


async def test_load_user_context_prefers_slack_email_for_salesforce() -> None:
    salesforce_context = UserContextData(app="salesforce", user_id="005", user_name="Kirill")
    runtime = Runtime(
        context=Context(
            slack_email="kirill@slack.example.com",
            github_email="kirill@github.example.com",
        )
    )
    state = State(selected_apps=["salesforce"])

    with patch(
        "examples.react_agent.nodes.user_context.fetch_user_context_for_app",
        new=AsyncMock(return_value=salesforce_context),
    ) as mock_fetch:
        result = await load_user_context(state, runtime)

    assert result == {"user_contexts": [salesforce_context]}
    mock_fetch.assert_awaited_once_with(
        app="salesforce",
        user_id=None,
        email="kirill@slack.example.com",
    )
