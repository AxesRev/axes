"""Slack Web API client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SLACK_API_BASE = "https://slack.com/api"


def _slack_headers(bot_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {bot_token}",
        "Content-Type": "application/json",
    }


async def fetch_user_email(slack_user_id: str, *, bot_token: str) -> str | None:
    """Return the Slack user's profile email via users.info, or None if unavailable."""
    user_id = slack_user_id.strip()
    if not user_id:
        return None
    if not bot_token:
        logger.debug("fetch_user_email: bot token not configured")
        return None

    url = f"{SLACK_API_BASE}/users.info"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=_slack_headers(bot_token), params={"user": user_id})
        data = response.json()

    if not data.get("ok"):
        logger.info(
            "fetch_user_email: users.info failed for user=%s error=%s",
            user_id,
            data.get("error"),
        )
        return None

    profile = data.get("user", {}).get("profile", {})
    email = profile.get("email")
    if not isinstance(email, str) or not email.strip():
        return None
    return email.strip()


async def post_message(channel: str, text: str, thread_ts: str | None = None, *, bot_token: str) -> dict:
    """
    Post a message to a Slack channel using the Web API.

    Args:
        channel: Channel ID to post to
        text: Message text to send
        thread_ts: Optional thread timestamp to reply in a thread
        bot_token: Workspace bot token from the Slack install

    Returns:
        Response from Slack API
    """
    if not bot_token:
        logger.error("post_message: bot token missing channel=%s", channel)
        return {"ok": False, "error": "missing_bot_token"}

    url = f"{SLACK_API_BASE}/chat.postMessage"
    headers = _slack_headers(bot_token)
    payload: dict[str, Any] = {
        "channel": channel,
        "text": text,
    }

    if thread_ts:
        payload["thread_ts"] = thread_ts

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        return response.json()
