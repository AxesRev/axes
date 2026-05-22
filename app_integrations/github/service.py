"""GitHub identity-linking service.

Provides two public entry points:

* ``get_github_identity`` – look up a stored Slack → GitHub mapping, or
  generate an OAuth linking URL if the mapping is absent.

* ``handle_access_request`` – guard wrapper used by Slack handlers: resolves
  the identity first and returns a typed result so callers can decide whether
  to surface a connect link or proceed with the mapped GitHub identity.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app_integrations.github.models import OAuthState, UserIdentity
from app_integrations.github.schemas import AccessRequestResult, IdentityLinked, IdentityNotLinked

logger = structlog.getLogger(__name__)

_OAUTH_STATE_TTL_MINUTES: int = 5


async def _get_or_create_identity(slack_user_id: str, session: AsyncSession) -> UserIdentity:
    """Return the UserIdentity row for *slack_user_id*, creating it if absent."""
    result = await session.execute(select(UserIdentity).where(UserIdentity.slack_user_id == slack_user_id))
    identity = result.scalar_one_or_none()

    if identity is None:
        identity = UserIdentity(slack_user_id=slack_user_id)
        session.add(identity)
        await session.flush()
        logger.info("created_user_identity", slack_user_id=slack_user_id)

    return identity


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
    slack_user_id: str,
    session: AsyncSession,
    *,
    server_url: str,
) -> IdentityLinked | IdentityNotLinked:
    """Return the GitHub identity for *slack_user_id*, or a linking URL.

    If the user already has a confirmed GitHub mapping, returns
    ``IdentityLinked``.  Otherwise generates a short-lived OAuthState token,
    persists it, and returns ``IdentityNotLinked`` with a ``connect_url`` the
    caller should send to the user.

    Args:
        slack_user_id: Slack user ID extracted from the Slack event.
        session: Active async database session.
        server_url: Public base URL of this server (used to build the link).

    Returns:
        ``IdentityLinked`` when the mapping exists, ``IdentityNotLinked`` when
        it does not.
    """
    identity = await _get_or_create_identity(slack_user_id, session)

    if identity.github_user_id and identity.github_username:
        await session.commit()
        return IdentityLinked(
            status="LINKED",
            slack_user_id=slack_user_id,
            github_user_id=identity.github_user_id,
            github_username=identity.github_username,
            github_installation_id=identity.github_installation_id or "",
        )

    token = await _create_oauth_state_token(slack_user_id, session)
    await session.commit()

    connect_url = f"{server_url}/auth/github/start?token={token}"
    logger.info("identity_not_linked", slack_user_id=slack_user_id, connect_url=connect_url)
    return IdentityNotLinked(status="NOT_LINKED", connect_url=connect_url)


async def handle_access_request(
    slack_user_id: str,
    request_payload: dict[str, Any],
    session: AsyncSession,
    *,
    server_url: str,
) -> AccessRequestResult:
    """Resolve the GitHub identity for *slack_user_id* before acting on a request.

    Enforces the following contract:
    * The GitHub username is **always** derived from the stored mapping —
      it is never accepted from ``request_payload`` or any user input.
    * If the mapping does not exist the caller receives a ``NOT_LINKED`` result
      and must surface the ``connect_url`` to the user.  The request is **not**
      executed.

    Args:
        slack_user_id: Identity of the requesting Slack user.
        request_payload: Arbitrary data describing the action to perform.
            **Must not** contain a ``github_username`` override — any such key
            is intentionally ignored here.
        session: Active async database session.
        server_url: Public base URL of this server.

    Returns:
        ``AccessRequestResult`` with ``linked=True`` and a populated
        ``identity`` when the mapping exists; ``linked=False`` and a populated
        ``not_linked`` when it does not.
    """
    result = await get_github_identity(slack_user_id, session, server_url=server_url)

    if isinstance(result, IdentityNotLinked):
        logger.info(
            "access_request_blocked_not_linked",
            slack_user_id=slack_user_id,
        )
        return AccessRequestResult(linked=False, not_linked=result)

    logger.info(
        "access_request_authorized",
        slack_user_id=slack_user_id,
        github_username=result.github_username,
    )
    return AccessRequestResult(linked=True, identity=result)


async def store_installation_by_github_user_id(
    *,
    github_user_id: str | None,
    github_username: str | None,
    installation_id: str,
    session: AsyncSession,
) -> UserIdentity:
    """Upsert a ``UserIdentity`` row for a GitHub App installation.

    Looks up an existing row by ``github_installation_id`` first, then by
    ``github_user_id`` if provided.  Creates a new row when neither matches.
    ``slack_user_id`` is left as ``None`` and can be filled in later when the
    user links their Slack account.

    Args:
        github_user_id: Numeric GitHub user ID (as a string), or ``None`` when
            the installation callback arrived without a user OAuth code.
        github_username: GitHub login / username, or ``None``.
        installation_id: GitHub App installation ID supplied by GitHub.
        session: Active async database session.

    Returns:
        The created or updated ``UserIdentity`` row.
    """
    identity: UserIdentity | None = None

    # Try to find an existing row for this installation first.
    result = await session.execute(select(UserIdentity).where(UserIdentity.github_installation_id == installation_id))
    identity = result.scalar_one_or_none()

    # Fall back to lookup by github_user_id if we have it.
    if identity is None and github_user_id is not None:
        result = await session.execute(select(UserIdentity).where(UserIdentity.github_user_id == github_user_id))
        identity = result.scalar_one_or_none()

    if identity is None:
        identity = UserIdentity(
            github_user_id=github_user_id,
            github_username=github_username,
            github_installation_id=installation_id,
        )
        session.add(identity)
        await session.flush()
        logger.info(
            "github_identity_created_from_install",
            github_user_id=github_user_id,
            installation_id=installation_id,
        )
    else:
        if github_user_id is not None:
            identity.github_user_id = github_user_id
        if github_username is not None:
            identity.github_username = github_username
        identity.github_installation_id = installation_id
        identity.updated_at = datetime.now(UTC)
        logger.info(
            "github_installation_updated",
            github_user_id=github_user_id,
            installation_id=installation_id,
        )

    await session.commit()
    return identity


async def store_github_installation(
    *,
    slack_user_id: str,
    installation_id: str,
    session: AsyncSession,
) -> UserIdentity:
    """Persist the GitHub App *installation_id* for *slack_user_id*.

    Creates the ``UserIdentity`` row if it does not yet exist (e.g. the user
    installed the app before completing OAuth).

    Args:
        slack_user_id: Slack user ID recovered from the verified signed state.
        installation_id: GitHub App installation ID supplied by GitHub.
        session: Active async database session.

    Returns:
        The updated ``UserIdentity`` row.
    """
    identity = await _get_or_create_identity(slack_user_id, session)
    identity.github_installation_id = installation_id
    identity.updated_at = datetime.now(UTC)
    await session.commit()
    logger.info(
        "github_installation_stored",
        slack_user_id=slack_user_id,
        installation_id=installation_id,
    )
    return identity


async def link_github_identity(
    *,
    slack_user_id: str,
    github_user_id: str,
    github_username: str,
    oauth_token: str,
    session: AsyncSession,
) -> UserIdentity:
    """Upsert the GitHub identity for *slack_user_id* and invalidate the OAuth state.

    Called exclusively from the OAuth callback endpoint after successfully
    exchanging the code for a GitHub access token and fetching ``/user``.

    Args:
        slack_user_id: Slack user owning this identity.
        github_user_id: Numeric GitHub user ID (as a string).
        github_username: GitHub login / username.
        oauth_token: The OAuthState token to invalidate after linking.
        session: Active async database session.

    Returns:
        The updated ``UserIdentity`` row.
    """
    identity = await _get_or_create_identity(slack_user_id, session)

    identity.github_user_id = github_user_id
    identity.github_username = github_username
    identity.updated_at = datetime.now(UTC)

    # Invalidate the OAuth state token to prevent replay.
    state_result = await session.execute(select(OAuthState).where(OAuthState.token == oauth_token))
    state_record = state_result.scalar_one_or_none()
    if state_record is not None:
        await session.delete(state_record)

    await session.commit()
    logger.info(
        "github_identity_linked",
        slack_user_id=slack_user_id,
        github_username=github_username,
        github_user_id=github_user_id,
    )
    return identity
