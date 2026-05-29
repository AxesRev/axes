from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceMalformedRequest

from integrations.salesforce.settings import SalesforceAppSettings, get_salesforce_settings

logger = logging.getLogger(__name__)

_MUTING_PERMISSION_SET_GROUP_SOQL = (
    "SELECT Id, PermissionSetGroupId, PermissionSetId FROM PermissionSetGroupMutingPermissionSet"
)
_MUTING_SOBJECT = "PermissionSetGroupMutingPermissionSet"

_queryable_sobjects_cache: dict[str, frozenset[str]] = {}


def make_salesforce_client(
    *,
    username: str,
    settings: SalesforceAppSettings | None = None,
) -> Salesforce:
    """Create a JWT-authenticated Salesforce REST client."""
    config = settings or get_salesforce_settings()
    return Salesforce(
        consumer_key=config.SALESFORCE_CLIENT_ID,
        privatekey=config.private_key,
        username=username,
        domain=config.jwt_domain,
    )


def query_all(sf: Salesforce, soql: str) -> list[dict[str, Any]]:
    """Run SOQL and return all records, following pagination."""
    result = sf.query(soql)
    records: list[dict[str, Any]] = list(result.get("records", []))
    while not result.get("done", True) and result.get("nextRecordsUrl"):
        result = sf.query_more(result["nextRecordsUrl"], identifier_is_url=True)
        records.extend(result.get("records", []))
    return records


def query_all_or_empty(sf: Salesforce, soql: str, *, context: str) -> list[dict[str, Any]]:
    """Run SOQL and return records, or an empty list when the query is unsupported."""
    try:
        return query_all(sf, soql)
    except SalesforceMalformedRequest as exc:
        logger.warning("optional_soql_skipped context=%s error=%s", context, exc)
        return []


def _queryable_sobject_names(sf: Salesforce) -> frozenset[str]:
    cache_key = str(getattr(sf, "sf_instance", "") or id(sf))
    cached = _queryable_sobjects_cache.get(cache_key)
    if cached is not None:
        return cached
    names = frozenset(
        str(summary["name"])
        for summary in describe_global(sf)
        if isinstance(summary.get("name"), str) and summary.get("queryable")
    )
    _queryable_sobjects_cache[cache_key] = names
    return names


def query_muting_permission_set_links(sf: Salesforce) -> list[dict[str, Any]]:
    """Return permission-set-group muting links when the org exposes that object."""
    if _MUTING_SOBJECT not in _queryable_sobject_names(sf):
        logger.debug("sobject_not_queryable name=%s", _MUTING_SOBJECT)
        return []
    return query_all(sf, _MUTING_PERMISSION_SET_GROUP_SOQL)


def query_batches(sf: Salesforce, soql: str, *, batch_size: int = 2000) -> Iterator[list[dict[str, Any]]]:
    """Yield SOQL result pages."""
    result = sf.query(soql)
    while True:
        records = list(result.get("records", []))
        for start in range(0, len(records), batch_size):
            yield records[start : start + batch_size]
        if result.get("done", True) or not result.get("nextRecordsUrl"):
            break
        result = sf.query_more(result["nextRecordsUrl"], identifier_is_url=True)


def describe_global(sf: Salesforce) -> list[dict[str, Any]]:
    """Return sobject describe summaries from the org."""
    payload = sf.describe()
    return list(payload.get("sobjects", []))
