"""CLI entry point for GitHub → graph ingestion (all tenants from ``app_integrations``).

Run directly:

    uv run --package aegra-graph-service python -m integrations.github.fetcher

Or use the parent fetcher for all apps:

    uv run --package aegra-graph-service python -m integrations.fetcher
"""

from __future__ import annotations

import asyncio
import logging

import nodes as _nodes_pkg  # noqa: F401 — registers all node classes with neomodel
from integrations.app_names import GITHUB_APP_NAME
from integrations.github.ingestion.installation import fetch_installation
from integrations.graph_runner import setup_graph, teardown_graph
from integrations.tenant_plans import github_installation_id, load_tenant_fetch_plans

logger = logging.getLogger(__name__)


async def fetch_github_for_all_tenants() -> None:
    """Ingest GitHub data for every tenant with a ``github`` app integration."""
    plans = await load_tenant_fetch_plans()
    if not plans:
        logger.error("no_tenants_in_database")
        raise SystemExit(1)

    found_any = False
    for plan in plans:
        for integration in plan.integrations:
            if integration.app_name != GITHUB_APP_NAME:
                continue
            installation_id = github_installation_id(integration)
            if installation_id is None:
                logger.warning(
                    "github_fetch_skipped_missing_installation_id tenant_id=%s",
                    plan.tenant_id,
                )
                continue
            found_any = True
            logger.info(
                "github_fetch_start tenant_id=%s installation_id=%s",
                plan.tenant_id,
                installation_id,
            )
            await fetch_installation(
                installation_id,
                tenant_id=plan.tenant_id,
                tenant_name=plan.tenant_name,
            )

    if not found_any:
        logger.error("no_github_app_integrations_found")
        raise SystemExit(1)


async def _run_once() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    await setup_graph(wipe=True)
    try:
        await fetch_github_for_all_tenants()
    finally:
        await teardown_graph()


if __name__ == "__main__":
    asyncio.run(_run_once())
