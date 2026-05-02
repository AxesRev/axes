"""Slack event handlers."""

from __future__ import annotations

import logging
from typing import Any

from langgraph_sdk import get_client

from slack_app.client import post_message
from slack_app.config import slack_settings

logger = logging.getLogger(__name__)

# Map Slack user IDs to LangGraph thread IDs.
# In production this should be persisted in a database.
USER_THREADS: dict[str, str] = {}


async def handle_message_event(event: dict[str, Any]) -> None:
    """Handle an incoming Slack message by resolving the sender's GitHub identity
    and then invoking the LangGraph agent.

    Flow:
    1. Extract the Slack ``user_id`` from the event.
    2. Resolve the GitHub identity via ``handle_access_request``.
    3. If the identity is not yet linked, reply with a connect link and stop.
    4. If linked, invoke the agent with the verified ``github_username`` so the
       agent never trusts user-supplied identity claims.

    Args:
        event: The raw Slack event payload.
    """
    user_id: str | None = event.get("user")
    if not user_id:
        return

    text: str = event.get("text", "")
    channel: str = event.get("channel", "")
    ts: str = event.get("ts", "")

    # Skip bot messages to prevent feedback loops.
    if event.get("bot_id"):
        return

    logger.info("Received message from %s in channel %s: %s", user_id, channel, text)

    # --- Identity resolution ---------------------------------------------------
    # Import here to avoid a circular dependency at module load time if handlers
    # is imported before the DB is initialised; the import itself is cheap.
    from aegra_api.core.orm import get_session
    from app_integrations.github.service import handle_access_request
    from app_integrations.github.settings import github_settings

    async for session in get_session():
        access_result = await handle_access_request(
            user_id,
            {"text": text, "channel": channel},
            session,
            server_url=github_settings.SERVER_URL,
        )

    if not access_result.linked:
        # User has not linked their GitHub account yet — prompt them.
        not_linked = access_result.not_linked
        connect_url = not_linked.connect_url if not_linked else ""
        await post_message(
            channel=channel,
            text=(
                f"Before I can act on your behalf, I need to know your GitHub account. "
                f"Please connect it here: {connect_url}"
            ),
            thread_ts=ts,
        )
        return

    # Identity is confirmed — use only the stored github_username.
    assert access_result.identity is not None
    github_username: str = access_result.identity.github_username

    # --- Agent invocation ------------------------------------------------------
    # Initialize LangGraph client with the Slack user ID in headers for authentication
    client = get_client(url=slack_settings.LANGGRAPH_API_URL, headers={"X-Slack-User-ID": user_id})

    thread_id: str | None = USER_THREADS.get(user_id)
    if not thread_id:
        thread = await client.threads.create()
        thread_id = thread["thread_id"]
        USER_THREADS[user_id] = thread_id
        logger.info("Created new thread %s for user %s", thread_id, user_id)

    try:
        run = await client.runs.create(
            thread_id=thread_id,
            assistant_id="agent",
            input={
                "messages": [{"role": "user", "content": text}],
                # Pass the verified GitHub username so the agent never reads it
                # from the message text or any client-controlled field.
                "github_username": github_username,
            },
            config={"configurable": {"slack_user_id": user_id}},
        )
        result = await client.runs.join(thread_id, run["run_id"])

        if result and "messages" in result:
            messages = result["messages"]
            if messages and messages[-1]["type"] == "ai":
                response_text = messages[-1]["content"]
                await post_message(
                    channel=channel,
                    text=response_text,
                    thread_ts=ts,
                )
    except Exception:
        logger.exception("Error invoking LangGraph agent for user %s", user_id)
        await post_message(
            channel=channel,
            text="Sorry, I encountered an error processing your request. Please try again.",
            thread_ts=ts,
        )
