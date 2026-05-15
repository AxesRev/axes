"""MCP server lifespan — Neo4j driver startup and teardown."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP
from neo4j import AsyncDriver

from neo4j_mcp.db.client import close_driver, init_driver, verify_connectivity
from neo4j_mcp.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Resources available to MCP tools via ``ctx.request_context.lifespan_context``."""

    driver: AsyncDriver


@asynccontextmanager
async def neo4j_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Open the Neo4j driver on startup, close it on shutdown.

    Any ``ConnectionError`` raised by ``verify_connectivity`` will propagate
    and prevent the server from starting — fail-fast is intentional here.
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

    try:
        yield AppContext(driver=driver)
    finally:
        logger.info("neo4j_mcp shutting down")
        await close_driver()
