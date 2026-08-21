"""Slack Bolt AsyncApp instance and event handlers."""

from __future__ import annotations

import asyncio
import logging

from slack_bolt.async_app import AsyncApp

from slack_app.config import slack_settings
from slack_app.handlers import handle_message_event

logger = logging.getLogger(__name__)

bolt_app = AsyncApp(
    signing_secret=slack_settings.SLACK_SIGNING_SECRET,
    token=slack_settings.SLACK_BOT_TOKEN,
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
