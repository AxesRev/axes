"""Orchestrate Salesforce org ingestion into the graph."""

from __future__ import annotations

import logging

from simple_salesforce import Salesforce

from integrations.salesforce.client import make_salesforce_client
from integrations.salesforce.ingestion.assignments import ingest_assignments
from integrations.salesforce.ingestion.groups import ingest_groups
from integrations.salesforce.ingestion.org_connection import upsert_connection
from integrations.salesforce.ingestion.permissions import ingest_permissions
from integrations.salesforce.ingestion.profiles import ingest_profiles
from integrations.salesforce.ingestion.record_access import ingest_record_access
from integrations.salesforce.ingestion.resources import ingest_resources
from integrations.salesforce.ingestion.roles import ingest_roles
from integrations.salesforce.ingestion.tenant import upsert_tenant
from integrations.salesforce.ingestion.users import ingest_users
from integrations.salesforce.settings import get_salesforce_settings

logger = logging.getLogger(__name__)


async def fetch_org(
    *,
    tenant_id: str,
    tenant_name: str,
    org_id: str | None = None,
    integration_username: str | None = None,
    skip_record_access: bool = False,
) -> None:
    """Fetch one Salesforce org and write all graph data."""
    settings = get_salesforce_settings()
    username = integration_username or settings.SALESFORCE_USERNAME
    if not username:
        msg = "integration username is required (SALESFORCE_USERNAME or CLI argument)"
        raise ValueError(msg)

    sf: Salesforce = make_salesforce_client(username=username, settings=settings)
    org = sf.query("SELECT Id, Name FROM Organization LIMIT 1")["records"][0]
    salesforce_org_id = str(org["Id"])
    if org_id is not None and org_id != salesforce_org_id:
        logger.warning(
            "salesforce_org_id_mismatch config=%s api=%s tenant_id=%s",
            org_id,
            salesforce_org_id,
            tenant_id,
        )

    await upsert_tenant(external_id=tenant_id, name=tenant_name)
    connection = await upsert_connection(sf, tenant_external_id=tenant_id)

    logger.info("ingest_users tenant_id=%s salesforce_org_id=%s", tenant_id, salesforce_org_id)
    identity_external_ids = await ingest_users(sf, connection=connection)

    logger.info("ingest_groups tenant_id=%s", tenant_id)
    groups_by_name = await ingest_groups(
        sf,
        connection=connection,
        identity_external_ids=identity_external_ids,
    )

    logger.info("ingest_roles tenant_id=%s", tenant_id)
    await ingest_roles(sf, connection=connection)

    logger.info("ingest_profiles tenant_id=%s", tenant_id)
    await ingest_profiles(sf, connection=connection)

    logger.info("ingest_assignments tenant_id=%s", tenant_id)
    await ingest_assignments(sf, connection=connection)

    logger.info("ingest_resources tenant_id=%s", tenant_id)
    resources_by_name = await ingest_resources(sf, connection=connection)

    logger.info("ingest_permissions tenant_id=%s", tenant_id)
    await ingest_permissions(sf, connection=connection, resources_by_name=resources_by_name)

    if not skip_record_access:
        logger.info("ingest_record_access tenant_id=%s", tenant_id)
        await ingest_record_access(
            sf,
            connection=connection,
            resources_by_name=resources_by_name,
            known_identity_ids=set(identity_external_ids.values()),
            known_group_ids=set(groups_by_name.values()),
        )

    logger.info("fetch_complete tenant_id=%s salesforce_org_id=%s username=%s", tenant_id, salesforce_org_id, username)
