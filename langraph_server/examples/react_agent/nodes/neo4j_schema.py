"""Node that loads the Neo4j schema for prompt injection."""

from __future__ import annotations

import logging
from typing import Any

from examples.react_agent.nodes.tools import fetch_neo4j_schema
from examples.react_agent.state import State

logger = logging.getLogger(__name__)


async def load_neo4j_schema(_state: State) -> dict[str, Any]:
    """Fetch the graph schema once so later agents can write Cypher against it."""
    try:
        schema = await fetch_neo4j_schema()
    except Exception:
        logger.exception("load_neo4j_schema: failed")
        return {"neo4j_schema": ""}

    if not schema:
        logger.info("load_neo4j_schema: empty schema")
        return {"neo4j_schema": ""}

    logger.info("load_neo4j_schema: loaded %d characters", len(schema))
    return {"neo4j_schema": schema}
