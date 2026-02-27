"""Slack event handlers."""

import logging
from typing import Any

from app.agents.runner import run_permission_request_graph

from slack_app.client import post_message

logger = logging.getLogger(__name__)


async def handle_message_event(event: dict[str, Any]) -> None:
    """
    Handle incoming Slack message events.

    Args:
        event: The Slack event payload
    """
    user = event.get("user", "Unknown user")
    text = event.get("text", "")
    channel = event.get("channel", "")
    ts = event.get("ts", "")

    print(f"Received message from {user} in channel {channel}: {text}")

    # Check for permission request keyword
    if "request permission" in text.lower():
        await handle_permission_request(event)
        return

    # Send "hello world" response back to Slack
    await post_message(
        channel=channel,
        text="hello world",
        thread_ts=ts,
    )


async def handle_permission_request(event: dict[str, Any]) -> None:
    """
    Handle permission request workflow trigger.

    Triggered when user sends a message containing "request permission".

    Args:
        event: The Slack event payload
    """
    user_id = event.get("user", "")
    channel = event.get("channel", "")
    ts = event.get("ts", "")

    logger.info(f"[Handler] Permission request from user {user_id} in channel {channel}")

    # Send acknowledgment
    await post_message(
        channel=channel,
        text="🔄 Processing your permission request...",
        thread_ts=ts,
    )

    try:
        # Execute permission request graph
        final_state = await run_permission_request_graph(
            slack_user_id=user_id,
            slack_channel=channel,
            slack_thread_ts=ts,
        )

        # Send completion message
        if final_state.get("error"):
            await post_message(
                channel=channel,
                text=f"❌ Error processing request: {final_state['error']}",
                thread_ts=ts,
            )
        else:
            request_id = final_state.get("request_id", "unknown")
            permission_name = final_state.get("permission_set_name", "unknown")
            owner_id = final_state.get("app_owner_slack_id", "unknown")

            await post_message(
                channel=channel,
                text=f"✅ Your request for `{permission_name}` has been sent to <@{owner_id}> for approval.\n\nRequest ID: `{request_id}`",
                thread_ts=ts,
            )

    except Exception as e:
        logger.error(f"[Handler] Error in permission request: {e}")
        await post_message(
            channel=channel,
            text=f"❌ An error occurred while processing your request: {str(e)}",
            thread_ts=ts,
        )


async def handle_app_mention(event: dict[str, Any]) -> None:
    """
    Handle app mention events.

    Args:
        event: The Slack event payload
    """
    user = event.get("user", "Unknown user")
    text = event.get("text", "")
    channel = event.get("channel", "")
    ts = event.get("ts", "")

    print(f"App mentioned by {user} in channel {channel}: {text}")

    # Send "hello world" response back to Slack
    await post_message(
        channel=channel,
        text="hello world",
        thread_ts=ts,
    )
