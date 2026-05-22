"""Shared constants and graph helpers for GitHub ingestion."""

from __future__ import annotations

import json
import logging
from typing import TypedDict

from github import Auth, GithubIntegration
from neomodel import adb

from integrations.github.settings import get_github_settings
from nodes.app_connection import AppConnection
from nodes.group import Group

logger = logging.getLogger(__name__)

GITHUB_APP = "github"
PERMISSION_BATCH_SIZE = 500


class PermissionEdgeRow(TypedDict):
    subject_id: str
    resource_external_id: str
    permission: str


class MemberOfRow(TypedDict):
    member_id: str
    group_id: str


def make_github_integration() -> GithubIntegration:
    settings = get_github_settings()
    auth = Auth.AppAuth(settings.GITHUB_APP_ID, settings.private_key)
    return GithubIntegration(auth=auth)


def gql_string(value: str) -> str:
    return json.dumps(value)


async def merge_resource_permissions(
    rows: list[PermissionEdgeRow],
    *,
    batch_size: int = PERMISSION_BATCH_SIZE,
) -> None:
    """Upsert HAS_PERMISSION edges in batches without neomodel cartesian MATCH."""
    if not rows:
        return

    query = """
    UNWIND $rows AS row
    MATCH (subject) WHERE elementId(subject) = row.subject_id
    MATCH (resource:Resource {external_id: row.resource_external_id})
    MERGE (subject)-[hp:HAS_PERMISSION]->(resource)
    SET hp.permission = row.permission
    """

    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        await adb.cypher_query(query, {"rows": batch})


async def merge_member_of(
    rows: list[MemberOfRow],
    *,
    batch_size: int = PERMISSION_BATCH_SIZE,
) -> None:
    """Upsert MEMBER_OF edges in batches (AppIdentity or Group → Group)."""
    if not rows:
        return

    query = """
    UNWIND $rows AS row
    MATCH (member) WHERE elementId(member) = row.member_id
    MATCH (group:Group) WHERE elementId(group) = row.group_id
    MERGE (member)-[:MEMBER_OF]->(group)
    """

    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        await adb.cypher_query(query, {"rows": batch})


async def upsert_group(
    *,
    external_id: str,
    name: str,
    connection: AppConnection,
    description: str | None = None,
) -> Group:
    group = await Group.nodes.get_or_none(external_id=external_id)
    if group is None:
        group = await Group(
            external_id=external_id,
            name=name,
            description=description or "",
        ).save()
        await group.connection.connect(connection)
        logger.info("created_group external_id=%s name=%s", external_id, name)
        return group

    group.name = name
    if description is not None:
        group.description = description
    await group.save()
    if not await group.connection.is_connected(connection):
        await group.connection.replace(connection)
    return group
