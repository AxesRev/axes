"""Slack event handlers."""

import logging
from typing import Any

from langgraph_sdk import get_client

from slack_app.client import post_message
from slack_app.config import slack_settings

logger = logging.getLogger(__name__)

# Map Slack user IDs to LangGraph thread IDs
# In production, this should be stored in a database
USER_THREADS: dict[str, str] = {}


async def handle_message_event(event: dict[str, Any]) -> None:
    """
    Handle incoming Slack message events by invoking the Salesforce permissions agent.

    Args:
        event: The Slack event payload
    """
    user_id = event.get("user")
    if not user_id:
        return

    text = event.get("text", "")
    channel = event.get("channel", "")
    ts = event.get("ts", "")

    # Skip bot messages
    if event.get("bot_id"):
        return

    print(f"Received message from {user_id} in channel {channel}: {text}")

    # Initialize LangGraph client
    client = get_client(url=slack_settings.LANGGRAPH_API_URL)

    # Get or create thread for this user
    thread_id = USER_THREADS.get(user_id)
    if not thread_id:
        thread = await client.threads.create()
        thread_id = thread["thread_id"]
        USER_THREADS[user_id] = thread_id
        logger.info(f"Created new thread {thread_id} for user {user_id}")

    # Invoke the agent
    # Using the salesforce_permissions graph configured in aegra.json
    try:
        # We use client.runs.create_and_wait for simplicity as Slack bot doesn't stream chunks
        result = await client.runs.create_and_wait(
            thread_id=thread_id,
            assistant_id="salesforce_permissions",
            input={"messages": [{"type": "human", "content": text}]},
        )

        # The final result is in the state of the thread
        # For a ReAct agent, the last message is usually the AI response
        if result and "messages" in result:
            messages = result["messages"]
            if messages and messages[-1]["type"] == "ai":
                response_text = messages[-1]["content"]
                await post_message(
                    channel=channel,
                    text=response_text,
                    thread_ts=ts,
                )
    except Exception as e:
        logger.error(f"Error invoking LangGraph agent: {e}")
        await post_message(
            channel=channel,
            text=f"Sorry, I encountered an error: {e}",
            thread_ts=ts,
        )
