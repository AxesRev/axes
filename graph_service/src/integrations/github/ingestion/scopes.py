"""GitHub static scope catalog → Scope nodes."""

from __future__ import annotations

import logging

from common.graph_schema import SCOPE_KIND_OBJECT

from integrations.github.ingestion.shared import (
    ConnectionRef,
    ScopeRow,
    merge_scopes,
    scope_external_id,
)

logger = logging.getLogger(__name__)

GITHUB_SCOPE_REPOSITORY = "repository"
_GITHUB_SCOPE_NAMES: tuple[str, ...] = (GITHUB_SCOPE_REPOSITORY,)


def scope_rows_for_connection(connection: ConnectionRef) -> list[ScopeRow]:
    """Return the static GitHub type catalog for one installation.

    Types are emitted even when the installation has no repositories.
    """
    return [
        ScopeRow(
            external_id=scope_external_id(connection, type_name),
            name=type_name,
            kind=SCOPE_KIND_OBJECT,
            connection_app=connection["app"],
            connection_external_id=connection["external_id"],
        )
        for type_name in _GITHUB_SCOPE_NAMES
    ]


async def ingest_scopes(connection: ConnectionRef) -> dict[str, str]:
    rows = scope_rows_for_connection(connection)
    await merge_scopes(rows)
    types_by_name = {row["name"]: row["external_id"] for row in rows}
    logger.info("merged_scopes count=%s", len(rows))
    return types_by_name
