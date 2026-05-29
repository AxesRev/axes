"""Seed example owned Accounts in Salesforce and ingest ownership into Neo4j."""

from __future__ import annotations

import asyncio
import logging
import sys

from neomodel import adb

import nodes as _nodes_pkg  # noqa: F401
from integrations.github.settings import get_runner_settings
from integrations.salesforce.client import make_salesforce_client
from integrations.salesforce.ingestion.org_connection import upsert_connection
from integrations.salesforce.ingestion.ownership import ingest_owned_records, seed_example_owned_accounts
from integrations.salesforce.ingestion.tenant import upsert_tenant
from integrations.salesforce.ingestion.users import ensure_identities_for_ids, ingest_users
from integrations.salesforce.settings import get_salesforce_settings

logger = logging.getLogger(__name__)


async def _run(*, seed: bool, ingest: bool) -> None:
    settings = get_salesforce_settings()
    username = settings.SALESFORCE_USERNAME
    if not username:
        msg = "SALESFORCE_USERNAME is required"
        raise ValueError(msg)

    sf = make_salesforce_client(username=username, settings=settings)
    org = sf.query("SELECT Id, Name FROM Organization LIMIT 1")["records"][0]
    tenant_external_id = settings.SALESFORCE_ORG_ID or str(org["Id"])

    if seed:
        created = seed_example_owned_accounts(sf)
        logger.info("seed_complete created_accounts=%s", len(created))

    if not ingest:
        return

    runner = get_runner_settings()
    await adb.set_connection(runner.neomodel_url)
    try:
        await adb.install_all_labels()
        await upsert_tenant(external_id=tenant_external_id, name=str(org.get("Name") or tenant_external_id))
        connection = await upsert_connection(sf, tenant_external_id=tenant_external_id)
        identity_external_ids = await ingest_users(sf, connection=connection)
        owner_ids = {
            str(record["OwnerId"])
            for record in sf.query("SELECT OwnerId FROM Account WHERE Name LIKE 'Axes Example Resource%'")["records"]
            if record.get("OwnerId")
        }
        await ensure_identities_for_ids(
            sf,
            connection=connection,
            user_ids=owner_ids,
            known_identity_ids=set(identity_external_ids.values()),
        )
        count = await ingest_owned_records(sf, connection=connection)
        logger.info("ingest_complete owner_edges=%s", count)
    finally:
        await adb.close_connection()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    seed = "--no-seed" not in sys.argv
    ingest = "--no-ingest" not in sys.argv
    asyncio.run(_run(seed=seed, ingest=ingest))


if __name__ == "__main__":
    main()
