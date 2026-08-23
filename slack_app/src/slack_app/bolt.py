"""Slack Bolt AsyncApp instance and event handlers."""

from __future__ import annotations

import asyncio
import logging

from slack_bolt.async_app import AsyncApp
from slack_bolt.authorization import AuthorizeResult

from slack_app.config import slack_settings
from slack_app.db import session_scope
from slack_app.handlers import handle_message_event
from slack_app.store import find_slack_bot_token

logger = logging.getLogger(__name__)


async def authorize(
    enterprise_id: str | None,
    team_id: str | None,
    user_id: str | None,  # noqa: ARG001
    client: object,  # noqa: ARG001
    logger: logging.Logger,
) -> AuthorizeResult | None:
    """Load the workspace bot token saved during Slack OAuth.

    AsyncApp is created without a static ``token``, so Bolt treats this as a
    multi-workspace app and will reject events unless ``authorize`` returns
    an ``AuthorizeResult``.
    """
    if not team_id:
        logger.error("slack_authorize_missing_team_id")
        return None
    async with session_scope() as session:
        bot_token = await find_slack_bot_token(session, team_id=team_id)
    if not bot_token:
        logger.error("slack_authorize_no_install team_id=%s", team_id)
        return None
    return AuthorizeResult(enterprise_id=enterprise_id, team_id=team_id, bot_token=bot_token)


bolt_app = AsyncApp(
    signing_secret=slack_settings.SLACK_SIGNING_SECRET,
    authorize=authorize,
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
