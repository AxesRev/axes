"""Shared Neo4j setup for graph ingestion CLIs."""

from __future__ import annotations

import logging

from neomodel import adb

from integrations.github.settings import get_runner_settings

logger = logging.getLogger(__name__)


async def wipe_graph() -> None:
    """Remove all nodes and relationships from the graph database."""
    await adb.cypher_query("MATCH (n) DETACH DELETE n")
    logger.info("graph_wiped")


async def setup_graph(*, wipe: bool = True) -> None:
    """Connect to Neo4j and optionally wipe the graph before ingestion."""
    runner = get_runner_settings()
    await adb.set_connection(runner.neomodel_url)
    if wipe:
        await wipe_graph()
    await adb.install_all_labels()


async def teardown_graph() -> None:
    """Close the Neo4j driver connection."""
    await adb.close_connection()
