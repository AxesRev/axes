"""Tests for permission_detection seeded detector messages."""

from __future__ import annotations

from examples.react_agent.state import State
from examples.react_agent.subgraphs.permission_detection import _extra_detector_context, _seed
from langchain_core.messages import HumanMessage


def test_extra_detector_context_empty_for_non_resource_fields() -> None:
    state = State(
        messages=[HumanMessage(content="hello")],
        github_repos=["o/a", "o/b"],
        github_orgs=["acme"],
    )
    assert _extra_detector_context(state, "domain") == ""
    assert _extra_detector_context(state, "permission") == ""


def test_extra_detector_context_includes_repos_and_orgs_for_resource() -> None:
    state = State(
        messages=[HumanMessage(content="make me admin")],
        github_repos=["AxesRev/Test_repo", "AxesRev/axes"],
        github_orgs=["AxesRev"],
    )
    block = _extra_detector_context(state, "resource")
    assert "AxesRev/Test_repo" in block
    assert "AxesRev/axes" in block
    assert "AxesRev" in block
    assert "Repositories linked to this user" in block
    assert "Organizations linked to this user" in block


def test_seed_resource_appends_github_lists() -> None:
    state = State(
        messages=[HumanMessage(content="I want to become the admin in our test repo.")],
        github_repos=["AxesRev/Test_repo"],
        github_orgs=[],
        domain_hint="x",
        resource_hint="y",
        permission_hint="z",
    )
    msg = _seed(state, "resource", hint="which repo", feedback=None)
    text = msg.content if isinstance(msg.content, str) else ""
    assert "I want to become the admin" in text
    assert "which repo" in text
    assert "AxesRev/Test_repo" in text


def test_seed_domain_does_not_append_github_lists() -> None:
    state = State(
        messages=[HumanMessage(content="repo access")],
        github_repos=["o/r"],
        github_orgs=["org"],
    )
    msg = _seed(state, "domain", hint="h", feedback=None)
    text = msg.content if isinstance(msg.content, str) else ""
    assert "o/r" not in text
    assert "Organizations linked" not in text
