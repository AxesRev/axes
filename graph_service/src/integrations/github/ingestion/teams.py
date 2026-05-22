"""GitHub team ingestion (Group nodes and MEMBER_OF edges)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from github.GithubException import GithubException
from github.MainClass import Github
from github.NamedUser import NamedUser
from github.Organization import Organization
from github.Team import Team

from integrations.github.ingestion.shared import (
    ConnectionRef,
    GroupRow,
    MemberOfRow,
    merge_groups,
    merge_member_of,
)
from integrations.github.ingestion.users import ensure_identities_for_logins

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


def group_row_from_record(record: TeamRecord, *, connection: ConnectionRef) -> GroupRow:
    return GroupRow(
        external_id=str(record.team_id),
        name=record.slug,
        description=record.description or record.name,
        connection_app=connection["app"],
        connection_external_id=connection["external_id"],
    )


def build_subteam_member_of_rows(records: list[TeamRecord]) -> list[MemberOfRow]:
    team_ids = {str(record.team_id) for record in records}
    rows: list[MemberOfRow] = []
    for record in records:
        if record.parent_team_id is None:
            continue
        child_external_id = str(record.team_id)
        parent_external_id = str(record.parent_team_id)
        if parent_external_id not in team_ids:
            logger.warning(
                "teams_skip_subteam parent_team_id=%s child_team_id=%s",
                record.parent_team_id,
                record.team_id,
            )
            continue
        rows.append(
            MemberOfRow(
                member_kind="group",
                member_external_id=child_external_id,
                member_app="",
                group_external_id=parent_external_id,
            )
        )
    return rows


def build_identity_member_of_rows(
    records: list[TeamRecord],
    *,
    identity_external_ids: dict[str, str],
    member_app: str,
) -> list[MemberOfRow]:
    rows: list[MemberOfRow] = []
    for record in records:
        group_external_id = str(record.team_id)
        for login in record.member_logins:
            member_external_id = identity_external_ids.get(login)
            if member_external_id is None:
                logger.warning("teams_skip_member missing_identity login=%s team=%s", login, record.slug)
                continue
            rows.append(
                MemberOfRow(
                    member_kind="identity",
                    member_external_id=member_external_id,
                    member_app=member_app,
                    group_external_id=group_external_id,
                )
            )
    return rows


async def ingest_teams(
    gh: Github,
    account: Organization | NamedUser,
    *,
    connection: ConnectionRef,
    identity_external_ids: dict[str, str],
) -> dict[str, str]:
    """Ingest org teams as Group nodes. Returns slug -> team external_id."""
    if account.type != "Organization":
        return {}

    org = gh.get_organization(account.login)
    records: list[TeamRecord] = []
    try:
        for team in org.get_teams():
            records.append(team_record_from_github(team))
    except GithubException as exc:
        logger.warning("teams_fetch_failed login=%s error=%s", account.login, exc)
        return {}

    group_rows = [group_row_from_record(record, connection=connection) for record in records]
    await merge_groups(group_rows)

    member_logins = {login for record in records for login in record.member_logins}
    resolved_identities = await ensure_identities_for_logins(
        gh,
        member_logins,
        connection=connection,
        known_external_ids=identity_external_ids,
    )

    subteam_rows = build_subteam_member_of_rows(records)
    member_rows = build_identity_member_of_rows(
        records,
        identity_external_ids=resolved_identities,
        member_app=connection["app"],
    )
    await merge_member_of(subteam_rows)
    await merge_member_of(member_rows)

    groups_by_slug = {record.slug: str(record.team_id) for record in records}
    logger.info(
        "merged_groups count=%s subteam_edges=%s member_edges=%s",
        len(group_rows),
        len(subteam_rows),
        len(member_rows),
    )
    return groups_by_slug
