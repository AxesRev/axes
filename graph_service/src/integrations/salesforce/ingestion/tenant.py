"""Tenant node ingestion."""

from __future__ import annotations

import logging

from integrations.salesforce.ingestion.shared import TenantRow, merge_tenants

logger = logging.getLogger(__name__)


async def upsert_tenant(*, external_id: str, name: str) -> None:
    row = TenantRow(external_id=external_id, name=name)
    await merge_tenants([row])
    logger.info("merged_tenant external_id=%s name=%s", external_id, name)
