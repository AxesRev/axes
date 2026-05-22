"""GitHub repository ingestion (Resource nodes)."""

from __future__ import annotations

import logging

from github.Installation import Installation
from github.Repository import Repository

from integrations.github.models import GithubResourceExtra
from nodes.app_connection import AppConnection
from nodes.resource import Resource

logger = logging.getLogger(__name__)


async def upsert_resource(repo: Repository, connection: AppConnection) -> Resource:
    extra = GithubResourceExtra(
        repo_id=repo.id,
        full_name=repo.full_name,
        private=repo.private,
        default_branch=repo.default_branch,
        html_url=repo.html_url,
        visibility=repo.visibility,
    )
    resource = await Resource.nodes.get_or_none(uri=repo.full_name)
    if resource is None:
        resource = await Resource(
            uri=repo.full_name,
            name=repo.name,
            kind="repository",
            extra=extra.model_dump(),
        ).save()
        logger.info("created_resource full_name=%s", repo.full_name)
    else:
        resource.name = repo.name
        resource.extra = extra.model_dump()
        await resource.save()

    if not await resource.connection.is_connected(connection):
        await resource.connection.replace(connection)

    return resource


async def ingest_repos(
    installation: Installation,
    connection: AppConnection,
) -> tuple[list[Repository], dict[str, Resource]]:
    repos = list(installation.get_repos())
    resources_by_uri: dict[str, Resource] = {}
    for repo in repos:
        resource = await upsert_resource(repo, connection)
        resources_by_uri[repo.full_name] = resource
    return repos, resources_by_uri
