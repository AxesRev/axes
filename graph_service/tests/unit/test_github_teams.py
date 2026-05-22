"""Unit tests for GitHub team ingestion helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from integrations.github.ingestion.teams import (
    TeamRecord,
    _build_subteam_member_of_rows,
    team_record_from_github,
)


def _mock_team(
    *,
    slug: str,
    name: str,
    team_id: int,
    description: str = "",
    parent: MagicMock | None = None,
    members: list[MagicMock] | None = None,
) -> MagicMock:
    team = MagicMock()
    team.slug = slug
    team.name = name
    team.id = team_id
    team.description = description
    team.parent = parent
    team.get_members.return_value = members or []
    return team


@pytest.mark.unit
def test_team_record_from_github_maps_members_and_parent() -> None:
    parent = _mock_team(slug="parent-team", name="Parent", team_id=1)
    alice = MagicMock()
    alice.login = "alice"
    bob = MagicMock()
    bob.login = "bob"
    team = _mock_team(
        slug="platform",
        name="Platform",
        team_id=42,
        description="Platform engineers",
        parent=parent,
        members=[alice, bob],
    )

    record = team_record_from_github(team)

    assert record == TeamRecord(
        slug="platform",
        name="Platform",
        description="Platform engineers",
        team_id=42,
        parent_team_id=1,
        member_logins=("alice", "bob"),
    )


@pytest.mark.unit
def test_team_record_from_github_without_parent_or_description() -> None:
    team = _mock_team(slug="solo", name="Solo", team_id=7, description="")

    record = team_record_from_github(team)

    assert record.parent_team_id is None
    assert record.description is None
    assert record.member_logins == ()


@pytest.mark.unit
def test_build_subteam_member_of_rows_links_child_to_parent() -> None:
    records = [
        TeamRecord("parent", "Parent", None, 1, None, ()),
        TeamRecord("child", "Child", None, 2, 1, ()),
    ]
    parent_group = MagicMock()
    parent_group.element_id = "parent-id"
    child_group = MagicMock()
    child_group.element_id = "child-id"
    groups_by_external_id = {"1": parent_group, "2": child_group}

    rows = _build_subteam_member_of_rows(records, groups_by_external_id)

    assert rows == [{"member_id": "child-id", "group_id": "parent-id"}]


@pytest.mark.unit
def test_build_subteam_member_of_rows_skips_missing_parent() -> None:
    records = [TeamRecord("child", "Child", None, 2, 999, ())]
    child_group = MagicMock()
    child_group.element_id = "child-id"

    rows = _build_subteam_member_of_rows(records, {"2": child_group})

    assert rows == []
