"""Orchestrate GitHub installation ingestion into the graph."""

from __future__ import annotations

import logging

from github.Installation import Installation
from github.NamedUser import NamedUser
from github.Organization import Organization

from integrations.github.ingestion.org import upsert_connection
from integrations.github.ingestion.permissions import ingest_permissions
from integrations.github.ingestion.repos import ingest_repos
from integrations.github.ingestion.shared import make_github_integration
from integrations.github.ingestion.teams import ingest_teams
from integrations.github.ingestion.tenant import upsert_tenant
from integrations.github.ingestion.users import ingest_users

logger = logging.getLogger(__name__)


async def fetch_installation(
    installation_id: int,
    *,
    tenant_id: str,
    tenant_name: str,
) -> None:
    """Fetch one GitHub App installation and write all graph data.

    Args:
        installation_id: GitHub App installation ID from ``app_integrations.config``.
        tenant_id: Postgres ``tenants.id`` — stored as the graph ``Tenant.external_id``.
        tenant_name: Postgres ``tenants.name`` — stored as the graph ``Tenant.name``.
    """
    gi = make_github_integration()
    installation: Installation = gi.get_app_installation(installation_id)
    account: Organization | NamedUser = installation.account

    gh = gi.get_github_for_installation(installation_id)

    await upsert_tenant(external_id=tenant_id, name=tenant_name)
    connection = await upsert_connection(account, tenant_external_id=tenant_id)

    logger.info("ingest_repos login=%s", account.login)
    repos, resources_by_uri = await ingest_repos(installation, connection=connection)

    logger.info("ingest_users login=%s", account.login)
    identity_external_ids = await ingest_users(gh, account, connection=connection)

    logger.info("ingest_teams login=%s", account.login)
    groups_by_slug = await ingest_teams(
        gh,
        account,
        connection=connection,
        identity_external_ids=identity_external_ids,
    )

    logger.info("ingest_permissions login=%s repos=%s", account.login, len(repos))
    org_login = account.login if account.type == "Organization" else None
    await ingest_permissions(
        gh,
        repos,
        resources_by_uri,
        connection=connection,
        org_login=org_login,
        groups_by_slug=groups_by_slug,
        identity_external_ids=identity_external_ids,
    )

    logger.info(
        "fetch_complete installation_id=%s tenant_id=%s login=%s",
        installation_id,
        tenant_id,
        account.login,
    )
