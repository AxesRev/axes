"""Parent CLI: rebuild every tenant's ArcadeDB graph database.

Run from repo root:

    uv run --package aegra-graph-service python -m integrations.fetcher
    uv run fetch-graph

For each row in ``tenants``, reads ``app_integrations`` and runs the matching
ingestion (GitHub installation, Salesforce org, etc.).
"""

from __future__ import annotations

import asyncio
import logging

from integrations.graph_db import setup_graph, teardown_graph
from integrations.tenant_runner import fetch_all_tenants

logger = logging.getLogger(__name__)


async def run_all_fetchers() -> None:
    """Reset each tenant's database, then ingest its configured app integrations."""
    await setup_graph()

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
