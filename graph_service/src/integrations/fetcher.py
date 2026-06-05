"""Parent CLI: wipe Neo4j once and fetch graph data for every tenant.

Run from repo root:

    uv run --package aegra-graph-service python -m integrations.fetcher
    uv run fetch-graph

For each row in ``tenants``, reads ``app_integrations`` and runs the matching
ingestion (GitHub installation, Salesforce org, etc.).
"""

from __future__ import annotations

import asyncio
import logging

import nodes as _nodes_pkg  # noqa: F401 — registers all node classes with neomodel
from integrations.graph_runner import setup_graph, teardown_graph
from integrations.tenant_runner import fetch_all_tenants

logger = logging.getLogger(__name__)


async def run_all_fetchers() -> None:
    """Wipe the graph, then ingest each tenant's configured app integrations."""
    await setup_graph(wipe=True)

    try:
        await fetch_all_tenants()
    finally:
        await teardown_graph()


async def _main_async() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    logger.info("fetch_graph_start")
    await run_all_fetchers()
    logger.info("fetch_graph_complete")


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
