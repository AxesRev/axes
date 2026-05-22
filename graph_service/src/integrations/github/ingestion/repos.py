"""GitHub repository ingestion (Resource nodes)."""

from __future__ import annotations

import logging

from github.Installation import Installation
from github.Repository import Repository

from integrations.github.ingestion.shared import ConnectionRef, ResourceRow, merge_resources

logger = logging.getLogger(__name__)


def resource_row_from_github(repo: Repository, *, connection: ConnectionRef) -> ResourceRow:
    return ResourceRow(
        external_id=str(repo.id),
        name=repo.name,
        uri=repo.full_name,
        kind="repository",
        connection_app=connection["app"],
        connection_external_id=connection["external_id"],
    )


async def ingest_repos(
    installation: Installation,
    *,
    connection: ConnectionRef,
) -> tuple[list[Repository], dict[str, str]]:
    repos = list(installation.get_repos())
    rows = [resource_row_from_github(repo, connection=connection) for repo in repos]
    await merge_resources(rows)
    resources_by_uri = {repo.full_name: str(repo.id) for repo in repos}
    logger.info("merged_resources count=%s", len(rows))
    return repos, resources_by_uri
