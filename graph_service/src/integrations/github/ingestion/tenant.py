"""Tenant node ingestion."""

from __future__ import annotations

import logging

from nodes.tenant import Tenant

logger = logging.getLogger(__name__)


async def get_or_create_tenant(name: str) -> Tenant:
    results = await Tenant.nodes.filter(name=name).all()
    if results:
        return results[0]
    tenant = await Tenant(name=name).save()
    logger.info("created_tenant name=%s", name)
    return tenant
