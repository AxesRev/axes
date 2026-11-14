"""GitHub static resource-type catalog → ResourceType nodes."""

from __future__ import annotations

import logging

from integrations.github.ingestion.shared import (
    ConnectionRef,
    ResourceTypeRow,
    merge_resource_types,
    resource_type_external_id,
)

logger = logging.getLogger(__name__)

GITHUB_RESOURCE_TYPE_REPOSITORY = "repository"
_GITHUB_RESOURCE_TYPE_NAMES: tuple[str, ...] = (GITHUB_RESOURCE_TYPE_REPOSITORY,)


def resource_type_rows_for_connection(connection: ConnectionRef) -> list[ResourceTypeRow]:
    """Return the static GitHub type catalog for one installation.

    Types are emitted even when the installation has no repositories.
    """
    return [
        ResourceTypeRow(
            external_id=resource_type_external_id(connection, type_name),
            name=type_name,
            connection_app=connection["app"],
            connection_external_id=connection["external_id"],
        )
        for type_name in _GITHUB_RESOURCE_TYPE_NAMES
    ]


async def ingest_resource_types(connection: ConnectionRef) -> dict[str, str]:
    rows = resource_type_rows_for_connection(connection)
    await merge_resource_types(rows)
    types_by_name = {row["name"]: row["external_id"] for row in rows}
    logger.info("merged_resource_types count=%s", len(rows))
    return types_by_name
