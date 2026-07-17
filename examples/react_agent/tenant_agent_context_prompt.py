"""Prompt helpers for tenant-specific agent context."""

from __future__ import annotations


def build_tenant_agent_context_block(content: str) -> str:
    """Return the tenant-context block for system prompts, or empty string."""
    stripped = content.strip()
    if not stripped:
        return ""
    return f"Tenant-specific policy and instructions from the organisation admin:\n{stripped}\n\n"
