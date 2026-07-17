"""Tests for supported-app detection and routing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.graph import route_after_detect_relevant_apps
from examples.react_agent.nodes.detect_relevant_apps import (
    RelevantAppsSelection,
    detect_relevant_apps,
    normalize_selected_apps,
)
from examples.react_agent.state import State
from examples.react_agent.supported_apps import UNSUPPORTED_APP_MESSAGE


def test_normalize_selected_apps_deduplicates_supported_apps() -> None:
    assert normalize_selected_apps(["github", "salesforce", "github"]) == ["github", "salesforce"]


def test_normalize_selected_apps_rejects_empty_selection() -> None:
    assert normalize_selected_apps([]) is None


def test_normalize_selected_apps_rejects_unknown_app() -> None:
    assert normalize_selected_apps(["github", "jira"]) is None


async def test_detect_relevant_apps_stores_supported_selection() -> None:
    state = State(messages=[HumanMessage(content="Give me Salesforce prompt template access")])
    runtime = Runtime(context=Context())

    mock_model = MagicMock()
    mock_model.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=RelevantAppsSelection(apps=["salesforce"])
    )

    with patch("examples.react_agent.nodes.detect_relevant_apps.load_chat_model", return_value=mock_model):
        result = await detect_relevant_apps(state, runtime)

    assert result == {"selected_apps": ["salesforce"]}


async def test_detect_relevant_apps_clears_invalid_selection() -> None:
    state = State(messages=[HumanMessage(content="Need access in Jira")])
    runtime = Runtime(context=Context())

    mock_model = MagicMock()
    mock_model.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=RelevantAppsSelection(apps=["jira"])
    )

    with patch("examples.react_agent.nodes.detect_relevant_apps.load_chat_model", return_value=mock_model):
        result = await detect_relevant_apps(state, runtime)

    assert result == {"selected_apps": []}


def test_route_after_detect_relevant_apps_routes_to_unsupported_when_empty() -> None:
    assert route_after_detect_relevant_apps(State(selected_apps=[])) == "respond_unsupported_app"


def test_route_after_detect_relevant_apps_routes_to_context_loader_when_selected() -> None:
    assert route_after_detect_relevant_apps(State(selected_apps=["github"])) == "load_user_context"


async def test_respond_unsupported_app_returns_static_message() -> None:
    from examples.react_agent.nodes.unsupported_app_response import respond_unsupported_app

    result = await respond_unsupported_app(State(), Runtime(context=Context()))

    assert len(result["messages"]) == 1
    assert result["messages"][0].content == UNSUPPORTED_APP_MESSAGE
