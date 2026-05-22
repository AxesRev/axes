"""Access grant execution subgraph."""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import StateGraph
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.state import State

logger = logging.getLogger(__name__)


async def dummy_grant(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Placeholder node for access grant execution."""
    logger.info("dummy_grant: access grant execution not implemented yet")
    return {}


builder = StateGraph(State, context_schema=Context)

builder.add_node("dummy_grant", dummy_grant)

builder.add_edge("__start__", "dummy_grant")
builder.add_edge("dummy_grant", "__end__")

access_grant_execution_graph = builder.compile(name="Access Grant Execution")
