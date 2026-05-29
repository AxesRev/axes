"""Slack Bolt AsyncApp instance and event handlers."""

from __future__ import annotations

import asyncio
import logging

from slack_bolt.async_app import AsyncApp
from slack_bolt.oauth.async_oauth_settings import AsyncOAuthSettings

from app_integrations.slack.installation_store import AxesInstallationStore
from app_integrations.slack.oauth_flow import TenantAsyncOAuthFlow
from app_integrations.slack.state_store import TenantOAuthStateStore
from slack_app.config import slack_settings
from slack_app.handlers import handle_message_event

logger = logging.getLogger(__name__)

# Must match scopes in slack_app/slack_manifest.json oauth_config.scopes.bot
_SLACK_BOT_SCOPES = [
    "app_mentions:read",
    "channels:history",
    "chat:write",
    "commands",
    "im:write",
    "im:read",
    "im:history",
]

_oauth_flow: TenantAsyncOAuthFlow | None = None
if slack_settings.SLACK_CLIENT_ID and slack_settings.SLACK_CLIENT_SECRET:
    _state_store = TenantOAuthStateStore(
        expiration_seconds=600,
        client_id=slack_settings.SLACK_CLIENT_ID,
    )
    _oauth_flow = TenantAsyncOAuthFlow(
        settings=AsyncOAuthSettings(
            client_id=slack_settings.SLACK_CLIENT_ID,
            client_secret=slack_settings.SLACK_CLIENT_SECRET,
            scopes=_SLACK_BOT_SCOPES,
            installation_store=AxesInstallationStore(),
            state_store=_state_store,
            redirect_uri=slack_settings.slack_oauth_redirect_uri,
            install_path="/slack/oauth/install",
            redirect_uri_path="/slack/oauth/callback",
            install_page_rendering_enabled=False,
        )
    )

bolt_app = AsyncApp(
    signing_secret=slack_settings.SLACK_SIGNING_SECRET or "dev",
    token=slack_settings.SLACK_BOT_TOKEN if not _oauth_flow else None,
    oauth_flow=_oauth_flow,
)


@bolt_app.event("message")
async def on_message(event: dict, body: dict, logger: logging.Logger) -> None:  # type: ignore[override]
    if event.get("subtype") is not None:
        return
    team_id = body.get("team_id")
    if not isinstance(team_id, str):
        team_id = event.get("team") if isinstance(event.get("team"), str) else None
    asyncio.create_task(handle_message_event(event, team_id=team_id))


@bolt_app.command("/axes")
async def on_axes_command(ack: object, body: dict) -> None:  # type: ignore[type-arg]
    await ack()  # type: ignore[misc]
    logger.info("slash_command_axes user=%s text=%r", body.get("user_id"), body.get("text"))
