"""Helpers for turning LangGraph stream updates into Slack replies."""

from __future__ import annotations

from typing import Any

SLACK_OUTPUT_NODES: frozenset[str] = frozenset({"permission_detection", "access_request_evaluation"})


def _message_content(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text", "")))
        return "".join(parts).strip()
    return str(content)


def latest_ai_content(node_update: dict[str, Any]) -> str | None:
    """Return the latest AI message content from a node update, if any."""
    messages = node_update.get("messages")
    if not isinstance(messages, list):
        return None

    ai_contents: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("type") != "ai":
            continue
        content = _message_content(message)
        if content:
            ai_contents.append(content)
    return ai_contents[-1] if ai_contents else None


def slack_replies_from_updates(data: dict[str, Any]) -> list[str]:
    """Extract Slack-ready AI replies from a LangGraph ``updates`` stream event."""
    replies: list[str] = []
    for node_name, node_update in data.items():
        if node_name not in SLACK_OUTPUT_NODES:
            continue
        if not isinstance(node_update, dict):
            continue
        content = latest_ai_content(node_update)
        if content:
            replies.append(content)
    return replies
