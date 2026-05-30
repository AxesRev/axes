"""Run Salesforce org ingestion (no graph wipe)."""

from __future__ import annotations

import logging

from integrations.salesforce.ingestion.fetch_org import fetch_org
from integrations.salesforce.settings import get_salesforce_settings

logger = logging.getLogger(__name__)


async def run_salesforce_ingestion(
    *,
    org_id: str | None = None,
    integration_username: str | None = None,
    skip_record_access: bool = False,
) -> None:
    """Fetch and ingest a Salesforce org into the graph."""
    settings = get_salesforce_settings()
    resolved_org_id = org_id or settings.SALESFORCE_ORG_ID or None
    resolved_username = integration_username or settings.SALESFORCE_USERNAME or None

    if not resolved_username:
        msg = "Salesforce integration username is required (set SALESFORCE_USERNAME in .env)"
        raise ValueError(msg)

    logger.info(
        "salesforce_fetch_start org_id=%s username=%s skip_record_access=%s",
        resolved_org_id,
        resolved_username,
        skip_record_access,
    )
    await fetch_org(
        org_id=resolved_org_id,
        integration_username=resolved_username,
        skip_record_access=skip_record_access,
    )
    logger.info("salesforce_fetch_complete org_id=%s", resolved_org_id)
