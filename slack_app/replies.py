"""Helpers for turning LangGraph stream updates into Slack replies."""

from __future__ import annotations

from typing import Any

SLACK_OUTPUT_NODES: frozenset[str] = frozenset(
    {"permission_detection", "access_request_evaluation", "access_grant_execution"}
)
SLACK_FINAL_AI_ONLY_NODES: frozenset[str] = frozenset({"access_grant_execution"})


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


def latest_ai_content(node_update: dict[str, Any], *, final_only: bool = False) -> str | None:
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
        if final_only and message.get("tool_calls"):
            continue
        content = _message_content(message)
        if content:
            ai_contents.append(content)
    return ai_contents[-1] if ai_contents else None


def _collect_output_updates(data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Collect message-bearing updates for Slack output nodes, including nested subgraph steps."""
    collected: list[tuple[str, dict[str, Any]]] = []

    def walk(payload: dict[str, Any], active_output: str | None = None) -> None:
        for key, value in payload.items():
            if not isinstance(value, dict):
                continue

            current_output = key if key in SLACK_OUTPUT_NODES else active_output
            if "messages" in value and current_output is not None:
                collected.append((current_output, value))
            walk(value, current_output)

    walk(data)
    return collected


def slack_replies_from_updates(data: dict[str, Any]) -> list[str]:
    """Extract Slack-ready AI replies from a LangGraph ``updates`` stream event."""
    replies: list[str] = []
    for node_name, node_update in _collect_output_updates(data):
        content = latest_ai_content(
            node_update,
            final_only=node_name in SLACK_FINAL_AI_ONLY_NODES,
        )
        if content:
            replies.append(content)
    return replies
