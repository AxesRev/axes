"""Link AppIdentity nodes to canonical Identity nodes by email."""

from __future__ import annotations

import logging
import re
from typing import Literal, TypedDict

from neomodel import adb

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CORRELATION_BATCH_SIZE = 500

IdentityKind = Literal["human", "service_account", "bot", "api_key"]


class AppIdentityCorrelationRow(TypedDict):
    identity_external_id: str
    name: str
    kind: IdentityKind
    app: str
    app_identity_external_id: str


def normalize_email(email: str) -> str | None:
    normalized = email.strip().lower()
    if not normalized or not _EMAIL_RE.fullmatch(normalized):
        return None
    return normalized


def correlation_row_from_email(
    *,
    app: str,
    app_identity_external_id: str,
    email: str | None,
    display_name: str,
    kind: IdentityKind = "human",
) -> AppIdentityCorrelationRow | None:
    normalized = normalize_email(email) if email else None
    if normalized is None:
        return None
    return AppIdentityCorrelationRow(
        identity_external_id=normalized,
        name=display_name,
        kind=kind,
        app=app,
        app_identity_external_id=app_identity_external_id,
    )


async def correlate_app_identities_by_email(rows: list[AppIdentityCorrelationRow]) -> int:
    """Merge Identity nodes and HAS_PROFILE edges for AppIdentity rows with valid email."""
    if not rows:
        return 0

    query = """
    UNWIND $rows AS row
    MERGE (i:Identity {external_id: row.identity_external_id})
    ON CREATE SET i.name = row.name, i.kind = row.kind
    WITH i, row
    MATCH (app_i:AppIdentity {app: row.app, external_id: row.app_identity_external_id})
    MERGE (i)-[:HAS_PROFILE]->(app_i)
    """
    for start in range(0, len(rows), CORRELATION_BATCH_SIZE):
        batch = rows[start : start + CORRELATION_BATCH_SIZE]
        await adb.cypher_query(query, {"rows": batch})

    logger.info("correlated_app_identities count=%s", len(rows))
    return len(rows)
