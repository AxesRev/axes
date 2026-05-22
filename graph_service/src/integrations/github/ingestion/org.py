"""GitHub org/account workspace ingestion (AppConnection)."""

from __future__ import annotations

import logging

from github.NamedUser import NamedUser
from github.Organization import Organization

from integrations.github.ingestion.shared import GITHUB_APP
from integrations.github.models import GithubConnectionExtra
from nodes.app_connection import AppConnection
from nodes.tenant import Tenant

logger = logging.getLogger(__name__)


async def upsert_connection(
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
    connection = await AppConnection.nodes.get_or_none(app=GITHUB_APP, external_id=str(account.id))
    if connection is None:
        connection = await AppConnection(
            app=GITHUB_APP,
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
