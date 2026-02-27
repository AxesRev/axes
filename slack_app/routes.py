"""Slack app API routes."""

import hashlib
import hmac
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from slack_app.config import slack_settings
from slack_app.handlers import handle_message_event

router = APIRouter()


def verify_slack_request(request_body: bytes, timestamp: str, signature: str) -> bool:
    """
    Verify that the request came from Slack.

    Args:
        request_body: The raw request body
        timestamp: The X-Slack-Request-Timestamp header
        signature: The X-Slack-Signature header

    Returns:
        True if the request is valid, False otherwise
    """
    # Avoid replay attacks
    if abs(time.time() - int(timestamp)) > 60 * 5:
        return False

    # Create the signature base string
    sig_basestring = f"v0:{timestamp}:{request_body.decode()}"

    # Create the expected signature
    my_signature = (
        "v0="
        + hmac.new(
            slack_settings.SLACK_SIGNING_SECRET.encode(),
            sig_basestring.encode(),
            hashlib.sha256,
        ).hexdigest()
    )

    # Compare signatures
    return hmac.compare_digest(my_signature, signature)


@router.post("/slack/events")
async def slack_events(request: Request) -> dict[str, Any]:
    """
    Handle Slack Events API callbacks.

    This endpoint receives events from Slack's Events API.
    """
    # Get headers for verification
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    body = await request.body()

    # Verify the request (skip verification if signing secret is not set)
    if slack_settings.SLACK_SIGNING_SECRET and not verify_slack_request(body, timestamp, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid request signature",
        )

    # Parse the request body
    data = await request.json()

    # Handle URL verification challenge
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}

    # Handle events
    if data.get("type") == "event_callback":
        event = data.get("event", {})
        event_type = event.get("type")

        # Ignore bot messages to avoid loops
        if event.get("bot_id"):
            return {"status": "ok"}

        # Handle different event types
        if event_type == "message":
            await handle_message_event(event)
            return {"status": "ok"}

    return {"status": "ok"}


@router.post("/slack/commands")
async def slack_commands(request: Request) -> dict[str, str]:
    """
    Handle Slack slash commands.

    This endpoint receives slash command requests from Slack.
    """
    form_data = await request.form()
    command = form_data.get("command", "")
    text = form_data.get("text", "")
    user_name = form_data.get("user_name", "")

    print(f"Received command: {command} from {user_name} with text: {text}")

    # Return a dummy response
    response_text = f"Hello {user_name}! You executed `{command}` with text: '{text}'. This is a dummy response!"
    return {
        "response_type": "in_channel",
        "text": response_text,
    }


@router.get("/slack/health")
async def slack_health() -> dict[str, str]:
    """Health check endpoint for Slack app."""
    return {"status": "healthy", "service": "slack_app"}
