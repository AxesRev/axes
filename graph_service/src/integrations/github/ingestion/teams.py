"""GitHub team ingestion (Group nodes and MEMBER_OF edges)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from github.GithubException import GithubException
from github.NamedUser import NamedUser
from github.Organization import Organization
from github.Team import Team

from integrations.github.ingestion.shared import merge_member_of, upsert_group
from integrations.github.ingestion.users import get_or_create_identity_by_login
from nodes.app_connection import AppConnection
from nodes.group import Group

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TeamRecord:
    slug: str
    name: str
    description: str | None
    team_id: int
    parent_team_id: int | None
    member_logins: tuple[str, ...]


def team_record_from_github(team: Team) -> TeamRecord:
    parent = team.parent
    parent_team_id = parent.id if parent is not None else None
    description = team.description or None
    members = tuple(member.login for member in team.get_members())
    return TeamRecord(
        slug=team.slug,
        name=team.name,
        description=description,
        team_id=team.id,
        parent_team_id=parent_team_id,
        member_logins=members,
    )


def _build_subteam_member_of_rows(
    records: list[TeamRecord],
    groups_by_external_id: dict[str, Group],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for record in records:
        if record.parent_team_id is None:
            continue
        child = groups_by_external_id.get(str(record.team_id))
        parent = groups_by_external_id.get(str(record.parent_team_id))
        if child is None or parent is None:
            logger.warning(
                "teams_skip_subteam parent_team_id=%s child_team_id=%s",
                record.parent_team_id,
                record.team_id,
            )
            continue
        child_id = child.element_id
        parent_id = parent.element_id
        if child_id is None or parent_id is None:
            continue
        rows.append({"member_id": child_id, "group_id": parent_id})
    return rows


async def ingest_teams(
    gh: object,
    account: Organization | NamedUser,
    connection: AppConnection,
) -> dict[str, Group]:
    """Ingest org teams as Group nodes. Returns slug -> Group for permission lookup."""
    if account.type != "Organization":
        return {}

    org = gh.get_organization(account.login)  # type: ignore[union-attr]
    records: list[TeamRecord] = []
    try:
        for team in org.get_teams():
            records.append(team_record_from_github(team))
    except GithubException as exc:
        logger.warning("teams_fetch_failed login=%s error=%s", account.login, exc)
        return {}

    groups_by_external_id: dict[str, Group] = {}
    groups_by_slug: dict[str, Group] = {}
    for record in records:
        group = await upsert_group(
            external_id=str(record.team_id),
            name=record.slug,
            connection=connection,
            description=record.description or record.name,
        )
        groups_by_external_id[str(record.team_id)] = group
        groups_by_slug[record.slug] = group

    subteam_rows = _build_subteam_member_of_rows(records, groups_by_external_id)
    await merge_member_of(subteam_rows)

    member_rows: list[dict[str, str]] = []
    for record in records:
        group = groups_by_external_id.get(str(record.team_id))
        if group is None or group.element_id is None:
            continue
        for login in record.member_logins:
            identity = await get_or_create_identity_by_login(gh, login, connection)  # type: ignore[arg-type]
            if identity is None or identity.element_id is None:
                continue
            member_rows.append({"member_id": identity.element_id, "group_id": group.element_id})

    await merge_member_of(member_rows)
    logger.info(
        "teams_merged teams=%s subteam_edges=%s member_edges=%s", len(records), len(subteam_rows), len(member_rows)
    )
    return groups_by_slug
