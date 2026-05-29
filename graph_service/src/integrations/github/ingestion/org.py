"""GitHub org/account workspace ingestion (AppConnection)."""

from __future__ import annotations

import logging

from github.NamedUser import NamedUser
from github.Organization import Organization

from integrations.github.ingestion.shared import (
    GITHUB_APP,
    AppConnectionRow,
    ConnectionRef,
    ConnectionTenantRow,
    merge_app_connections,
    merge_connections_belong_to_tenants,
)
from integrations.github.models import GithubConnectionExtra

logger = logging.getLogger(__name__)


async def upsert_connection(
    account: Organization | NamedUser,
    *,
    tenant_external_id: str,
) -> ConnectionRef:
    extra = GithubConnectionExtra(
        org_id=account.id,
        login=account.login,
        type=account.type,
        html_url=account.html_url,
        avatar_url=account.avatar_url,
    )
    connection_external_id = str(account.id)
    connection_row = AppConnectionRow(
        app=GITHUB_APP,
        external_id=connection_external_id,
        name=GITHUB_APP,
        extra=extra.model_dump(),
    )
    await merge_app_connections([connection_row])
    await merge_connections_belong_to_tenants(
        [
            ConnectionTenantRow(
                app=GITHUB_APP,
                connection_external_id=connection_external_id,
                tenant_external_id=tenant_external_id,
            )
        ]
    )
    logger.info("merged_app_connection login=%s name=%s", account.login, GITHUB_APP)
    return ConnectionRef(app=GITHUB_APP, external_id=connection_external_id)
