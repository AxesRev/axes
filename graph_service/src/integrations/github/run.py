"""Run GitHub App installation ingestion (no graph wipe)."""

from __future__ import annotations

import logging

from integrations.app_names import GITHUB_APP_NAME
from integrations.github.ingestion.installation import fetch_installation
from integrations.tenant_plans import github_installation_id, load_tenant_fetch_plans

logger = logging.getLogger(__name__)


async def run_github_ingestion_for_all_tenants() -> None:
    """Ingest GitHub for each tenant that has a ``github`` app integration."""
    plans = await load_tenant_fetch_plans()
    for plan in plans:
        for integration in plan.integrations:
            if integration.app_name != GITHUB_APP_NAME:
                continue
            installation_id = github_installation_id(integration)
            if installation_id is None:
                continue
            await fetch_installation(
                installation_id,
                tenant_id=plan.tenant_id,
                tenant_name=plan.tenant_name,
            )
