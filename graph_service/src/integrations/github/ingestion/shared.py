"""Shared constants and graph helpers for GitHub ingestion."""

from __future__ import annotations

import json
import logging

from github import Auth, GithubIntegration

from integrations.github.settings import get_github_settings
from nodes.app_connection import AppConnection
from nodes.app_identity import AppIdentity
from nodes.group import Group
from nodes.resource import Resource

logger = logging.getLogger(__name__)

GITHUB_APP = "github"


def make_github_integration() -> GithubIntegration:
    settings = get_github_settings()
    auth = Auth.AppAuth(settings.GITHUB_APP_ID, settings.private_key)
    return GithubIntegration(auth=auth)


def gql_string(value: str) -> str:
    return json.dumps(value)


async def connect_resource_permission(
    subject: AppIdentity | Group,
    resource: Resource,
    permission: str,
) -> None:
    rel = subject.permitted_resources
    await rel.connect(resource, {"permission": permission})


async def upsert_group(slug: str, connection: AppConnection) -> Group:
    candidates = await Group.nodes.filter(name=slug).all()
    for group in candidates:
        if await group.connection.is_connected(connection):
            return group

    group = await Group(name=slug).save()
    await group.connection.connect(connection)
    logger.info("created_group slug=%s", slug)
    return group
