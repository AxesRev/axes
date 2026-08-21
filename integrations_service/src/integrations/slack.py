"""Slack workspace OAuth install and callback."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt as pyjwt
from sqlalchemy.ext.asyncio import AsyncSession

from integrations.config import SLACK_BOT_SCOPES, settings
from integrations.errors import HttpError
from integrations.http import public_base_url, query_params, redirect, require_tenant_id, text_response
from integrations.store import get_tenant, upsert_slack_app_integration

logger = logging.getLogger(__name__)

_SLACK_AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
_SLACK_TOKEN_URL = "https://slack.com/api/oauth.v2.access"  # nosec B105
_INSTALL_STATE_TTL_SECONDS = 600


def slack_callback_url(event: dict[str, Any]) -> str:
    return f"{public_base_url(event)}/app_integrations/slack/callback"


def _encode_state(tenant_id: str) -> str:
    if not settings.SLACK_CLIENT_SECRET:
        raise HttpError(500, "SLACK_CLIENT_SECRET is not configured.")
    return pyjwt.encode(
        {
            "tenant_id": tenant_id,
            "exp": datetime.now(UTC) + timedelta(seconds=_INSTALL_STATE_TTL_SECONDS),
        },
        settings.SLACK_CLIENT_SECRET,
        algorithm="HS256",
        headers={"typ": "JWT"},
    )


def _decode_state(state: str) -> str:
    if not settings.SLACK_CLIENT_SECRET:
        raise HttpError(500, "SLACK_CLIENT_SECRET is not configured.")
    try:
        claims = pyjwt.decode(
            state,
            settings.SLACK_CLIENT_SECRET,
            algorithms=["HS256"],
            options={"require": ["tenant_id", "exp"]},
        )
        tenant_id = claims["tenant_id"]
        if not isinstance(tenant_id, str) or not tenant_id:
            raise ValueError("state is missing tenant_id")
        return tenant_id
    except (pyjwt.PyJWTError, ValueError) as exc:
        raise HttpError(400, f"Invalid installation state: {exc}") from exc


async def slack_install(event: dict[str, Any], session: AsyncSession) -> dict[str, object]:
    tenant_id = require_tenant_id(query_params(event))
    tenant = await get_tenant(session, tenant_id)
    if tenant is None:
        return text_response(404, f"tenant not found: {tenant_id}")
    if not settings.SLACK_CLIENT_ID:
        raise HttpError(500, "SLACK_CLIENT_ID is not configured.")

    state = _encode_state(tenant_id)
    params = urlencode(
        {
            "client_id": settings.SLACK_CLIENT_ID,
            "scope": ",".join(SLACK_BOT_SCOPES),
            "redirect_uri": slack_callback_url(event),
            "state": state,
        }
    )
    logger.info("slack_oauth_install_redirect tenant_id=%s", tenant_id)
    return redirect(f"{_SLACK_AUTHORIZE_URL}?{params}")


async def slack_callback(event: dict[str, Any], session: AsyncSession) -> dict[str, object]:
    params = query_params(event)
    error = params.get("error")
    if error:
        return text_response(400, f"Slack OAuth error: {error}")

    code = params.get("code", "").strip()
    state = params.get("state", "").strip()
    if not code or not state:
        raise HttpError(400, "Missing OAuth code or state.")

    tenant_id = _decode_state(state)
    if not settings.SLACK_CLIENT_ID or not settings.SLACK_CLIENT_SECRET:
        raise HttpError(500, "Slack OAuth client credentials are not configured.")

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_response = await client.post(
            _SLACK_TOKEN_URL,
            data={
                "client_id": settings.SLACK_CLIENT_ID,
                "client_secret": settings.SLACK_CLIENT_SECRET,
                "code": code,
                "redirect_uri": slack_callback_url(event),
            },
        )

    try:
        payload = token_response.json()
    except ValueError:
        payload = {}
    if token_response.status_code != 200 or not payload.get("ok"):
        detail = payload.get("error") if isinstance(payload, dict) else token_response.text
        logger.error("slack_oauth_exchange_failed status=%s error=%s", token_response.status_code, detail)
        raise HttpError(502, "Failed to exchange Slack authorization code.")

    team = payload.get("team") if isinstance(payload.get("team"), dict) else {}
    team_id = str(team.get("id") or "")
    team_name = str(team.get("name") or team_id)
    bot_token = str(payload.get("access_token") or "").strip()
    if not team_id:
        raise HttpError(502, "Slack did not return a workspace team_id.")
    if not bot_token:
        raise HttpError(502, "Slack did not return a bot token.")

    try:
        await upsert_slack_app_integration(
            tenant_id=tenant_id,
            team_id=team_id,
            team_name=team_name,
            bot_token=bot_token,
            session=session,
        )
    except ValueError as exc:
        return text_response(400, str(exc))

    logger.info("slack_oauth_install_complete tenant_id=%s team_id=%s", tenant_id, team_id)
    webapp = settings.WEBAPP_URL.rstrip("/")
    return text_response(200, f"Slack workspace {team_name} connected. Return to Axes: {webapp}")
