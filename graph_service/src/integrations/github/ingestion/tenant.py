"""Tenant node ingestion."""

from __future__ import annotations

import logging

from nodes.tenant import Tenant

logger = logging.getLogger(__name__)


async def get_or_create_tenant(*, external_id: str, name: str) -> Tenant:
    tenant = await Tenant.nodes.get_or_none(external_id=external_id)
    if tenant is None:
        tenant = await Tenant(external_id=external_id, name=name).save()
        logger.info("created_tenant external_id=%s name=%s", external_id, name)
        return tenant

    if tenant.name != name:
        tenant.name = name
        await tenant.save()
    return tenant
