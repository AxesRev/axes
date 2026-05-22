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
from integrations.github.ingestion.tenant import get_or_create_tenant
from integrations.github.ingestion.users import ingest_users

logger = logging.getLogger(__name__)


async def fetch_installation(installation_id: int) -> None:
    """Fetch one GitHub App installation and write all graph data.

    Args:
        installation_id: The GitHub App installation ID stored in UserIdentity.
    """
    gi = make_github_integration()
    installation: Installation = gi.get_app_installation(installation_id)
    account: Organization | NamedUser = installation.account

    gh = gi.get_github_for_installation(installation_id)

    tenant = await get_or_create_tenant(f"github:{account.login}")
    connection = await upsert_connection(account, tenant)

    logger.info("ingest_repos login=%s", account.login)
    repos, resources_by_uri = await ingest_repos(installation, connection)

    logger.info("ingest_users login=%s", account.login)
    await ingest_users(gh, account, connection)

    logger.info("ingest_permissions login=%s repos=%s", account.login, len(repos))
    org_login = account.login if account.type == "Organization" else None
    await ingest_permissions(gh, repos, resources_by_uri, connection, org_login=org_login)

    logger.info("fetch_complete installation_id=%s login=%s", installation_id, account.login)
