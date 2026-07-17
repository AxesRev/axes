"""Tests for per-app grant execution tool loading."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from examples.react_agent.grant_execution_tools import (
    GRANT_EXECUTION_TOOLS_BY_APP,
    load_grant_execution_tools,
)


def test_grant_execution_tools_registry_includes_github_and_salesforce() -> None:
    assert set(GRANT_EXECUTION_TOOLS_BY_APP) == {"github", "salesforce"}


@pytest.mark.asyncio
async def test_load_grant_execution_tools_loads_salesforce_tools_when_selected() -> None:
    runtime = MagicMock()
    fake_tool = MagicMock(name="salesforce_tool")

    with (
        patch(
            "examples.react_agent.grant_execution_tools.build_salesforce_rest_tools",
            new=AsyncMock(return_value=[fake_tool]),
        ) as mock_build,
        patch(
            "examples.react_agent.grant_execution_tools._get_all_tools",
            new=AsyncMock(return_value=[]),
        ),
    ):
        tools = await load_grant_execution_tools(runtime=runtime, selected_apps=["salesforce"])

    assert tools == [fake_tool]
    mock_build.assert_awaited_once_with(runtime)


@pytest.mark.asyncio
async def test_load_grant_execution_tools_loads_github_tools_when_selected() -> None:
    runtime = MagicMock()
    fake_tool = MagicMock(name="github_tool")
    fake_toolkit = MagicMock()
    fake_toolkit.get_tools.return_value = [fake_tool]

    with (
        patch(
            "examples.react_agent.grant_execution_tools.build_openapi_toolkit",
            return_value=fake_toolkit,
        ) as mock_build,
        patch(
            "examples.react_agent.grant_execution_tools._get_all_tools",
            new=AsyncMock(return_value=[]),
        ),
    ):
        tools = await load_grant_execution_tools(runtime=runtime, selected_apps=["github"])

    assert tools == [fake_tool]
    mock_build.assert_called_once_with(runtime)


@pytest.mark.asyncio
async def test_load_grant_execution_tools_includes_graph_tools() -> None:
    runtime = MagicMock()
    fake_salesforce_tool = MagicMock(name="salesforce_rest")
    fake_graph_tool = MagicMock(name="read_neo4j_cypher")

    with (
        patch(
            "examples.react_agent.grant_execution_tools.build_salesforce_rest_tools",
            new=AsyncMock(return_value=[fake_salesforce_tool]),
        ),
        patch(
            "examples.react_agent.grant_execution_tools._get_all_tools",
            new=AsyncMock(return_value=[fake_graph_tool]),
        ),
    ):
        tools = await load_grant_execution_tools(runtime=runtime, selected_apps=["salesforce"])

    assert tools == [fake_salesforce_tool, fake_graph_tool]


@pytest.mark.asyncio
async def test_load_grant_execution_tools_skips_unknown_apps() -> None:
    runtime = MagicMock()
    fake_toolkit = MagicMock()
    fake_toolkit.get_tools.return_value = []

    with (
        patch(
            "examples.react_agent.grant_execution_tools.build_openapi_toolkit",
            return_value=fake_toolkit,
        ),
        patch(
            "examples.react_agent.grant_execution_tools._get_all_tools",
            new=AsyncMock(return_value=[]),
        ),
    ):
        tools = await load_grant_execution_tools(runtime=runtime, selected_apps=["github", "unknown"])

    assert tools == []
