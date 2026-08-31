"""Shared Neo4j setup for graph ingestion CLIs."""

from __future__ import annotations

import asyncio
import logging

from neomodel import adb

from integrations.github.settings import get_runner_settings

logger = logging.getLogger(__name__)

_CONNECT_ATTEMPTS = 12
_CONNECT_DELAY_SECONDS = 10


async def wipe_graph() -> None:
    """Remove all nodes and relationships from the graph database."""
    await adb.cypher_query("MATCH (n) DETACH DELETE n")
    logger.info("graph_wiped")


async def setup_graph(*, wipe: bool = True) -> None:
    """Connect to Neo4j and optionally wipe the graph before ingestion."""
    runner = get_runner_settings()
    last_error: Exception | None = None
    for attempt in range(1, _CONNECT_ATTEMPTS + 1):
        try:
            await adb.set_connection(runner.neomodel_url)
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            logger.warning("neo4j_connect_retry attempt=%s error=%s", attempt, exc)
            if attempt < _CONNECT_ATTEMPTS:
                await asyncio.sleep(_CONNECT_DELAY_SECONDS)
    if last_error is not None:
        raise last_error
    if wipe:
        await wipe_graph()
    await adb.install_all_labels()


async def teardown_graph() -> None:
    """Close the Neo4j driver connection."""
    await adb.close_connection()
