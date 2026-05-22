"""GitHub user ingestion (AppIdentity nodes)."""

from __future__ import annotations

import logging

from github import GithubException
from github.MainClass import Github
from github.NamedUser import NamedUser
from github.Organization import Organization

from integrations.github.ingestion.shared import GITHUB_APP, link_belongs_to
from integrations.github.models import GithubIdentityExtra
from nodes.app_connection import AppConnection
from nodes.app_identity import AppIdentity

logger = logging.getLogger(__name__)


async def upsert_identity(user: NamedUser, connection: AppConnection) -> AppIdentity:
    extra = GithubIdentityExtra(
        login=user.login,
        name=user.name,
        email=user.email,
        type=user.type,
        html_url=user.html_url,
        avatar_url=user.avatar_url,
    )
    identity = await AppIdentity.nodes.get_or_none(app=GITHUB_APP, external_id=str(user.id))
    if identity is None:
        identity = await AppIdentity(
            app=GITHUB_APP,
            external_id=str(user.id),
            name=user.login,
            extra=extra.model_dump(),
        ).save()
        logger.info("created_app_identity login=%s", user.login)
    else:
        identity.name = user.login
        identity.extra = extra.model_dump()
        await identity.save()

    if identity.element_id is not None and connection.element_id is not None:
        await link_belongs_to(child_id=identity.element_id, parent_id=connection.element_id)

    return identity


async def get_or_create_identity_by_login(
    gh: Github,
    login: str,
    connection: AppConnection,
) -> AppIdentity | None:
    try:
        user = gh.get_user(login)
    except GithubException:
        logger.warning("skip_unknown_user login=%s", login)
        return None

    return await upsert_identity(user, connection)


async def ingest_users(
    gh: Github,
    account: Organization | NamedUser,
    connection: AppConnection,
) -> None:
    if account.type == "Organization":
        org = gh.get_organization(account.login)
        for member in org.get_members():
            await upsert_identity(member, connection)
        return

    user = gh.get_user(account.login)
    await upsert_identity(user, connection)
