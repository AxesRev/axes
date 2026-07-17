"""Slack event handlers."""

from __future__ import annotations

import logging
from typing import Any

from langgraph_sdk import get_client

from aegra_api.core.orm import get_session
from app_integrations.github.identity_linking import handle_access_request
from app_integrations.github.settings import github_settings
from app_integrations.slack.service import get_or_create_slack_user_identity_for_team
from slack_app.client import fetch_user_email, post_message
from slack_app.config import slack_settings
from slack_app.replies import slack_replies_from_updates

logger = logging.getLogger(__name__)

# Map Slack thread root timestamps to LangGraph thread IDs.
# Key: Slack channel + ":" + root message ts  →  LangGraph thread_id.
# In production this should be persisted in a database.
SLACK_THREAD_MAP: dict[str, str] = {}


async def handle_message_event(event: dict[str, Any], *, team_id: str | None = None) -> None:
    """Handle an incoming Slack message by invoking the LangGraph agent.

    Threading behaviour:
    - A **top-level message** (no ``thread_ts`` in the event) always starts a
      brand-new LangGraph thread and opens a new Slack reply-thread.
    - A **thread reply** (``thread_ts`` present) continues the LangGraph thread
      that was created when the parent Slack message arrived.  If no mapping
      exists (e.g. the thread pre-dates this bot), the reply is silently ignored.

    Args:
        event: The raw Slack event payload.
    """
    user_id: str | None = event.get("user")
    if not user_id:
        return

    resolved_team_id = team_id or event.get("team")
    if not isinstance(resolved_team_id, str) or not resolved_team_id:
        logger.debug("Ignoring Slack message without team_id for user %s", user_id)
        return

    text: str = event.get("text", "")
    channel: str = event.get("channel", "")
    ts: str = event.get("ts", "")
    thread_ts: str | None = event.get("thread_ts")

    # Skip bot messages to prevent feedback loops.
    if event.get("bot_id"):
        return

    # Determine whether this is a top-level message or a thread reply.
    is_thread_reply: bool = thread_ts is not None and thread_ts != ts

    if is_thread_reply:
        # Only continue if this thread was started by our bot.
        map_key = f"{channel}:{thread_ts}"
        if map_key not in SLACK_THREAD_MAP:
            logger.debug("Ignoring reply in untracked thread %s (channel %s)", thread_ts, channel)
            return
        # Replies are posted back into the same thread.
        reply_thread_ts: str = thread_ts  # type: ignore[assignment]
    else:
        # Top-level message — a new Slack thread will be opened by replying with
        # thread_ts=ts, so the root message becomes the thread parent.
        reply_thread_ts = ts

    logger.info("Received message from %s in channel %s: %s", user_id, channel, text)

    access_result = None
    async for session in get_session():
        identity = await get_or_create_slack_user_identity_for_team(
            slack_user_id=user_id,
            team_id=resolved_team_id,
            session=session,
        )
        if identity is None:
            break

        access_result = await handle_access_request(
            identity,
            {"text": text, "channel": channel},
            session,
            server_url=github_settings.SERVER_URL,
        )
        break

    if access_result is None:
        logger.info(
            "Ignoring Slack message from unregistered workspace team_id=%s user=%s",
            resolved_team_id,
            user_id,
        )
        return

    if not access_result.linked:
        not_linked = access_result.not_linked
        connect_url = not_linked.connect_url if not_linked else ""
        await post_message(
            channel=channel,
            text=(
                "Before I can act on your behalf, I need to know your GitHub account. "
                f"Please connect it here: {connect_url}"
            ),
            thread_ts=reply_thread_ts,
        )
        return

    assert access_result.identity is not None
    github_user_id = access_result.identity.github_user_id
    github_email = access_result.identity.github_email
    github_installation_id = access_result.identity.github_installation_id
    tenant_id = identity.tenant_id
    slack_email = await fetch_user_email(user_id) or ""

    # --- Agent invocation ------------------------------------------------------
    client = get_client(url=slack_settings.LANGGRAPH_API_URL, headers={"X-Slack-User-ID": user_id})

    map_key = f"{channel}:{reply_thread_ts}"

    if is_thread_reply:
        # The mapping was already confirmed to exist above.
        thread_id: str = SLACK_THREAD_MAP[map_key]
        logger.info("Continuing thread %s for Slack thread %s", thread_id, reply_thread_ts)
    else:
        # New top-level message — always create a fresh LangGraph thread.
        thread = await client.threads.create()
        thread_id = thread["thread_id"]
        SLACK_THREAD_MAP[map_key] = thread_id
        logger.info(
            "Created new LangGraph thread %s for Slack thread %s (user %s)",
            thread_id,
            reply_thread_ts,
            user_id,
        )

    try:
        posted_replies = 0
        run_status: str | None = None

        async for chunk in client.runs.stream(
            thread_id=thread_id,
            assistant_id="agent",
            input={"messages": [{"role": "user", "content": text}]},
            config={
                "configurable": {
                    "slack_user_id": user_id,
                    "slack_email": slack_email,
                    "tenant_id": tenant_id,
                    "github_user_id": github_user_id,
                    "github_email": github_email,
                    "github_installation_id": github_installation_id,
                }
            },
            stream_mode=["updates"],
        ):
            if chunk.event == "updates":
                for reply_text in slack_replies_from_updates(chunk.data):
                    await post_message(
                        channel=channel,
                        text=reply_text,
                        thread_ts=reply_thread_ts,
                    )
                    posted_replies += 1
            elif chunk.event == "end":
                run_status = chunk.data.get("status")

        if posted_replies == 0:
            logger.warning(
                "Run produced no Slack replies for user %s (status=%r)",
                user_id,
                run_status,
            )
            await post_message(
                channel=channel,
                text="Sorry, I encountered an error processing your request. Please try again.",
                thread_ts=reply_thread_ts,
            )
    except Exception:
        logger.exception("Error invoking LangGraph agent for user %s", user_id)
        await post_message(
            channel=channel,
            text="Sorry, I encountered an error processing your request. Please try again.",
            thread_ts=reply_thread_ts,
        )
