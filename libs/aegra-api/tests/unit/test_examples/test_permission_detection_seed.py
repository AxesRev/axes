"""Tests for permission_detection seeded detector messages."""

from __future__ import annotations

from examples.react_agent.state import State
from examples.react_agent.subgraphs.permission_detection import _extra_detector_context, _seed
from examples.react_agent.user_context_models import UserContextData, UserContextGroup, UserContextPermission
from langchain_core.messages import HumanMessage


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


def test_extra_detector_context_empty_for_non_resource_fields() -> None:
    state = State(
        messages=[HumanMessage(content="hello")],
        user_contexts=[_sample_user_context()],
    )
    assert _extra_detector_context(state, "domain") == ""
    assert _extra_detector_context(state, "permission") == ""


def test_extra_detector_context_includes_groups_and_resource_permissions() -> None:
    state = State(
        messages=[HumanMessage(content="make me admin")],
        user_contexts=[_sample_user_context()],
    )
    block = _extra_detector_context(state, "resource")
    assert "AxesRev/Test_repo" in block
    assert "AxesRev/axes" in block
    assert "AxesRev - Main org" in block
    assert "Groups this user currently belongs to" in block
    assert "Resources this user currently has access to" in block


def test_seed_resource_appends_user_context_lists() -> None:
    state = State(
        messages=[HumanMessage(content="I want to become the admin in our test repo.")],
        user_contexts=[_sample_user_context()],
    )
    msg = _seed(state, "resource", feedback=None)
    text = msg.content if isinstance(msg.content, str) else ""
    assert "I want to become the admin" in text
    assert "AxesRev/Test_repo" in text


def test_seed_domain_does_not_append_user_context_lists() -> None:
    state = State(
        messages=[HumanMessage(content="repo access")],
        user_contexts=[_sample_user_context()],
    )
    msg = _seed(state, "domain", feedback=None)
    text = msg.content if isinstance(msg.content, str) else ""
    assert "AxesRev/Test_repo" not in text
    assert "Groups this user currently belongs to" not in text
