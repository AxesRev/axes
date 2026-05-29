"""Bolt AsyncApp wired into the Aegra FastAPI server."""

from __future__ import annotations

import asyncio
import logging

from slack_bolt.async_app import AsyncApp
from slack_bolt.oauth.async_oauth_flow import AsyncOAuthFlow
from slack_bolt.oauth.oauth_settings import OAuthSettings
from slack_bolt.oauth.state_store.file import FileOAuthStateStore

from app_integrations.slack.installation_store import AxesInstallationStore
from slack_app.config import slack_settings
from slack_app.handlers import handle_message_event

logger = logging.getLogger(__name__)

_oauth_flow: AsyncOAuthFlow | None = None
if slack_settings.SLACK_CLIENT_ID and slack_settings.SLACK_CLIENT_SECRET:
    _oauth_flow = AsyncOAuthFlow(
        settings=OAuthSettings(
            client_id=slack_settings.SLACK_CLIENT_ID,
            client_secret=slack_settings.SLACK_CLIENT_SECRET,
            installation_store=AxesInstallationStore(),
            state_store=FileOAuthStateStore(expiration_seconds=300),
            redirect_uri=slack_settings.slack_oauth_redirect_uri,
        )
    )

bolt_app = AsyncApp(
    signing_secret=slack_settings.SLACK_SIGNING_SECRET or "dev",
    token=slack_settings.SLACK_BOT_TOKEN if not _oauth_flow else None,
    oauth_flow=_oauth_flow,
)


@bolt_app.event("message")
async def on_message(event: dict, logger: logging.Logger) -> None:  # type: ignore[override]
    if event.get("subtype") is not None:
        return
    asyncio.create_task(handle_message_event(event))


@bolt_app.command("/axes")
async def on_axes_command(ack: object, body: dict) -> None:  # type: ignore[type-arg]
    await ack()  # type: ignore[misc]
    logger.info("slash_command_axes user=%s text=%r", body.get("user_id"), body.get("text"))
