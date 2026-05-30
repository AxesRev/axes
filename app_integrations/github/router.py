"""FastAPI router for GitHub App installation and Slack → GitHub OAuth linking."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

import httpx
import jwt as pyjwt
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.core.orm import get_session
from app_integrations.github.identity_linking import link_github_identity
from app_integrations.github.models import OAuthState, Tenant
from app_integrations.github.oauth_state import create_github_oauth_state, verify_github_oauth_state
from app_integrations.github.service import upsert_github_app_integration
from app_integrations.github.settings import github_settings

logger = structlog.getLogger(__name__)

router = APIRouter(prefix="/auth/github", tags=["github-app"])
_INSTALL_STATE_TTL_SECONDS = 600

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

_TENANT_INSTALL_SUCCESS_HTML = """<!DOCTYPE html>
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
    a  {{ color: #0969da; text-decoration: none; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>&#10003; GitHub App installed</h1>
    <p>Installation <strong>#{installation_id}</strong> has been connected to your tenant.<br>
       <a href="{webapp_url}">Return to Axes</a></p>
  </div>
</body>
</html>"""


def _state_kind(state: str) -> Literal["jwt", "oauth_hmac"]:
    """Distinguish tenant install JWT (3 segments) from OAuth HMAC state (2 segments)."""
    if state.count(".") == 2:
        return "oauth_hmac"
    return "jwt"


async def _validate_oauth_state_token(
    token: str,
    session: AsyncSession,
) -> str:
    """Validate an OAuthState DB token and return the associated slack_user_id."""
    result = await session.execute(select(OAuthState).where(OAuthState.token == token))
    record = result.scalar_one_or_none()

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth linking token is invalid or has already been used.",
        )

    if record.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        await session.delete(record)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth linking token has expired. Please request a new link from Slack.",
        )

    return record.slack_user_id


def _decode_tenant_install_state(state: str) -> str:
    if not github_settings.GITHUB_INSTALL_STATE_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GITHUB_INSTALL_STATE_SECRET is not configured.",
        )
    try:
        claims = pyjwt.decode(
            state,
            github_settings.GITHUB_INSTALL_STATE_SECRET,
            algorithms=["HS256"],
            options={"require": ["tenant_id", "exp"]},
        )
        tenant_id = claims["tenant_id"]
        if not isinstance(tenant_id, str) or not tenant_id:
            raise ValueError("state is missing tenant_id")
        return tenant_id
    except (pyjwt.PyJWTError, ValueError) as exc:
        logger.warning("github_app_install_invalid_state", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid installation state: {exc}",
        ) from exc


@router.get("/install", response_model=None)
async def github_app_install(
    tenant_id: str | None = None,
    installation_id: str | None = None,
    state: str | None = None,
    setup_action: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse | HTMLResponse:
    """Start tenant GitHub App install, or handle Slack-signed install callback.

    * ``?tenant_id=`` — redirect browser to GitHub's install page (webapp flow).
    * ``?installation_id=&state=`` with OAuth HMAC state — legacy Slack install callback.
    """
    if tenant_id is not None:
        return await _github_app_install_start(tenant_id, session)

    if installation_id is not None and state is not None and _state_kind(state) == "oauth_hmac":
        if not github_settings.GITHUB_OAUTH_STATE_SECRET:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GITHUB_OAUTH_STATE_SECRET is not configured.",
            )
        try:
            slack_user_id = verify_github_oauth_state(state, github_settings.GITHUB_OAUTH_STATE_SECRET)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid state parameter: {exc}",
            ) from exc
        logger.info(
            "github_app_install_slack_callback",
            slack_user_id=slack_user_id,
            installation_id=installation_id,
            setup_action=setup_action,
        )
        return HTMLResponse(
            content=_TENANT_INSTALL_SUCCESS_HTML.format(
                installation_id=installation_id,
                webapp_url=github_settings.WEBAPP_URL.rstrip("/"),
            ),
            status_code=status.HTTP_200_OK,
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Provide tenant_id to start installation, or installation_id with a valid state.",
    )


async def _github_app_install_start(tenant_id: str, session: AsyncSession) -> RedirectResponse:
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"tenant not found: {tenant_id}")

    if not github_settings.GITHUB_APP_SLUG:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GITHUB_APP_SLUG is not configured on this server.",
        )
    if not github_settings.GITHUB_INSTALL_STATE_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GITHUB_INSTALL_STATE_SECRET is not configured.",
        )

    state = pyjwt.encode(
        {
            "tenant_id": tenant_id,
            "exp": datetime.now(UTC) + timedelta(seconds=_INSTALL_STATE_TTL_SECONDS),
        },
        github_settings.GITHUB_INSTALL_STATE_SECRET,
        algorithm="HS256",
        headers={"typ": "JWT"},
    )
    install_url = f"https://github.com/apps/{github_settings.GITHUB_APP_SLUG}/installations/new?state={state}"
    logger.info("github_app_install_redirect", tenant_id=tenant_id)
    return RedirectResponse(url=install_url, status_code=status.HTTP_302_FOUND)


@router.get("/start")
async def github_oauth_start(
    token: str,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    """Validate a Slack linking token and redirect the user to GitHub OAuth."""
    slack_user_id = await _validate_oauth_state_token(token, session)

    if not github_settings.GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitHub OAuth is not configured on this server.",
        )
    if not github_settings.GITHUB_OAUTH_STATE_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GITHUB_OAUTH_STATE_SECRET is not configured.",
        )

    oauth_state = create_github_oauth_state(
        slack_user_id=slack_user_id,
        secret=github_settings.GITHUB_OAUTH_STATE_SECRET,
    )

    callback_url = f"{github_settings.SERVER_URL.rstrip('/')}/auth/github/callback"
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
async def github_callback(
    code: str | None = None,
    state: str | None = None,
    installation_id: str | None = None,
    setup_action: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """GitHub OAuth callback, tenant App install callback, or direct App install."""
    if code is not None:
        return await _github_oauth_callback(
            code=code,
            state=state,
            installation_id=installation_id,
            session=session,
        )

    if installation_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing installation_id or authorization code.",
        )

    if state is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing state parameter. Start installation from the Axes webapp.",
        )

    if _state_kind(state) == "jwt":
        tenant_id = _decode_tenant_install_state(state)
        try:
            await upsert_github_app_integration(
                tenant_id=tenant_id,
                installation_id=installation_id,
                session=session,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        logger.info(
            "github_app_install_complete",
            tenant_id=tenant_id,
            installation_id=installation_id,
            setup_action=setup_action,
        )
        return HTMLResponse(
            content=_TENANT_INSTALL_SUCCESS_HTML.format(
                installation_id=installation_id,
                webapp_url=github_settings.WEBAPP_URL.rstrip("/"),
            ),
            status_code=status.HTTP_200_OK,
        )

    return HTMLResponse(
        content=_TENANT_INSTALL_SUCCESS_HTML.format(
            installation_id=installation_id,
            webapp_url=github_settings.WEBAPP_URL.rstrip("/"),
        ),
        status_code=status.HTTP_200_OK,
    )


async def _github_oauth_callback(
    *,
    code: str,
    state: str | None,
    installation_id: str | None,
    session: AsyncSession,
) -> HTMLResponse:
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing OAuth state parameter.",
        )
    if not github_settings.GITHUB_OAUTH_STATE_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GITHUB_OAUTH_STATE_SECRET is not configured.",
        )
    if not github_settings.GITHUB_CLIENT_ID or not github_settings.GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitHub OAuth client credentials are not configured.",
        )

    try:
        slack_user_id = verify_github_oauth_state(state, github_settings.GITHUB_OAUTH_STATE_SECRET)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid OAuth state: {exc}",
        ) from exc

    callback_url = f"{github_settings.SERVER_URL.rstrip('/')}/auth/github/callback"
    async with httpx.AsyncClient(timeout=15.0) as client:
        token_response = await client.post(
            _GITHUB_TOKEN_URL,
            data={
                "client_id": github_settings.GITHUB_CLIENT_ID,
                "client_secret": github_settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": callback_url,
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
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch GitHub user information.",
        )

    user_data = user_response.json()
    github_user_id = str(user_data["id"])
    github_username = str(user_data["login"])

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
