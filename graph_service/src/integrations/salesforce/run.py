"""Run Salesforce org ingestion (no graph wipe)."""

from __future__ import annotations

import logging

from integrations.salesforce.ingestion.fetch_org import fetch_org

logger = logging.getLogger(__name__)


async def run_salesforce_ingestion(
    *,
    tenant_id: str,
    tenant_name: str,
    org_id: str,
    integration_username: str,
    skip_record_access: bool = False,
) -> None:
    """Fetch and ingest a Salesforce org into the graph."""
    logger.info(
        "salesforce_fetch_start tenant_id=%s org_id=%s username=%s skip_record_access=%s",
        tenant_id,
        org_id,
        integration_username,
        skip_record_access,
    )
    await fetch_org(
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        org_id=org_id,
        integration_username=integration_username,
        skip_record_access=skip_record_access,
    )
    logger.info("salesforce_fetch_complete tenant_id=%s", tenant_id)
