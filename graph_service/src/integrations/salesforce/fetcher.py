"""CLI entry point for Salesforce → graph ingestion (all tenants from ``app_integrations``).

Run directly:

    uv run --package aegra-graph-service python -m integrations.salesforce.fetcher

Optional flag for this entrypoint only:

    --skip-record-access   Skip Share-table record access ingest

Or use the parent fetcher for all apps:

    uv run --package aegra-graph-service python -m integrations.fetcher
"""

from __future__ import annotations

import asyncio
import logging
import sys

import nodes as _nodes_pkg  # noqa: F401 — registers all node classes with neomodel
from integrations.app_names import SALESFORCE_APP_NAME
from integrations.graph_runner import setup_graph, teardown_graph
from integrations.salesforce.run import run_salesforce_ingestion
from integrations.salesforce.settings import get_salesforce_settings
from integrations.tenant_plans import (
    load_tenant_fetch_plans,
    salesforce_integration_username,
    salesforce_org_id,
)

logger = logging.getLogger(__name__)


def _parse_skip_record_access(argv: list[str]) -> bool:
    return "--skip-record-access" in argv


async def fetch_salesforce_for_all_tenants(*, skip_record_access: bool) -> None:
    """Ingest Salesforce data for every tenant with a ``salesforce`` app integration."""
    plans = await load_tenant_fetch_plans()
    if not plans:
        logger.error("no_tenants_in_database")
        raise SystemExit(1)

    default_username = get_salesforce_settings().SALESFORCE_USERNAME or None
    found_any = False

    for plan in plans:
        for integration in plan.integrations:
            if integration.app_name != SALESFORCE_APP_NAME:
                continue
            username = salesforce_integration_username(integration) or default_username
            if not username:
                logger.warning(
                    "salesforce_fetch_skipped_missing_username tenant_id=%s",
                    plan.tenant_id,
                )
                continue
            found_any = True
            org_id = salesforce_org_id(integration)
            logger.info(
                "salesforce_fetch_start tenant_id=%s org_id=%s username=%s",
                plan.tenant_id,
                org_id,
                username,
            )
            await run_salesforce_ingestion(
                org_id=org_id,
                integration_username=username,
                skip_record_access=skip_record_access,
            )

    if not found_any:
        logger.error("no_salesforce_app_integrations_found")
        raise SystemExit(1)


async def _run_once() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    skip_record_access = _parse_skip_record_access(sys.argv[1:])
    await setup_graph(wipe=True)
    try:
        await fetch_salesforce_for_all_tenants(skip_record_access=skip_record_access)
    finally:
        await teardown_graph()


def main() -> None:
    asyncio.run(_run_once())


if __name__ == "__main__":
    main()
