"""Tests for access_request_evaluation seeded task messages."""

from examples.react_agent.state import Permission, State
from examples.react_agent.subgraphs.access_request_evaluation import _seed_evaluation_message
from langchain_core.messages import HumanMessage


def test_seed_evaluation_message_includes_permission_fields() -> None:
    state = State(
        messages=[HumanMessage(content="Give me admin on AxesRev org")],
        permission=Permission(domain="github_organization", resource="AxesRev", permission="admin"),
    )

    message = _seed_evaluation_message(state)

    assert "Give me admin on AxesRev org" in message.content
    assert "github_organization" in message.content
    assert "AxesRev" in message.content
    assert "admin" in message.content


def test_seed_evaluation_message_uses_placeholder_for_missing_resource() -> None:
    state = State(
        messages=[HumanMessage(content="I need org-wide admin")],
        permission=Permission(domain="github_organization", resource=None, permission="admin"),
    )

    message = _seed_evaluation_message(state)

    assert "(none — domain-level access)" in message.content
