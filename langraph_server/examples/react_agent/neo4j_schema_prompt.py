"""Prompt helper for the injected Neo4j schema."""

from __future__ import annotations


def build_neo4j_schema_block(schema: str) -> str:
    """Return the schema block for system prompts, or empty string."""
    stripped = schema.strip()
    if not stripped:
        return ""
    return (
        "Neo4j graph schema. Cypher must use these labels, properties, and relationships. "
        "Do not invent labels or property names.\n"
        f"{stripped}\n\n"
    )
