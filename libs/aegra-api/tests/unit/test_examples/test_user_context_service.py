"""Tests for user context models and MCP fetch service."""

from unittest.mock import AsyncMock, patch

from examples.react_agent.user_context_models import (
    UserContextData,
    UserContextGroup,
    UserContextPermission,
    build_user_context,
    parse_group_rows,
    parse_permission_rows,
)
from examples.react_agent.user_context_service import fetch_user_context


def test_parse_group_rows_skips_incomplete_entries() -> None:
    groups = parse_group_rows(
        [
            {"external_id": "team-1", "name": "admins", "description": "Admin team"},
            {"external_id": None, "name": "ignored"},
        ]
    )

    assert groups == [UserContextGroup(external_id="team-1", name="admins", description="Admin team")]


def test_parse_permission_rows_normalizes_target_kind() -> None:
    permissions = parse_permission_rows(
        [
            {
                "permission": "admin",
                "target_kind": "Resource",
                "target_name": "AxesRev/Test_repo",
                "target_external_id": "repo-1",
            },
        ]
    )

    assert permissions == [
        UserContextPermission(
            permission="admin",
            target_kind="resource",
            target_name="AxesRev/Test_repo",
            target_external_id="repo-1",
        )
    ]


def test_build_user_context_from_record() -> None:
    user_context = build_user_context(
        {
            "app": "github",
            "user_id": "123",
            "user_name": "alice",
            "groups": [{"external_id": "g1", "name": "team-a", "description": None}],
            "permissions": [],
        }
    )

    assert user_context.user_name == "alice"
    assert user_context.groups[0].name == "team-a"


async def test_fetch_user_context_queries_mcp_and_parses_rows() -> None:
    rows = [
        {
            "app": "github",
            "user_id": "123",
            "user_name": "alice",
            "groups": [{"external_id": "g1", "name": "team-a", "description": None}],
            "permissions": [],
        }
    ]

    with patch(
        "examples.react_agent.user_context_service.read_neo4j_cypher",
        new=AsyncMock(return_value=rows),
    ) as mock_read:
        user_context = await fetch_user_context(app="github", user_id="123")

    assert user_context == UserContextData(
        app="github",
        user_id="123",
        user_name="alice",
        groups=[UserContextGroup(external_id="g1", name="team-a")],
    )
    mock_read.assert_awaited_once()
    assert mock_read.await_args.args[1] == {"app": "github", "user_id": "123"}


async def test_fetch_user_context_returns_none_when_no_rows() -> None:
    with patch(
        "examples.react_agent.user_context_service.read_neo4j_cypher",
        new=AsyncMock(return_value=[]),
    ):
        user_context = await fetch_user_context(app="github", user_id="missing")

    assert user_context is None


def test_format_for_prompt_includes_group_descriptions() -> None:
    user_context = UserContextData(
        app="github",
        user_id="123",
        user_name="alice",
        groups=[UserContextGroup(external_id="g1", name="AxesRev", description="Main org")],
    )

    prompt = user_context.format_for_prompt()

    assert "  - AxesRev - Main org" in prompt
