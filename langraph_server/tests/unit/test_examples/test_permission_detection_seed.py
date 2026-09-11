"""Tests for permission_detection seeding and validator routing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from examples.react_agent.state import DetectedPermission, FieldResult, State
from examples.react_agent.subgraphs.permission_detection import (
    _BindDetectorRuntime,
    _extra_detector_context,
    _seed,
    apply_structured_response,
    route_validator,
)
from examples.react_agent.user_context_models import (
    UserContextData,
    UserContextGroup,
    UserContextPermission,
    UserContextProfile,
)


def _sample_user_context() -> UserContextData:
    return UserContextData(
        app="github",
        user_id="123",
        user_name="alice",
        groups=[UserContextGroup(external_id="org-1", name="AxesRev", description="Main org")],
        permissions=[
            UserContextPermission(
                permission="admin",
                target_kind="resource",
                target_name="AxesRev/Test_repo",
                target_external_id="repo-1",
            ),
            UserContextPermission(
                permission="read",
                target_kind="resource",
                target_name="AxesRev/axes",
                target_external_id="repo-2",
            ),
        ],
    )


def test_extra_detector_context_empty_without_user_contexts() -> None:
    state = State(messages=[HumanMessage(content="hello")])
    assert _extra_detector_context(state) == ""


def test_extra_detector_context_includes_groups_and_resource_permissions() -> None:
    state = State(
        messages=[HumanMessage(content="make me admin")],
        user_contexts=[_sample_user_context()],
    )
    block = _extra_detector_context(state)
    assert "AxesRev/Test_repo" in block
    assert "AxesRev/axes" in block
    assert "AxesRev - Main org" in block
    assert "Groups this user currently belongs to" in block
    assert "Resources this user currently has access to" in block


def test_extra_detector_context_includes_assigned_profiles() -> None:
    state = State(
        messages=[HumanMessage(content="create prompt templates")],
        user_contexts=[
            UserContextData(
                app="salesforce",
                user_id="005",
                user_name="Kirill",
                profiles=[
                    UserContextProfile(
                        external_id="0PS1",
                        name="EinsteinGPTPromptTemplateUser",
                        kind="permission_set",
                    )
                ],
            )
        ],
    )

    block = _extra_detector_context(state)

    assert "EinsteinGPTPromptTemplateUser (permission set)" in block
    assert "Profiles and permission sets assigned to this user (salesforce)" in block


def test_seed_includes_user_request_and_resource_context() -> None:
    state = State(
        user_request="I want to become the admin in our test repo.",
        user_contexts=[_sample_user_context()],
    )
    text = _seed(state).content if isinstance(_seed(state).content, str) else ""
    assert "I want to become the admin" in text
    assert "AxesRev/Test_repo" in text
    assert "submit_detected_permission" not in text
    assert "structured output" in text


def test_seed_includes_validator_feedback() -> None:
    state = State(
        user_request="repo access",
        resource_feedback="Use the exact repo name.",
    )
    text = _seed(state).content if isinstance(_seed(state).content, str) else ""
    assert "Use the exact repo name." in text


async def test_apply_structured_response_copies_field_results() -> None:
    detected = DetectedPermission(
        resource_result=FieldResult(value="AxesRev/Test_repo", justification="Matched the named test repo."),
        permission_result=FieldResult(value="write", justification="User asked to push code."),
    )
    state = State(structured_response=detected)
    update = await apply_structured_response(state, runtime=None)  # type: ignore[arg-type]
    assert update["resource_result"].value == "AxesRev/Test_repo"
    assert update["permission_result"].value == "write"


def test_route_validator_reruns_detector_when_feedback_present() -> None:
    state = State(resource_feedback="too generic")
    assert route_validator(state) == "inject_feedback"


def test_route_validator_finalizes_when_passed() -> None:
    assert route_validator(State()) == "finalize"


@pytest.mark.asyncio
async def test_bind_detector_runtime_adds_inspect_tools_to_model_request() -> None:
    inspect_tool = MagicMock()
    inspect_tool.name = "salesforce_inspect"
    graph_tool = MagicMock()
    graph_tool.name = "read_neo4j_cypher"
    request = MagicMock()
    request.tools = [graph_tool]
    request.state = {"selected_apps": ["salesforce"]}
    request.runtime.context.model = "test-model"
    request.runtime.context.thinking_budget_tokens = 0
    request.runtime.context.reasoning_effort = ""
    overridden = MagicMock()
    request.override.return_value = overridden
    handler = AsyncMock(return_value="ok")

    with (
        patch(
            "examples.react_agent.subgraphs.permission_detection.load_detection_lookup_tools",
            new=AsyncMock(return_value=[inspect_tool]),
        ),
        patch(
            "examples.react_agent.subgraphs.permission_detection.load_chat_model",
            return_value="bound-model",
        ),
    ):
        result = await _BindDetectorRuntime().awrap_model_call(request, handler)

    assert result == "ok"
    request.override.assert_called_once()
    assert request.override.call_args.kwargs["tools"] == [graph_tool, inspect_tool]
    handler.assert_awaited_once_with(overridden)


@pytest.mark.asyncio
async def test_bind_detector_runtime_executes_unregistered_inspect_tool() -> None:
    inspect_tool = MagicMock()
    inspect_tool.name = "salesforce_inspect"
    request = MagicMock()
    request.tool = None
    request.tool_call = {"name": "salesforce_inspect", "args": {}, "id": "call-1"}
    request.state = {"selected_apps": ["salesforce"]}
    overridden = MagicMock()
    request.override.return_value = overridden
    handler = AsyncMock(return_value="executed")

    with patch(
        "examples.react_agent.subgraphs.permission_detection.load_detection_lookup_tools",
        new=AsyncMock(return_value=[inspect_tool]),
    ):
        result = await _BindDetectorRuntime().awrap_tool_call(request, handler)

    assert result == "executed"
    request.override.assert_called_once_with(tool=inspect_tool)
    handler.assert_awaited_once_with(overridden)
