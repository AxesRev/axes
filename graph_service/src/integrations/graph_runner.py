"""Shared Neo4j setup for graph ingestion CLIs."""

from __future__ import annotations

import logging

from neomodel import adb

from integrations.github.settings import get_runner_settings

logger = logging.getLogger(__name__)

# Labels looked up or MERGEd by external_id. Without these indexes every lookup
# and every ingestion MERGE scans the whole label.
EXTERNAL_ID_INDEXED_LABELS: tuple[str, ...] = (
    "Tenant",
    "AppConnection",
    "ResourceType",
    "Resource",
    "Profile",
    "Group",
    "AppIdentity",
    "Identity",
)


async def wipe_graph() -> None:
    """Remove all nodes and relationships from the graph database."""
    await adb.cypher_query("MATCH (n) DETACH DELETE n")
    logger.info("graph_wiped")


async def install_external_id_indexes() -> None:
    """Create a range index on external_id for every looked-up label (idempotent)."""
    for label in EXTERNAL_ID_INDEXED_LABELS:
        index_name = f"{label.lower()}_external_id"
        await adb.cypher_query(f"CREATE INDEX {index_name} IF NOT EXISTS FOR (n:{label}) ON (n.external_id)")
    logger.info("external_id_indexes_installed labels=%s", len(EXTERNAL_ID_INDEXED_LABELS))


async def setup_graph(*, wipe: bool = True) -> None:
    """Connect to Neo4j and optionally wipe the graph before ingestion."""
    runner = get_runner_settings()
    await adb.set_connection(runner.neomodel_url)
    if wipe:
        await wipe_graph()
    await adb.install_all_labels()
    await install_external_id_indexes()


async def teardown_graph() -> None:
    """Close the Neo4j driver connection."""
    await adb.close_connection()
