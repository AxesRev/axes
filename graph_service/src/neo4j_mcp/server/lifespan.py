"""MCP server lifespan — Neo4j driver startup and teardown."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP
from neo4j import AsyncDriver
from neomodel import adb, install_all_labels

import common_nodes as _common_nodes  # noqa: F401 — registers all node classes with neomodel
from db.client import close_driver, init_driver, verify_connectivity
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

    neomodel_url = (
        f"bolt://{settings.neo4j_user}:{settings.neo4j_password}@{settings.neo4j_uri.removeprefix('bolt://')}"
    )
    await adb.set_connection(neomodel_url)
    await install_all_labels()
    logger.info("neomodel connected and labels installed")

    try:
        yield AppContext(driver=driver)
    finally:
        logger.info("neo4j_mcp shutting down")
        await adb.close_connection()
        await close_driver()
