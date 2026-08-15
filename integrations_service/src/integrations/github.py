"""GitHub App installation and Slack → GitHub OAuth linking."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx
import jwt as pyjwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from integrations.config import settings
from integrations.errors import HttpError
from integrations.github_oauth import (
    create_github_oauth_state,
    fetch_github_user_id_and_email,
    verify_github_oauth_state,
)
from integrations.http import html_response, public_base_url, query_params, redirect
from integrations.models import OAuthState, Tenant
from integrations.store import link_github_identity, upsert_github_app_integration

logger = logging.getLogger(__name__)

_INSTALL_STATE_TTL_SECONDS = 600
_GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"  # nosec B105

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
    <p>Your GitHub account (<strong>{github_email}</strong>) has been connected.<br>
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


def github_callback_url(event: dict[str, Any]) -> str:
    return f"{public_base_url(event)}/app_integrations/github/callback"


def _state_kind(state: str) -> Literal["jwt", "oauth_hmac"]:
    if state.count(".") == 2:
        return "oauth_hmac"
    return "jwt"


def _decode_tenant_install_state(state: str) -> str:
    if not settings.GITHUB_INSTALL_STATE_SECRET:
        raise HttpError(500, "GITHUB_INSTALL_STATE_SECRET is not configured.")
    try:
        claims = pyjwt.decode(
            state,
            settings.GITHUB_INSTALL_STATE_SECRET,
            algorithms=["HS256"],
            options={"require": ["tenant_id", "exp"]},
        )
        tenant_id = claims["tenant_id"]
        if not isinstance(tenant_id, str) or not tenant_id:
            raise ValueError("state is missing tenant_id")
        return tenant_id
    except (pyjwt.PyJWTError, ValueError) as exc:
        logger.warning("github_app_install_invalid_state error=%s", exc)
        raise HttpError(400, f"Invalid installation state: {exc}") from exc


def _install_success(installation_id: str) -> dict[str, object]:
    return html_response(
        200,
        _TENANT_INSTALL_SUCCESS_HTML.format(
            installation_id=installation_id,
            webapp_url=settings.WEBAPP_URL.rstrip("/"),
        ),
    )


async def _validate_oauth_state_token(token: str, session: AsyncSession) -> str:
    result = await session.execute(select(OAuthState).where(OAuthState.token == token))
    record = result.scalar_one_or_none()
    if record is None:
        raise HttpError(400, "OAuth linking token is invalid or has already been used.")
    if record.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        await session.delete(record)
        await session.commit()
        raise HttpError(400, "OAuth linking token has expired. Please request a new link from Slack.")
    return record.slack_user_id


async def github_install(event: dict[str, Any], session: AsyncSession) -> dict[str, object]:
    params = query_params(event)
    tenant_id = params.get("tenant_id")
    installation_id = params.get("installation_id")
    state = params.get("state")
    setup_action = params.get("setup_action")

    if tenant_id is not None:
        return await _github_app_install_start(tenant_id, session)

    if installation_id is not None and state is not None and _state_kind(state) == "oauth_hmac":
        if not settings.GITHUB_OAUTH_STATE_SECRET:
            raise HttpError(500, "GITHUB_OAUTH_STATE_SECRET is not configured.")
        try:
            slack_user_id = verify_github_oauth_state(state, settings.GITHUB_OAUTH_STATE_SECRET)
        except ValueError as exc:
            raise HttpError(400, f"Invalid state parameter: {exc}") from exc
        logger.info(
            "github_app_install_slack_callback slack_user_id=%s installation_id=%s setup_action=%s",
            slack_user_id,
            installation_id,
            setup_action,
        )
        return _install_success(installation_id)

    raise HttpError(400, "Provide tenant_id to start installation, or installation_id with a valid state.")


async def _github_app_install_start(tenant_id: str, session: AsyncSession) -> dict[str, object]:
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HttpError(404, f"tenant not found: {tenant_id}")
    if not settings.GITHUB_APP_SLUG:
        raise HttpError(500, "GITHUB_APP_SLUG is not configured on this server.")
    if not settings.GITHUB_INSTALL_STATE_SECRET:
        raise HttpError(500, "GITHUB_INSTALL_STATE_SECRET is not configured.")

    state = pyjwt.encode(
        {
            "tenant_id": tenant_id,
            "exp": datetime.now(UTC) + timedelta(seconds=_INSTALL_STATE_TTL_SECONDS),
        },
        settings.GITHUB_INSTALL_STATE_SECRET,
        algorithm="HS256",
        headers={"typ": "JWT"},
    )
    install_url = f"https://github.com/apps/{settings.GITHUB_APP_SLUG}/installations/new?state={state}"
    logger.info("github_app_install_redirect tenant_id=%s", tenant_id)
    return redirect(install_url)


async def github_oauth_start(event: dict[str, Any], session: AsyncSession) -> dict[str, object]:
    token = query_params(event).get("token", "").strip()
    if not token:
        raise HttpError(400, "token query parameter is required")
    slack_user_id = await _validate_oauth_state_token(token, session)
    if not settings.GITHUB_CLIENT_ID:
        raise HttpError(500, "GitHub OAuth is not configured on this server.")
    if not settings.GITHUB_OAUTH_STATE_SECRET:
        raise HttpError(500, "GITHUB_OAUTH_STATE_SECRET is not configured.")

    oauth_state = create_github_oauth_state(
        slack_user_id=slack_user_id,
        secret=settings.GITHUB_OAUTH_STATE_SECRET,
    )
    callback_url = github_callback_url(event)
    authorize_url = (
        f"{_GITHUB_AUTHORIZE_URL}"
        f"?client_id={settings.GITHUB_CLIENT_ID}"
        f"&redirect_uri={callback_url}"
        f"&state={oauth_state}"
        f"&scope=read:user%20user:email"
    )
    logger.info("github_oauth_redirect slack_user_id=%s", slack_user_id)
    return redirect(authorize_url)


async def github_callback(event: dict[str, Any], session: AsyncSession) -> dict[str, object]:
    params = query_params(event)
    code = params.get("code")
    state = params.get("state")
    installation_id = params.get("installation_id")
    setup_action = params.get("setup_action")

    if code is not None:
        return await _github_oauth_callback(
            event=event,
            code=code,
            state=state,
            installation_id=installation_id,
            session=session,
        )

    if installation_id is None:
        raise HttpError(400, "Missing installation_id or authorization code.")
    if state is None:
        raise HttpError(400, "Missing state parameter. Start installation from the Axes webapp.")

    if _state_kind(state) == "jwt":
        tenant_id = _decode_tenant_install_state(state)
        try:
            await upsert_github_app_integration(
                tenant_id=tenant_id,
                installation_id=installation_id,
                session=session,
            )
        except ValueError as exc:
            raise HttpError(400, str(exc)) from exc
        logger.info(
            "github_app_install_complete tenant_id=%s installation_id=%s setup_action=%s",
            tenant_id,
            installation_id,
            setup_action,
        )
        return _install_success(installation_id)

    return _install_success(installation_id)


async def _github_oauth_callback(
    *,
    event: dict[str, Any],
    code: str,
    state: str | None,
    installation_id: str | None,
    session: AsyncSession,
) -> dict[str, object]:
    if state is None:
        raise HttpError(400, "Missing OAuth state parameter.")
    if not settings.GITHUB_OAUTH_STATE_SECRET:
        raise HttpError(500, "GITHUB_OAUTH_STATE_SECRET is not configured.")
    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        raise HttpError(500, "GitHub OAuth client credentials are not configured.")

    try:
        slack_user_id = verify_github_oauth_state(state, settings.GITHUB_OAUTH_STATE_SECRET)
    except ValueError as exc:
        raise HttpError(400, f"Invalid OAuth state: {exc}") from exc

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_response = await client.post(
            _GITHUB_TOKEN_URL,
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": github_callback_url(event),
            },
            headers={"Accept": "application/json"},
        )

    if token_response.status_code != 200:
        logger.error("github_token_exchange_failed status=%s body=%s", token_response.status_code, token_response.text)
        raise HttpError(502, "Failed to exchange GitHub authorization code for an access token.")

    token_data = token_response.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HttpError(502, "GitHub did not return an access token.")

    async with httpx.AsyncClient(timeout=15.0) as client:
        github_user_id, github_email = await fetch_github_user_id_and_email(client, access_token=access_token)

    state_result = await session.execute(select(OAuthState).where(OAuthState.slack_user_id == slack_user_id))
    oauth_token_record = state_result.scalar_one_or_none()
    oauth_token = oauth_token_record.token if oauth_token_record else ""

    await link_github_identity(
        slack_user_id=slack_user_id,
        github_user_id=github_user_id,
        github_email=github_email,
        oauth_token=oauth_token,
        session=session,
    )
    logger.info(
        "github_oauth_complete slack_user_id=%s github_user_id=%s installation_id=%s",
        slack_user_id,
        github_user_id,
        installation_id,
    )
    return html_response(200, _SUCCESS_HTML.format(github_email=github_email))
