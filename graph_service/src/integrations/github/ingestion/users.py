"""GitHub user ingestion (AppIdentity nodes)."""

from __future__ import annotations

import logging

from github import GithubException
from github.MainClass import Github
from github.NamedUser import NamedUser
from github.Organization import Organization

from integrations.github.ingestion.shared import (
    GITHUB_APP,
    AppIdentityRow,
    ConnectionRef,
    merge_app_identities,
)
from integrations.github.models import GithubIdentityExtra

logger = logging.getLogger(__name__)


def identity_row_from_github(user: NamedUser, *, connection: ConnectionRef) -> AppIdentityRow:
    extra = GithubIdentityExtra(
        login=user.login,
        name=user.name,
        email=user.email,
        type=user.type,
        html_url=user.html_url,
        avatar_url=user.avatar_url,
    )
    return AppIdentityRow(
        app=GITHUB_APP,
        external_id=str(user.id),
        name=user.login,
        extra=extra.model_dump(),
        connection_app=connection["app"],
        connection_external_id=connection["external_id"],
    )


async def merge_identities(
    users: list[NamedUser],
    *,
    connection: ConnectionRef,
) -> dict[str, str]:
    rows = [identity_row_from_github(user, connection=connection) for user in users]
    await merge_app_identities(rows)
    return {user.login: str(user.id) for user in users}


async def ensure_identities_for_logins(
    gh: Github,
    logins: set[str],
    *,
    connection: ConnectionRef,
    known_external_ids: dict[str, str] | None = None,
) -> dict[str, str]:
    """Fetch missing GitHub users and batch-merge AppIdentity nodes."""
    external_ids = dict(known_external_ids or {})
    missing_logins = sorted(login for login in logins if login not in external_ids)
    if not missing_logins:
        return external_ids

    users: list[NamedUser] = []
    for login in missing_logins:
        try:
            users.append(gh.get_user(login))
        except GithubException:
            logger.warning("skip_unknown_user login=%s", login)

    if users:
        fetched = await merge_identities(users, connection=connection)
        external_ids.update(fetched)

    return external_ids


async def ingest_users(
    gh: Github,
    account: Organization | NamedUser,
    *,
    connection: ConnectionRef,
) -> dict[str, str]:
    if account.type == "Organization":
        org = gh.get_organization(account.login)
        members = list(org.get_members())
    else:
        members = [gh.get_user(account.login)]

    external_ids = await merge_identities(members, connection=connection)
    logger.info("merged_app_identities count=%s", len(external_ids))
    return external_ids
