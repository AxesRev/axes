"""Slack workspace lookup and GitHub identity checks against the shared RDS."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import AppIntegration, OAuthState, UserIdentity

logger = logging.getLogger(__name__)

_SLACK_APP_NAME = "slack"
_GITHUB_APP_NAME = "github"
_GITHUB_KEY = "github"
_OAUTH_STATE_TTL_MINUTES = 5


@dataclass
class GithubAccess:
    linked: bool
    tenant_id: str
    github_user_id: str = ""
    github_email: str = ""
    github_installation_id: str = ""
    connect_url: str = ""


def _github_extra(identity: UserIdentity) -> dict[str, str]:
    raw = (identity.extra_app_data or {}).get(_GITHUB_KEY)
    if not isinstance(raw, dict):
        return {}
    result: dict[str, str] = {}
    if raw.get("user_id"):
        result["user_id"] = str(raw["user_id"])
    if raw.get("email"):
        result["email"] = str(raw["email"])
    return result


@dataclass
class SlackWorkspaceUser:
    identity: UserIdentity
    bot_token: str


def slack_bot_token(config: object) -> str:
    if not isinstance(config, dict):
        return ""
    return str(config.get("bot_token") or "").strip()


async def _slack_integration_for_team(session: AsyncSession, team_id: str) -> AppIntegration | None:
    result = await session.execute(
        select(AppIntegration).where(
            AppIntegration.app_name == _SLACK_APP_NAME,
            AppIntegration.config["team_id"].astext == team_id,
        )
    )
    return result.scalar_one_or_none()


async def find_slack_bot_token(session: AsyncSession, *, team_id: str) -> str:
    integration = await _slack_integration_for_team(session, team_id)
    if integration is None:
        return ""
    return slack_bot_token(integration.config)


async def get_or_create_slack_user_identity_for_team(
    *,
    slack_user_id: str,
    team_id: str,
    session: AsyncSession,
) -> SlackWorkspaceUser | None:
    integration = await _slack_integration_for_team(session, team_id)
    if integration is None:
        return None

    tenant_id = integration.tenant_id
    bot_token = slack_bot_token(integration.config)
    result = await session.execute(select(UserIdentity).where(UserIdentity.slack_user_id == slack_user_id))
    identity = result.scalar_one_or_none()
    if identity is not None:
        return SlackWorkspaceUser(identity=identity, bot_token=bot_token)

    identity = UserIdentity(slack_user_id=slack_user_id, tenant_id=tenant_id, extra_app_data={})
    session.add(identity)
    await session.commit()
    logger.info(
        "slack_user_identity_created slack_user_id=%s team_id=%s tenant_id=%s",
        slack_user_id,
        team_id,
        tenant_id,
    )
    return SlackWorkspaceUser(identity=identity, bot_token=bot_token)


async def resolve_github_access(
    identity: UserIdentity,
    session: AsyncSession,
    *,
    server_url: str,
) -> GithubAccess:
    slack_user_id = identity.slack_user_id
    github = _github_extra(identity)
    if github.get("user_id") and github.get("email"):
        installation = await session.execute(
            select(AppIntegration).where(
                AppIntegration.tenant_id == identity.tenant_id,
                AppIntegration.app_name == _GITHUB_APP_NAME,
            )
        )
        row = installation.scalar_one_or_none()
        installation_id = ""
        if row is not None:
            raw_id = (row.config or {}).get("installation_id")
            installation_id = str(raw_id) if raw_id else ""
        return GithubAccess(
            linked=True,
            tenant_id=identity.tenant_id,
            github_user_id=github["user_id"],
            github_email=github["email"],
            github_installation_id=installation_id,
        )

    token = secrets.token_urlsafe(32)
    session.add(
        OAuthState(
            token=token,
            slack_user_id=slack_user_id,
            expires_at=datetime.now(UTC) + timedelta(minutes=_OAUTH_STATE_TTL_MINUTES),
        )
    )
    await session.commit()
    connect_url = f"{server_url.rstrip('/')}/app_integrations/github/start?token={token}"
    logger.info("identity_not_linked slack_user_id=%s connect_url=%s", slack_user_id, connect_url)
    return GithubAccess(linked=False, tenant_id=identity.tenant_id, connect_url=connect_url)
