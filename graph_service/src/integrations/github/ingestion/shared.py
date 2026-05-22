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
    resource_uri: str
    permission: str


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
    MATCH (resource:Resource {uri: row.resource_uri})
    MERGE (subject)-[hp:HAS_PERMISSION]->(resource)
    SET hp.permission = row.permission
    """

    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        await adb.cypher_query(query, {"rows": batch})


async def upsert_group(slug: str, connection: AppConnection) -> Group:
    candidates = await Group.nodes.filter(name=slug).all()
    for group in candidates:
        if await group.connection.is_connected(connection):
            return group

    group = await Group(name=slug).save()
    await group.connection.connect(connection)
    logger.info("created_group slug=%s", slug)
    return group
