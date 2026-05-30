"""Slack → GitHub OAuth identity linking (user-level OAuth, not tenant App install)."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app_integrations.github.extra_app_data import get_github_extra, github_is_linked, set_github_extra
from app_integrations.github.models import OAuthState, UserIdentity
from app_integrations.github.schemas import AccessRequestResult, IdentityLinked, IdentityNotLinked
from app_integrations.github.service import find_github_app_integration_for_tenant

logger = structlog.getLogger(__name__)

_OAUTH_STATE_TTL_MINUTES: int = 5


async def _resolve_tenant_installation_id(*, tenant_id: str, session: AsyncSession) -> str:
    integration = await find_github_app_integration_for_tenant(tenant_id=tenant_id, session=session)
    if integration is None:
        return ""
    installation_id = integration.config.get("installation_id")
    return str(installation_id) if installation_id else ""


async def _create_oauth_state_token(slack_user_id: str, session: AsyncSession) -> str:
    """Persist a short-lived OAuthState record and return the token."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(minutes=_OAUTH_STATE_TTL_MINUTES)

    oauth_state = OAuthState(
        token=token,
        slack_user_id=slack_user_id,
        expires_at=expires_at,
    )
    session.add(oauth_state)
    await session.flush()
    logger.info(
        "created_oauth_state_token",
        slack_user_id=slack_user_id,
        expires_at=expires_at.isoformat(),
    )
    return token


async def get_github_identity(
    identity: UserIdentity,
    session: AsyncSession,
    *,
    server_url: str,
) -> IdentityLinked | IdentityNotLinked:
    """Return linked GitHub identity or a one-time OAuth connect URL."""
    slack_user_id = identity.slack_user_id

    if github_is_linked(identity):
        github = get_github_extra(identity)
        installation_id = await _resolve_tenant_installation_id(tenant_id=identity.tenant_id, session=session)
        await session.commit()
        return IdentityLinked(
            status="LINKED",
            slack_user_id=slack_user_id,
            github_user_id=github["user_id"],
            github_email=github["email"],
            github_installation_id=installation_id,
        )

    token = await _create_oauth_state_token(slack_user_id, session)
    await session.commit()

    connect_url = f"{server_url.rstrip('/')}/auth/github/start?token={token}"
    logger.info("identity_not_linked", slack_user_id=slack_user_id, connect_url=connect_url)
    return IdentityNotLinked(status="NOT_LINKED", connect_url=connect_url)


async def handle_access_request(
    identity: UserIdentity,
    request_payload: dict[str, Any],
    session: AsyncSession,
    *,
    server_url: str,
) -> AccessRequestResult:
    """Resolve GitHub identity before acting on a Slack request.

    ``request_payload`` is intentionally not used for identity — mapping comes
    only from the database.
    """
    _ = request_payload
    result = await get_github_identity(identity, session, server_url=server_url)

    if isinstance(result, IdentityNotLinked):
        logger.info("access_request_blocked_not_linked", slack_user_id=identity.slack_user_id)
        return AccessRequestResult(linked=False, not_linked=result)

    logger.info(
        "access_request_authorized",
        slack_user_id=identity.slack_user_id,
        github_user_id=result.github_user_id,
    )
    return AccessRequestResult(linked=True, identity=result)


async def link_github_identity(
    *,
    slack_user_id: str,
    github_user_id: str,
    github_email: str,
    oauth_token: str,
    session: AsyncSession,
) -> UserIdentity:
    """Store GitHub identity on the Slack user row and invalidate the OAuth state token."""
    result = await session.execute(select(UserIdentity).where(UserIdentity.slack_user_id == slack_user_id))
    identity = result.scalar_one_or_none()
    if identity is None:
        raise ValueError(f"user identity not found for slack_user_id={slack_user_id}")

    set_github_extra(identity, user_id=github_user_id, email=github_email)

    state_result = await session.execute(select(OAuthState).where(OAuthState.token == oauth_token))
    state_record = state_result.scalar_one_or_none()
    if state_record is not None:
        await session.delete(state_record)

    await session.commit()
    logger.info(
        "github_identity_linked",
        slack_user_id=slack_user_id,
        github_user_id=github_user_id,
        tenant_id=identity.tenant_id,
    )
    return identity
