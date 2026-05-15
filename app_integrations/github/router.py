"""FastAPI router for GitHub OAuth identity-linking endpoints.

Endpoints
---------
GET /auth/github/start?token=...
    Validates a short-lived OAuthState token, then redirects the user's
    browser to GitHub's OAuth authorization URL with a signed ``state``
    parameter.

GET /auth/github/callback?code=...&state=...
    Receives the GitHub callback, verifies the ``state`` signature, exchanges
    the authorization code for a GitHub access token, fetches the user's
    GitHub identity, and stores the Slack → GitHub mapping.

GET /auth/github/install?installation_id=...&state=...&setup_action=...
    Receives the GitHub App installation callback.  Verifies the signed
    ``state`` to recover the ``slack_user_id``, then persists the
    ``installation_id`` on the corresponding ``user_identities`` row.
"""

from __future__ import annotations

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.core.orm import get_session
from app_integrations.github.models import OAuthState
from app_integrations.github.oauth_state import create_github_oauth_state, verify_github_oauth_state
from app_integrations.github.service import (
    link_github_identity,
    store_github_installation,
    store_installation_by_github_user_id,
)
from app_integrations.github.settings import github_settings

logger = structlog.getLogger(__name__)

router = APIRouter(prefix="/auth/github", tags=["github-auth"])

_GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"  # nosec B105
_GITHUB_USER_URL = "https://api.github.com/user"

_SUCCESS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>GitHub Linked</title>
  <style>
    body {{ font-family: sans-serif; display: flex; justify-content: center;
           align-items: center; height: 100vh; margin: 0; background: #f6f8fa; }}
    .card {{ background: white; border-radius: 8px; padding: 2rem 3rem;
             box-shadow: 0 2px 8px rgba(0,0,0,.12); text-align: center; }}
    h1 {{ color: #2da44e; }}
    p  {{ color: #57606a; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>&#10003; GitHub account linked</h1>
    <p>Your GitHub account <strong>{github_username}</strong> has been connected.<br>
       You can close this tab and return to Slack.</p>
  </div>
</body>
</html>"""


async def _validate_oauth_state_token(
    token: str,
    session: AsyncSession,
) -> str:
    """Validate an OAuthState DB token and return the associated slack_user_id.

    Raises ``HTTPException(400)`` if the token is missing, expired, or already
    consumed.
    """
    result = await session.execute(select(OAuthState).where(OAuthState.token == token))
    record = result.scalar_one_or_none()

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth linking token is invalid or has already been used.",
        )

    from datetime import UTC, datetime

    if record.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        await session.delete(record)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth linking token has expired. Please request a new link from Slack.",
        )

    return record.slack_user_id


@router.get("/start")
async def github_oauth_start(
    token: str,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    """Validate the short-lived linking token and redirect the user to GitHub.

    The ``state`` parameter embedded in the GitHub redirect URL is HMAC-signed
    and contains the ``slack_user_id`` so the callback can retrieve it without
    trusting client input.

    Args:
        token: Short-lived OAuthState token sent to the user via Slack.
        session: Injected async database session.

    Returns:
        HTTP 302 redirect to GitHub's OAuth authorization endpoint.
    """
    slack_user_id = await _validate_oauth_state_token(token, session)

    if not github_settings.GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitHub OAuth is not configured on this server.",
        )
    if not github_settings.GITHUB_OAUTH_STATE_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitHub OAuth state secret is not configured.",
        )

    oauth_state = create_github_oauth_state(
        slack_user_id=slack_user_id,
        secret=github_settings.GITHUB_OAUTH_STATE_SECRET,
    )

    callback_url = f"{github_settings.SERVER_URL}/auth/github/callback"
    authorize_url = (
        f"{_GITHUB_AUTHORIZE_URL}"
        f"?client_id={github_settings.GITHUB_CLIENT_ID}"
        f"&redirect_uri={callback_url}"
        f"&state={oauth_state}"
        f"&scope=read:user"
    )

    logger.info("github_oauth_redirect", slack_user_id=slack_user_id)
    return RedirectResponse(url=authorize_url, status_code=status.HTTP_302_FOUND)


@router.get("/callback")
async def github_oauth_callback(
    code: str,
    state: str | None = None,
    installation_id: str | None = None,
    setup_action: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Handle the GitHub OAuth callback and/or GitHub App installation.

    GitHub calls this endpoint in two scenarios:

    **Scenario A — Slack-initiated OAuth linking** (``state`` present):
    The user followed a Slack-generated link.  ``state`` is HMAC-signed and
    encodes the ``slack_user_id``.  The code is exchanged for an access token,
    the GitHub identity is fetched, and the Slack → GitHub mapping is upserted.
    If ``installation_id`` is also present it is stored at the same time.

    **Scenario B — GitHub App installation** (``state`` absent):
    The user installed the app directly from GitHub.  The ``installation_id``
    is stored immediately — **no code exchange is performed**.  The code
    supplied by GitHub is only needed if user-level API access is required,
    which it is not for a plain installation record.  ``slack_user_id`` and
    ``github_user_id`` are left as ``None`` and can be filled in later.

    The ``slack_user_id`` is **never** accepted from the query string — it is
    always recovered from the verified signed state.

    Args:
        code: GitHub authorization code (used only in Scenario A).
        state: Optional HMAC-signed state parameter echoed back by GitHub.
            Present for Slack-initiated flows; absent for direct installations.
        installation_id: Optional GitHub App installation ID.
        setup_action: Optional setup action (``install`` / ``update`` /
            ``delete``).  Informational only.
        session: Injected async database session.

    Returns:
        HTML success page.
    """
    # Scenario B: GitHub App installation — exchange the code to get the
    # installer's identity, then store the installation record.
    if state is None:
        github_user_id: str | None = None
        github_username: str | None = None

        async with httpx.AsyncClient(timeout=15.0) as client:
            token_response = await client.post(
                _GITHUB_TOKEN_URL,
                data={
                    "client_id": github_settings.GITHUB_CLIENT_ID,
                    "client_secret": github_settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": f"{github_settings.SERVER_URL}/auth/github/callback",
                },
                headers={"Accept": "application/json"},
            )

        if token_response.status_code == status.HTTP_200_OK:
            access_token = token_response.json().get("access_token")
            if access_token:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    user_response = await client.get(
                        _GITHUB_USER_URL,
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Accept": "application/vnd.github+json",
                        },
                    )
                if user_response.status_code == status.HTTP_200_OK:
                    user_data = user_response.json()
                    github_user_id = str(user_data["id"])
                    github_username = user_data["login"]

        if installation_id is not None:
            await store_installation_by_github_user_id(
                github_user_id=github_user_id,
                github_username=github_username,
                installation_id=installation_id,
                session=session,
            )
        logger.info(
            "github_app_install_complete",
            installation_id=installation_id,
            github_username=github_username,
            setup_action=setup_action,
        )
        return HTMLResponse(
            content=_INSTALL_SUCCESS_HTML.format(installation_id=installation_id or ""),
            status_code=status.HTTP_200_OK,
        )

    # Scenario A: Slack-initiated OAuth flow.
    try:
        slack_user_id = verify_github_oauth_state(state, github_settings.GITHUB_OAUTH_STATE_SECRET)
    except ValueError as exc:
        logger.warning("github_oauth_invalid_state", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid OAuth state: {exc}",
        )

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_response = await client.post(
            _GITHUB_TOKEN_URL,
            data={
                "client_id": github_settings.GITHUB_CLIENT_ID,
                "client_secret": github_settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": f"{github_settings.SERVER_URL}/auth/github/callback",
            },
            headers={"Accept": "application/json"},
        )

    if token_response.status_code != status.HTTP_200_OK:
        logger.error(
            "github_token_exchange_failed",
            status_code=token_response.status_code,
            body=token_response.text,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to exchange GitHub authorization code for an access token.",
        )

    token_data = token_response.json()
    access_token = token_data.get("access_token")
    if not access_token:
        logger.error("github_token_missing", response=token_data)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub did not return an access token.",
        )

    async with httpx.AsyncClient(timeout=15.0) as client:
        user_response = await client.get(
            _GITHUB_USER_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )

    if user_response.status_code != status.HTTP_200_OK:
        logger.error(
            "github_user_fetch_failed",
            status_code=user_response.status_code,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch GitHub user information.",
        )

    user_data = user_response.json()
    github_user_id: str = str(user_data["id"])
    github_username: str = user_data["login"]

    state_result = await session.execute(select(OAuthState).where(OAuthState.slack_user_id == slack_user_id))
    oauth_token_record = state_result.scalar_one_or_none()
    oauth_token = oauth_token_record.token if oauth_token_record else ""

    await link_github_identity(
        slack_user_id=slack_user_id,
        github_user_id=github_user_id,
        github_username=github_username,
        oauth_token=oauth_token,
        session=session,
    )

    if installation_id is not None:
        await store_github_installation(
            slack_user_id=slack_user_id,
            installation_id=installation_id,
            session=session,
        )

    logger.info(
        "github_oauth_complete",
        slack_user_id=slack_user_id,
        github_username=github_username,
        installation_id=installation_id,
    )
    return HTMLResponse(
        content=_SUCCESS_HTML.format(github_username=github_username),
        status_code=status.HTTP_200_OK,
    )


_INSTALL_SUCCESS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>GitHub App Installed</title>
  <style>
    body {{ font-family: sans-serif; display: flex; justify-content: center;
           align-items: center; height: 100vh; margin: 0; background: #f6f8fa; }}
    .card {{ background: white; border-radius: 8px; padding: 2rem 3rem;
             box-shadow: 0 2px 8px rgba(0,0,0,.12); text-align: center; }}
    h1 {{ color: #2da44e; }}
    p  {{ color: #57606a; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>&#10003; GitHub App installed</h1>
    <p>Installation <strong>#{installation_id}</strong> has been recorded.<br>
       You can close this tab and return to Slack.</p>
  </div>
</body>
</html>"""


@router.get("/install")
async def github_app_install_callback(
    installation_id: str,
    state: str,
    setup_action: str = "install",
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Handle the GitHub App installation callback.

    GitHub redirects here after a user installs the app.  The ``state``
    parameter must be the HMAC-signed value generated when the bot sent the
    user their installation link — it encodes the ``slack_user_id`` so we can
    associate the installation without trusting client input.

    Steps:
    1. Verify and decode the signed ``state`` to recover ``slack_user_id``.
    2. Persist ``installation_id`` on the ``user_identities`` row.
    3. Return a success HTML page the user can close.

    Args:
        installation_id: GitHub App installation ID provided by GitHub.
        state: HMAC-signed state containing the ``slack_user_id``.
        setup_action: Action that triggered the callback (``install`` /
            ``update`` / ``delete``).  Defaults to ``"install"``.
        session: Injected async database session.

    Returns:
        HTML success page.
    """
    try:
        slack_user_id = verify_github_oauth_state(state, github_settings.GITHUB_OAUTH_STATE_SECRET)
    except ValueError as exc:
        logger.warning("github_install_invalid_state", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state parameter: {exc}",
        )

    await store_github_installation(
        slack_user_id=slack_user_id,
        installation_id=installation_id,
        session=session,
    )

    logger.info(
        "github_app_install_complete",
        slack_user_id=slack_user_id,
        installation_id=installation_id,
        setup_action=setup_action,
    )
    return HTMLResponse(
        content=_INSTALL_SUCCESS_HTML.format(installation_id=installation_id),
        status_code=status.HTTP_200_OK,
    )
