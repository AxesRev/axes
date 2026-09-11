"""Tests for per-app API tool loading (inspect vs mutate)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from examples.react_agent.app_api_tools import (
    APP_API_TOOLS_BY_APP,
    load_app_api_tools,
    load_detection_lookup_tools,
    load_grant_execution_tools,
)
from examples.react_agent.grant_execution_tools import GRANT_EXECUTION_TOOLS_BY_APP


def test_app_api_tools_registry_includes_github_and_salesforce() -> None:
    assert set(APP_API_TOOLS_BY_APP) == {"github", "salesforce"}
    assert GRANT_EXECUTION_TOOLS_BY_APP is APP_API_TOOLS_BY_APP


@pytest.mark.asyncio
async def test_load_grant_execution_tools_loads_salesforce_tools_when_selected() -> None:
    runtime = MagicMock()
    inspect_tool = MagicMock()
    inspect_tool.name = "salesforce_inspect"
    mutate_tool = MagicMock()
    mutate_tool.name = "salesforce_mutate"

    with (
        patch(
            "examples.react_agent.app_api_tools.build_salesforce_rest_tools",
            new=AsyncMock(return_value=[inspect_tool, mutate_tool]),
        ) as mock_build,
        patch(
            "examples.react_agent.app_api_tools._get_all_tools",
            new=AsyncMock(return_value=[]),
        ),
    ):
        tools = await load_grant_execution_tools(runtime=runtime, selected_apps=["salesforce"])

    assert tools == [inspect_tool, mutate_tool]
    mock_build.assert_awaited_once_with(runtime, include_read=True, include_write=True)


@pytest.mark.asyncio
async def test_load_grant_execution_tools_loads_github_tools_when_selected() -> None:
    runtime = MagicMock()
    fake_tool = MagicMock()
    fake_tool.name = "requests_get"

    with (
        patch(
            "examples.react_agent.app_api_tools.build_github_api_tools",
            return_value=[fake_tool],
        ) as mock_build,
        patch(
            "examples.react_agent.app_api_tools._get_all_tools",
            new=AsyncMock(return_value=[]),
        ),
    ):
        tools = await load_grant_execution_tools(runtime=runtime, selected_apps=["github"])

    assert tools == [fake_tool]
    mock_build.assert_called_once_with(runtime, include_read=True, include_write=True)


@pytest.mark.asyncio
async def test_load_grant_execution_tools_includes_graph_tools() -> None:
    runtime = MagicMock()
    fake_salesforce_tool = MagicMock()
    fake_salesforce_tool.name = "salesforce_inspect"
    fake_graph_tool = MagicMock()
    fake_graph_tool.name = "read_neo4j_cypher"

    with (
        patch(
            "examples.react_agent.app_api_tools.build_salesforce_rest_tools",
            new=AsyncMock(return_value=[fake_salesforce_tool]),
        ),
        patch(
            "examples.react_agent.app_api_tools._get_all_tools",
            new=AsyncMock(return_value=[fake_graph_tool]),
        ),
    ):
        tools = await load_grant_execution_tools(runtime=runtime, selected_apps=["salesforce"])

    assert tools == [fake_salesforce_tool, fake_graph_tool]


@pytest.mark.asyncio
async def test_load_grant_execution_tools_skips_unknown_apps() -> None:
    runtime = MagicMock()

    with (
        patch(
            "examples.react_agent.app_api_tools.build_github_api_tools",
            return_value=[],
        ),
        patch(
            "examples.react_agent.app_api_tools._get_all_tools",
            new=AsyncMock(return_value=[]),
        ),
    ):
        tools = await load_grant_execution_tools(runtime=runtime, selected_apps=["github", "unknown"])

    assert tools == []


@pytest.mark.asyncio
async def test_load_detection_lookup_tools_omits_mutate() -> None:
    runtime = MagicMock()
    inspect_tool = MagicMock()
    inspect_tool.name = "salesforce_inspect"

    with patch(
        "examples.react_agent.app_api_tools.build_salesforce_rest_tools",
        new=AsyncMock(return_value=[inspect_tool]),
    ) as mock_build:
        tools = await load_detection_lookup_tools(runtime=runtime, selected_apps=["salesforce"])

    assert tools == [inspect_tool]
    mock_build.assert_awaited_once_with(runtime, include_read=True, include_write=False)


@pytest.mark.asyncio
async def test_load_app_api_tools_skips_unconfigured_app_when_read_only() -> None:
    runtime = MagicMock()

    with (
        patch(
            "examples.react_agent.app_api_tools.build_salesforce_rest_tools",
            new=AsyncMock(side_effect=ValueError("tenant_id is required")),
        ),
        patch(
            "examples.react_agent.app_api_tools._get_all_tools",
            new=AsyncMock(return_value=[]),
        ),
    ):
        tools = await load_app_api_tools(
            runtime=runtime,
            selected_apps=["salesforce"],
            include_read=True,
            include_write=False,
        )

    assert tools == []
