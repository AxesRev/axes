"""Pydantic models for MCP tool I/O (FastMCP structured tools → MCP JSON schemas)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunCypherOutput(BaseModel):
    """Structured tool result; serialized as MCP ``structuredContent`` when supported."""

    model_config = ConfigDict(extra="forbid")

    rows: list[dict[str, Any]] = Field(description="One dict per record; keys are column names.")
    row_count: int = Field(description="Number of rows returned.")
