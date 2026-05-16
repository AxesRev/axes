"""Fetch GitHub installation data and write it into the graph.

Entry point: ``fetch_installation(installation_id)``.

Fetches the org/account, all repos the app has access to, and all org
members, then upserts them as AppConnection, Resource, and AppIdentity
nodes linked under a Tenant.  A dummy Tenant is created if one does not
yet exist for this installation.

Run directly:
    cd graph_service
    uv run --package aegra-neo4j-mcp python -m integrations.github.fetcher [INSTALLATION_ID]

When INSTALLATION_ID is omitted, the first row with a non-null ``github_installation_id``
is read from Postgres.
"""

from __future__ import annotations

import asyncio
import logging
import sys

import asyncpg
from github import Auth, GithubIntegration
from github.Installation import Installation
from github.NamedUser import NamedUser
from github.Organization import Organization
from github.Repository import Repository
from neomodel import adb

import common_nodes as _common_nodes  # noqa: F401 — registers all node classes with neomodel
from integrations.github.models import GithubConnectionExtra, GithubIdentityExtra, GithubResourceExtra
from integrations.github.settings import get_github_settings, get_runner_settings
from nodes.app_connection import AppConnection
from nodes.app_identity import AppIdentity
from nodes.resource import Resource
from nodes.tenant import Tenant

logger = logging.getLogger(__name__)

_GITHUB_APP = "github"


def _make_github_integration() -> GithubIntegration:
    settings = get_github_settings()
    auth = Auth.AppAuth(settings.GITHUB_APP_ID, settings.private_key)
    return GithubIntegration(auth=auth)


async def _get_or_create_dummy_tenant(name: str) -> Tenant:
    results = await Tenant.nodes.filter(name=name).all()
    if results:
        return results[0]
    tenant = await Tenant(name=name).save()
    logger.info("created_dummy_tenant tenant=%s", name)
    return tenant


async def _upsert_connection(
    account: Organization | NamedUser,
    tenant: Tenant,
) -> AppConnection:
    extra = GithubConnectionExtra(
        org_id=account.id,
        login=account.login,
        type=account.type,
        html_url=account.html_url,
        avatar_url=account.avatar_url,
    )
    connection = await AppConnection.nodes.get_or_none(app=_GITHUB_APP, external_id=str(account.id))
    if connection is None:
        connection = await AppConnection(
            app=_GITHUB_APP,
            external_id=str(account.id),
            name=account.login,
            extra=extra.model_dump(),
        ).save()
        logger.info("created_app_connection login=%s", account.login)
    else:
        connection.name = account.login
        connection.extra = extra.model_dump()
        await connection.save()

    if not await connection.tenant.is_connected(tenant):
        await connection.tenant.replace(tenant)

    return connection


async def _upsert_resource(repo: Repository, connection: AppConnection) -> Resource:
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


async def _upsert_identity(user: NamedUser, connection: AppConnection) -> AppIdentity:
    extra = GithubIdentityExtra(
        login=user.login,
        name=user.name,
        email=user.email,
        type=user.type,
        html_url=user.html_url,
        avatar_url=user.avatar_url,
    )
    identity = await AppIdentity.nodes.get_or_none(app=_GITHUB_APP, external_id=str(user.id))
    if identity is None:
        identity = await AppIdentity(
            app=_GITHUB_APP,
            external_id=str(user.id),
            extra=extra.model_dump(),
        ).save()
        logger.info("created_app_identity login=%s", user.login)
    else:
        identity.extra = extra.model_dump()
        await identity.save()

    if not await identity.connection.is_connected(connection):
        await identity.connection.replace(connection)

    return identity


async def fetch_installation(installation_id: int) -> None:
    """Fetch repos and users for a GitHub App installation and write to graph.

    Creates a dummy Tenant scoped to this installation if one does not exist.
    All fetched nodes are linked under the resolved AppConnection.

    Args:
        installation_id: The GitHub App installation ID stored in UserIdentity.
    """
    gi = _make_github_integration()
    installation: Installation = gi.get_app_installation(installation_id)
    account: Organization | NamedUser = installation.account

    gh = gi.get_github_for_installation(installation_id)

    tenant = await _get_or_create_dummy_tenant(f"github:{account.login}")
    connection = await _upsert_connection(account, tenant)

    logger.info("fetching_repos login=%s", account.login)
    for repo in installation.get_repos():
        await _upsert_resource(repo, connection)

    logger.info("fetching_members login=%s", account.login)
    if account.type == "Organization":
        org: Organization = gh.get_organization(account.login)
        for member in org.get_members():
            await _upsert_identity(member, connection)
    else:
        user: NamedUser = gh.get_user(account.login)
        await _upsert_identity(user, connection)

    logger.info("fetch_complete installation_id=%s login=%s", installation_id, account.login)


async def _run_once() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    if len(sys.argv) > 1:
        installation_id = int(sys.argv[1])
        logger.info("installation_id_from_cli=%s", installation_id)
    else:
        runner = get_runner_settings()

        pg_conn = await asyncpg.connect(runner.postgres_url)
        try:
            row = await pg_conn.fetchrow(
                "SELECT github_installation_id FROM user_identities WHERE github_installation_id IS NOT NULL LIMIT 1"
            )
        finally:
            await pg_conn.close()

        if row is None:
            logger.error("no_installation_id_found_in_postgres")
            sys.exit(1)

        installation_id = int(row["github_installation_id"])
        logger.info("resolved_installation_id=%s", installation_id)

    runner = get_runner_settings()
    await adb.set_connection(runner.neomodel_url)
    await adb.install_all_labels()

    try:
        await fetch_installation(installation_id)
    finally:
        await adb.close_connection()


if __name__ == "__main__":
    asyncio.run(_run_once())
