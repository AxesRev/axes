"""CLI entry point for GitHub → graph ingestion.

Run directly:
    uv run --package aegra-graph-service python -m integrations.github.fetcher INSTALLATION_ID [INSTALLATION_ID ...]

Installation IDs must be passed as CLI arguments.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from neomodel import adb

import nodes as _nodes_pkg  # noqa: F401 — registers all node classes with neomodel
from integrations.github.ingestion.installation import fetch_installation
from integrations.github.settings import get_runner_settings

logger = logging.getLogger(__name__)


async def wipe_graph() -> None:
    """Remove all nodes and relationships from the graph database."""
    await adb.cypher_query("MATCH (n) DETACH DELETE n")
    logger.info("graph_wiped")


async def _run_once() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    if len(sys.argv) <= 1:
        logger.error("installation_id_required_pass_as_cli_argument")
        sys.exit(1)

    installation_ids = [int(arg) for arg in sys.argv[1:]]
    logger.info("installation_ids_from_cli=%s", installation_ids)

    runner = get_runner_settings()
    await adb.set_connection(runner.neomodel_url)
    await wipe_graph()
    await adb.install_all_labels()

    try:
        for installation_id in installation_ids:
            logger.info("fetch_start installation_id=%s", installation_id)
            await fetch_installation(installation_id)
    finally:
        await adb.close_connection()


if __name__ == "__main__":
    asyncio.run(_run_once())
