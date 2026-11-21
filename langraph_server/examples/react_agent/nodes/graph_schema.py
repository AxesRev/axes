"""Node that loads the access graph schema for prompt injection."""

from __future__ import annotations

from typing import Any

from common.graph_schema import schema_prompt
from examples.react_agent.state import State


async def load_graph_schema(_state: State) -> dict[str, Any]:
    """Provide the static graph schema (same definition ingestion creates) to later agents."""
    return {"graph_schema": schema_prompt()}
