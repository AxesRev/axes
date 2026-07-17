"""Prompt helpers for graph-backed user context."""

from __future__ import annotations

from collections.abc import Sequence

from examples.react_agent.user_context_models import UserContextData


def build_user_context_block(user_contexts: Sequence[UserContextData] | UserContextData | None) -> str:
    """Return the user-context block for system prompts, or empty string."""
    if user_contexts is None:
        return ""
    if isinstance(user_contexts, UserContextData):
        return user_contexts.format_for_prompt()
    blocks = [context.format_for_prompt() for context in user_contexts]
    return "\n".join(block for block in blocks if block.strip())
