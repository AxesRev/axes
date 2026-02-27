"""Slack Web API client for sending messages."""

from typing import Any

import httpx

from slack_app.config import slack_settings

SLACK_API_BASE = "https://slack.com/api"


async def post_message(channel: str, text: str, thread_ts: str | None = None) -> dict:
    """
    Post a message to a Slack channel using the Web API.

    Args:
        channel: Channel ID to post to
        text: Message text to send
        thread_ts: Optional thread timestamp to reply in a thread

    Returns:
        Response from Slack API
    """
    url = f"{SLACK_API_BASE}/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {slack_settings.SLACK_BOT_TOKEN}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "channel": channel,
        "text": text,
    }

    if thread_ts:
        payload["thread_ts"] = thread_ts

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        return response.json()
