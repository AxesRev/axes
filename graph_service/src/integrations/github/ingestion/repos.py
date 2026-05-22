"""GitHub repository ingestion (Resource nodes)."""

from __future__ import annotations

import logging

from github.Installation import Installation
from github.Repository import Repository

from nodes.app_connection import AppConnection
from nodes.resource import Resource

logger = logging.getLogger(__name__)


async def upsert_resource(repo: Repository, connection: AppConnection) -> Resource:
    external_id = str(repo.id)
    resource = await Resource.nodes.get_or_none(external_id=external_id)
    if resource is None:
        resource = await Resource(
            external_id=external_id,
            uri=repo.full_name,
            name=repo.name,
            kind="repository",
        ).save()
        logger.info("created_resource external_id=%s full_name=%s", external_id, repo.full_name)
    else:
        resource.name = repo.name
        resource.uri = repo.full_name
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
