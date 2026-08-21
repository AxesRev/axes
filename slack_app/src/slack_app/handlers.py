"""Slack event handlers."""

from __future__ import annotations

import logging
from typing import Any

from langgraph_sdk import get_client

from slack_app.client import fetch_user_email, post_message
from slack_app.config import slack_settings
from slack_app.db import session_scope
from slack_app.replies import slack_replies_from_updates
from slack_app.store import get_or_create_slack_user_identity_for_team, resolve_github_access

logger = logging.getLogger(__name__)

_SLACK_CHANNEL_META = "slack_channel"
_SLACK_THREAD_TS_META = "slack_thread_ts"


def _slack_thread_metadata(channel: str, thread_ts: str) -> dict[str, str]:
    return {_SLACK_CHANNEL_META: channel, _SLACK_THREAD_TS_META: thread_ts}


async def _find_langgraph_thread_id(client: Any, channel: str, thread_ts: str) -> str | None:
    threads = await client.threads.search(
        metadata=_slack_thread_metadata(channel, thread_ts),
        limit=1,
    )
    if not threads:
        return None
    return threads[0]["thread_id"]


async def handle_message_event(event: dict[str, Any], *, team_id: str | None = None) -> None:
    """Handle an incoming Slack message by invoking the LangGraph agent.

    Threading behaviour:
    - A **top-level message** (no ``thread_ts`` in the event) always starts a
      brand-new LangGraph thread and opens a new Slack reply-thread.
    - A **thread reply** (``thread_ts`` present) continues the LangGraph thread
      that was created when the parent Slack message arrived.  If no LangGraph
      thread is found for that Slack thread, the reply is silently ignored.

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
        reply_thread_ts: str = thread_ts  # type: ignore[assignment]
    else:
        # Top-level message — a new Slack thread will be opened by replying with
        # thread_ts=ts, so the root message becomes the thread parent.
        reply_thread_ts = ts

    logger.info("Received message from %s in channel %s: %s", user_id, channel, text)

    access_result = None
    tenant_id = ""
    async with session_scope() as session:
        identity = await get_or_create_slack_user_identity_for_team(
            slack_user_id=user_id,
            team_id=resolved_team_id,
            session=session,
        )
        if identity is not None:
            access_result = await resolve_github_access(
                identity,
                session,
                server_url=slack_settings.integrations_public_url,
            )
            tenant_id = identity.tenant_id

    if access_result is None:
        logger.info(
            "Ignoring Slack message from unregistered workspace team_id=%s user=%s",
            resolved_team_id,
            user_id,
        )
        return

    client = get_client(url=slack_settings.LANGGRAPH_API_URL, headers={"X-Slack-User-ID": user_id})
    thread_id: str | None = None

    if is_thread_reply:
        thread_id = await _find_langgraph_thread_id(client, channel, reply_thread_ts)
        if thread_id is None:
            logger.debug("Ignoring reply in untracked thread %s (channel %s)", reply_thread_ts, channel)
            return
        logger.info("Continuing thread %s for Slack thread %s", thread_id, reply_thread_ts)

    if not access_result.linked:
        await post_message(
            channel=channel,
            text=(
                "Before I can act on your behalf, I need to know your GitHub account. "
                f"Please connect it here: {access_result.connect_url}"
            ),
            thread_ts=reply_thread_ts,
        )
        return

    github_user_id = access_result.github_user_id
    github_email = access_result.github_email
    github_installation_id = access_result.github_installation_id
    slack_email = await fetch_user_email(user_id) or ""

    if thread_id is None:
        thread = await client.threads.create(
            metadata=_slack_thread_metadata(channel, reply_thread_ts),
        )
        thread_id = thread["thread_id"]
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
