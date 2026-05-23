"""CLI entry point for Salesforce → graph ingestion.

Run directly:
    uv run --package aegra-graph-service python -m integrations.salesforce.fetcher [ORG_ID] [INTEGRATION_USERNAME]

Optional flags:
    --skip-record-access   Skip Share-table record access ingest
"""

from __future__ import annotations

import asyncio
import logging
import sys

from neomodel import adb

import nodes as _nodes_pkg  # noqa: F401 — registers all node classes with neomodel
from integrations.github.settings import get_runner_settings
from integrations.salesforce.ingestion.fetch_org import fetch_org
from integrations.salesforce.settings import get_salesforce_settings

logger = logging.getLogger(__name__)


async def wipe_graph() -> None:
    """Remove all nodes and relationships from the graph database."""
    await adb.cypher_query("MATCH (n) DETACH DELETE n")
    logger.info("graph_wiped")


def _parse_args(argv: list[str]) -> tuple[str | None, str | None, bool]:
    skip_record_access = "--skip-record-access" in argv
    positional = [arg for arg in argv if arg != "--skip-record-access"]
    org_id = positional[0] if len(positional) > 0 else None
    integration_username = positional[1] if len(positional) > 1 else None
    return org_id, integration_username, skip_record_access


async def _run_once() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    settings = get_salesforce_settings()
    org_id, integration_username, skip_record_access = _parse_args(sys.argv[1:])
    org_id = org_id or settings.SALESFORCE_ORG_ID or None
    integration_username = integration_username or settings.SALESFORCE_USERNAME or None

    runner = get_runner_settings()
    await adb.set_connection(runner.neomodel_url)
    await wipe_graph()
    await adb.install_all_labels()

    try:
        await fetch_org(
            org_id=org_id,
            integration_username=integration_username,
            skip_record_access=skip_record_access,
        )
    finally:
        await adb.close_connection()


def main() -> None:
    asyncio.run(_run_once())


if __name__ == "__main__":
    main()
