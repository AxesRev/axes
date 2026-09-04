"""Tests for permission_detection seeding and validator routing."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from examples.react_agent.state import DetectedPermission, FieldResult, State
from examples.react_agent.subgraphs.permission_detection import (
    _extra_detector_context,
    _seed,
    apply_structured_response,
    route_validator,
)
from examples.react_agent.user_context_models import UserContextData, UserContextGroup, UserContextPermission


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


def test_seed_includes_user_request_and_resource_context() -> None:
    state = State(
        messages=[HumanMessage(content="I want to become the admin in our test repo.")],
        user_contexts=[_sample_user_context()],
    )
    text = _seed(state).content if isinstance(_seed(state).content, str) else ""
    assert "I want to become the admin" in text
    assert "AxesRev/Test_repo" in text
    assert "submit_detected_permission" not in text
    assert "structured output" in text


def test_seed_includes_validator_feedback() -> None:
    state = State(
        messages=[HumanMessage(content="repo access")],
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
