"""Prompt helpers for graph-backed user context."""

from __future__ import annotations

from examples.react_agent.user_context_models import UserContextData


def build_user_context_block(user_context: UserContextData | None) -> str:
    """Return the user-context block for system prompts, or empty string."""
    if user_context is None:
        return ""
    return user_context.format_for_prompt()
