"""Helpers for turning LangGraph stream updates into Slack replies."""

from __future__ import annotations

from typing import Any

SLACK_OUTPUT_NODES: frozenset[str] = frozenset(
    {"respond_unsupported_app", "permission_detection", "access_request_evaluation", "access_grant_execution"}
)


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


def ai_message_contents(node_update: dict[str, Any]) -> list[str]:
    """Return every AI message with text from a node update, in order."""
    messages = node_update.get("messages")
    if not isinstance(messages, list):
        return []

    contents: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("type") != "ai":
            continue
        content = _message_content(message)
        if content:
            contents.append(content)
    return contents


def _has_nested_messages(payload: dict[str, Any]) -> bool:
    for key, value in payload.items():
        if key == "messages" or not isinstance(value, dict):
            continue
        if "messages" in value or _has_nested_messages(value):
            return True
    return False


def _collect_output_updates(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect the innermost message lists under Slack output nodes."""
    collected: list[dict[str, Any]] = []

    def walk(payload: dict[str, Any], active_output: str | None = None) -> None:
        for key, value in payload.items():
            if not isinstance(value, dict):
                continue
            current_output = key if key in SLACK_OUTPUT_NODES else active_output
            walk(value, current_output)
            if current_output is not None and "messages" in value and not _has_nested_messages(value):
                collected.append(value)

    walk(data)
    return collected


def slack_replies_from_updates(data: dict[str, Any]) -> list[str]:
    """Extract every completed AI message from a LangGraph ``updates`` event."""
    replies: list[str] = []
    for node_update in _collect_output_updates(data):
        replies.extend(ai_message_contents(node_update))
    return replies
