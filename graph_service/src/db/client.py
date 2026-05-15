"""Async Neo4j driver lifecycle helpers.

The driver is created once per server startup (via the MCP lifespan) and
stored as a module-level singleton so that query helpers can access it
without needing to thread the driver object through every call.
"""

import logging

from neo4j import AsyncDriver, AsyncGraphDatabase

logger = logging.getLogger(__name__)

_driver: AsyncDriver | None = None


async def init_driver(*, uri: str, user: str, password: str) -> AsyncDriver:
    """Create and store the module-level driver.

    Must be called exactly once during server startup.
    """
    global _driver
    _driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    logger.info("neo4j driver initialised", extra={"uri": uri})
    return _driver


async def close_driver() -> None:
    """Close and discard the module-level driver.

    Safe to call even if the driver was never initialised.
    """
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None
        logger.info("neo4j driver closed")


async def verify_connectivity() -> None:
    """Raise if the server cannot be reached.

    Intended as a startup health-check inside the MCP lifespan.
    """
    driver = get_driver()
    await driver.verify_connectivity()
    logger.info("neo4j connectivity verified")


def get_driver() -> AsyncDriver:
    """Return the active driver or raise if not yet initialised."""
    if _driver is None:
        raise RuntimeError("Neo4j driver is not initialised. Call init_driver() during server startup.")
    return _driver
