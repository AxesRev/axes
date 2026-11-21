"""Prompt helper for the injected access graph schema."""

from __future__ import annotations


def build_graph_schema_block(schema: str) -> str:
    """Return the schema block for system prompts, or empty string."""
    stripped = schema.strip()
    if not stripped:
        return ""
    return (
        "Access graph schema (ArcadeDB, queried with Cypher). Use these labels, properties, and relationships. "
        "Do not invent labels or property names.\n"
        f"{stripped}\n\n"
    )
