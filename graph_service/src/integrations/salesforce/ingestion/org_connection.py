"""Salesforce org workspace ingestion (AppConnection + OWD)."""

from __future__ import annotations

import logging
from typing import Any

from simple_salesforce import Salesforce

from integrations.salesforce.client import describe_global, query_all
from integrations.salesforce.ingestion.shared import (
    SALESFORCE_APP,
    AppConnectionRow,
    ConnectionRef,
    ConnectionTenantRow,
    merge_app_connections,
    merge_connections_belong_to_tenants,
)
from integrations.salesforce.models import SalesforceConnectionExtra

logger = logging.getLogger(__name__)

_ORG_SOQL = "SELECT Id, Name, InstanceName FROM Organization LIMIT 1"


def fetch_organization(sf: Salesforce) -> dict[str, Any]:
    records = query_all(sf, _ORG_SOQL)
    if not records:
        msg = "Organization query returned no rows"
        raise RuntimeError(msg)
    return records[0]


def fetch_org_wide_defaults(sf: Salesforce) -> dict[str, str]:
    """Collect default sharing models from sobject describe metadata."""
    owd: dict[str, str] = {}
    for summary in describe_global(sf):
        name = summary.get("name")
        if not isinstance(name, str):
            continue
        if summary.get("customSetting") or not summary.get("queryable"):
            continue
        sharing_model = summary.get("sharingModel")
        if isinstance(sharing_model, str) and sharing_model:
            owd[name] = sharing_model
    return owd


async def upsert_connection(
    sf: Salesforce,
    *,
    tenant_external_id: str,
) -> ConnectionRef:
    org = fetch_organization(sf)
    org_id = str(org["Id"])
    org_name = str(org.get("Name") or org_id)
    instance_url = str(getattr(sf, "sf_instance", "") or "")
    if instance_url and not instance_url.startswith("http"):
        instance_url = f"https://{instance_url}"

    extra = SalesforceConnectionExtra(
        org_id=org_id,
        instance_url=instance_url,
        owd=fetch_org_wide_defaults(sf),
    )
    connection_row = AppConnectionRow(
        app=SALESFORCE_APP,
        external_id=org_id,
        name=org_name,
        extra=extra.model_dump(),
    )
    await merge_app_connections([connection_row])
    await merge_connections_belong_to_tenants(
        [
            ConnectionTenantRow(
                app=SALESFORCE_APP,
                connection_external_id=org_id,
                tenant_external_id=tenant_external_id,
            )
        ]
    )
    logger.info("merged_app_connection org_id=%s name=%s", org_id, org_name)
    return ConnectionRef(app=SALESFORCE_APP, external_id=org_id)
