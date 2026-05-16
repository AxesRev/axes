"""MCP server lifespan — Neo4j driver startup, schema snapshot, teardown."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP
from neo4j import AsyncDriver

from db.client import close_driver, init_driver, verify_connectivity
from neo4j_mcp.schema_snapshot import (
    build_run_cypher_tool_description,
    fetch_schema_visualization_schematic,
    schematic_to_json,
)
from neo4j_mcp.settings import get_settings

logger = logging.getLogger(__name__)

_TOOL_NAME = "run_cypher"


@dataclass
class AppContext:
    """Resources available to MCP tools via ``ctx.request_context.lifespan_context``."""

    driver: AsyncDriver


@asynccontextmanager
async def neo4j_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Open the Neo4j driver, load schema visualization, attach schematic to ``run_cypher``.

    Mutates the registered FastMCP tool description after introspection so clients listing tools see an accurate schematic without maintaining strings by hand.

    Raises:
        RuntimeError: If the ``run_cypher`` tool was not registered (programming error).
        neo4j.exceptions.ClientError: If Neo4j rejects ``CALL db.schema.visualization()`` or related calls.
        ValueError: If visualization returns no rows.
    """
    settings = get_settings()
    logger.info(
        "neo4j_mcp starting",
        extra={"uri": settings.neo4j_uri, "server": settings.mcp_server_name},
    )

    driver = await init_driver(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )
    await verify_connectivity()

    schematic = await fetch_schema_visualization_schematic(
        driver=driver,
        database=settings.neo4j_database,
    )
    schema_json = schematic_to_json(schematic)

    tool = server._tool_manager.get_tool(_TOOL_NAME)
    if tool is None:
        logger.error("run_cypher_tool_missing")
        raise RuntimeError(f"Internal error: MCP tool {_TOOL_NAME!r} is not registered.")
    tool.description = build_run_cypher_tool_description(
        schema_json=schema_json,
        read_only=not settings.allow_write_queries,
    )

    try:
        yield AppContext(driver=driver)
    finally:
        logger.info("neo4j_mcp shutting down")
        await close_driver()
