"""Low-level Neo4j query helpers.

All public functions accept an explicit ``AsyncDriver`` so they remain
easily testable without touching the module-level singleton.

By default only read transactions are exposed.  Write access requires the
caller to pass ``allow_write=True`` AND the server setting
``ALLOW_WRITE_QUERIES=true`` to prevent accidental mutations.
"""

from collections.abc import Mapping
from typing import Any

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
) -> list[dict[str, Any]]:
    """Execute a write Cypher query.

    Raises ``PermissionError`` unless ``ALLOW_WRITE_QUERIES=true`` is set.
    """
    if not get_settings().allow_write_queries:
        raise PermissionError("Write queries are disabled. Set ALLOW_WRITE_QUERIES=true to enable.")
    db = database or get_settings().neo4j_database
    async with driver.session(database=db) as session:
        result = await session.run(query, dict(parameters or {}))
        records: list[dict[str, Any]] = await result.data()
    logger.debug("neo4j_write_query_executed", query=query, row_count=len(records))
    return records
