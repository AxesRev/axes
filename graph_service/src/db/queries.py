"""Low-level Neo4j query helpers.

All public functions accept an explicit ``AsyncDriver`` so they remain
easily testable without touching the module-level singleton.

This workspace keeps Neo4j access **read-only** at the MCP boundary.
``run_write_query`` is disabled and always raises.
"""

from collections.abc import Mapping
from typing import Any, NoReturn

import structlog
from neo4j import AsyncDriver

from neo4j_mcp.settings import get_settings

logger = structlog.get_logger(__name__)


async def run_read_query(
    driver: AsyncDriver,
    query: str,
    *,
    parameters: Mapping[str, Any] | None = None,
    database: str | None = None,
) -> list[dict[str, Any]]:
    """Execute a read-only Cypher query and return all rows as dicts."""
    db = database or get_settings().neo4j_database
    async with driver.session(database=db) as session:
        result = await session.run(query, dict(parameters or {}))
        records: list[dict[str, Any]] = await result.data()
    logger.debug("neo4j_read_query_executed", query=query, row_count=len(records))
    return records


async def run_write_query(
    driver: AsyncDriver,
    query: str,
    *,
    parameters: Mapping[str, Any] | None = None,
    database: str | None = None,
) -> NoReturn:
    """Write queries are not supported in this configuration."""
    del driver, query, parameters, database
    raise PermissionError(
        "Neo4j writes are disabled for this service. Use run_read_query or enable a dedicated write path elsewhere."
    )
