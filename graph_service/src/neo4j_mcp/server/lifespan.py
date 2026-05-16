"""MCP server lifespan — Neo4j driver startup, schema snapshot for resources, teardown."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP
from neo4j import AsyncDriver

from db.client import close_driver, init_driver, verify_connectivity
from neo4j_mcp.schema_snapshot import fetch_schema_visualization_schematic, schematic_to_json
from neo4j_mcp.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Resources available to MCP tools/resources via ``lifespan_context``."""

    driver: AsyncDriver
    schema_json: str


@asynccontextmanager
async def neo4j_lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    """Open the Neo4j driver and cache the schema schematic JSON for ``neo4j://schema``."""
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

    try:
        yield AppContext(driver=driver, schema_json=schema_json)
    finally:
        logger.info("neo4j_mcp shutting down")
        await close_driver()
