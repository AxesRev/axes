"""Slack event handlers."""

from __future__ import annotations

import logging
from typing import Any

from langgraph_sdk import get_client

from slack_app.client import post_message
from slack_app.config import slack_settings

logger = logging.getLogger(__name__)

# Map Slack thread root timestamps to LangGraph thread IDs.
# Key: Slack channel + ":" + root message ts  →  LangGraph thread_id.
# In production this should be persisted in a database.
SLACK_THREAD_MAP: dict[str, str] = {}


async def handle_message_event(event: dict[str, Any]) -> None:
    """Handle an incoming Slack message by resolving the sender's GitHub identity
    and then invoking the LangGraph agent.

    Threading behaviour:
    - A **top-level message** (no ``thread_ts`` in the event) always starts a
      brand-new LangGraph thread and opens a new Slack reply-thread.
    - A **thread reply** (``thread_ts`` present) continues the LangGraph thread
      that was created when the parent Slack message arrived.  If no mapping
      exists (e.g. the thread pre-dates this bot), the reply is silently ignored.

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
            thread_ts=reply_thread_ts,
        )
        return

    # Identity is confirmed — use only the stored values from the database.
    assert access_result.identity is not None
    github_username: str = access_result.identity.github_username
    github_user_id: str = access_result.identity.github_user_id

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
        run = await client.runs.create(
            thread_id=thread_id,
            assistant_id="agent",
            input={"messages": [{"role": "user", "content": text}]},
            # Pass the verified GitHub identity via configurable so the agent's
            # Context picks it up and includes it in the system prompt.
            config={
                "configurable": {
                    "slack_user_id": user_id,
                    "github_username": github_username,
                    "github_user_id": github_user_id,
                }
            },
        )
        result = await client.runs.join(thread_id, run["run_id"])

        response_text: str | None = None
        if result and "messages" in result:
            messages = result["messages"]
            if messages and messages[-1]["type"] == "ai":
                response_text = messages[-1]["content"]

        if response_text:
            await post_message(
                channel=channel,
                text=response_text,
                thread_ts=reply_thread_ts,
            )
        else:
            # Run failed or produced no AI message (e.g. tool error, empty output).
            logger.warning(
                "Run %s produced no AI response for user %s (result keys: %s)",
                run["run_id"],
                user_id,
                list(result.keys()) if result else [],
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
