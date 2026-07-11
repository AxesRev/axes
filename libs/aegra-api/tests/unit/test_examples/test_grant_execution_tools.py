"""Tests for per-app grant execution tool loading."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from examples.react_agent.grant_execution_tools import (
    GRANT_EXECUTION_TOOLS_BY_APP,
    load_grant_execution_tools,
)


def test_grant_execution_tools_registry_includes_github_and_salesforce() -> None:
    assert set(GRANT_EXECUTION_TOOLS_BY_APP) == {"github", "salesforce"}


def test_load_grant_execution_tools_returns_empty_for_salesforce_only() -> None:
    runtime = MagicMock()

    tools = load_grant_execution_tools(runtime=runtime, selected_apps=["salesforce"])

    assert tools == []


def test_load_grant_execution_tools_loads_github_tools_when_selected() -> None:
    runtime = MagicMock()
    fake_tool = MagicMock(name="github_tool")
    fake_toolkit = MagicMock()
    fake_toolkit.get_tools.return_value = [fake_tool]

    with patch(
        "examples.react_agent.grant_execution_tools.build_openapi_toolkit",
        return_value=fake_toolkit,
    ) as mock_build:
        tools = load_grant_execution_tools(runtime=runtime, selected_apps=["github"])

    assert tools == [fake_tool]
    mock_build.assert_called_once_with(runtime)


def test_load_grant_execution_tools_skips_unknown_apps() -> None:
    runtime = MagicMock()
    fake_toolkit = MagicMock()
    fake_toolkit.get_tools.return_value = []

    with patch(
        "examples.react_agent.grant_execution_tools.build_openapi_toolkit",
        return_value=fake_toolkit,
    ):
        tools = load_grant_execution_tools(runtime=runtime, selected_apps=["github", "unknown"])

    assert tools == []
