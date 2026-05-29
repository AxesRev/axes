"""Salesforce role hierarchy ingestion → MANAGER_OF edges."""

from __future__ import annotations

import logging
from typing import Any

from simple_salesforce import Salesforce

from integrations.salesforce.client import query_all
from integrations.salesforce.ingestion.shared import (
    SALESFORCE_APP,
    ConnectionRef,
    ManagerOfRow,
    merge_manager_of,
)

logger = logging.getLogger(__name__)

_ROLE_SOQL = "SELECT Id, Name, ParentRoleId FROM UserRole"
_USER_SOQL = "SELECT Id, UserRoleId FROM User WHERE IsActive = true AND UserRoleId != null"


def _ancestor_role_ids(role_id: str, parent_by_role: dict[str, str | None]) -> set[str]:
    ancestors: set[str] = set()
    current: str | None = parent_by_role.get(role_id)
    while current:
        ancestors.add(current)
        current = parent_by_role.get(current)
    return ancestors


def build_manager_of_rows_from_role_tree(
    users: list[dict[str, Any]],
    roles: list[dict[str, Any]],
) -> list[ManagerOfRow]:
    """Build MANAGER_OF edges: users in strict ancestor roles manage users in descendant roles."""
    parent_by_role: dict[str, str | None] = {
        str(role["Id"]): str(role["ParentRoleId"]) if role.get("ParentRoleId") else None for role in roles
    }
    users_by_role: dict[str, list[str]] = {}
    for user in users:
        role_id = user.get("UserRoleId")
        if not role_id:
            continue
        users_by_role.setdefault(str(role_id), []).append(str(user["Id"]))

    descendant_roles_by_ancestor: dict[str, set[str]] = {}
    for role_id in users_by_role:
        for ancestor_id in _ancestor_role_ids(role_id, parent_by_role):
            descendant_roles_by_ancestor.setdefault(ancestor_id, set()).add(role_id)
        descendant_roles_by_ancestor.setdefault(role_id, set()).add(role_id)

    rows: list[ManagerOfRow] = []
    for ancestor_role_id, descendant_role_ids in descendant_roles_by_ancestor.items():
        manager_ids = users_by_role.get(ancestor_role_id, [])
        if not manager_ids:
            continue
        report_ids: list[str] = []
        for descendant_role_id in descendant_role_ids:
            if descendant_role_id == ancestor_role_id:
                continue
            report_ids.extend(users_by_role.get(descendant_role_id, []))
        for manager_id in manager_ids:
            for report_id in report_ids:
                if manager_id == report_id:
                    continue
                rows.append(
                    ManagerOfRow(
                        manager_app=SALESFORCE_APP,
                        manager_external_id=manager_id,
                        report_app=SALESFORCE_APP,
                        report_external_id=report_id,
                    )
                )
    deduped: dict[tuple[str, str, str, str], ManagerOfRow] = {}
    for row in rows:
        key = (
            row["manager_app"],
            row["manager_external_id"],
            row["report_app"],
            row["report_external_id"],
        )
        deduped[key] = row
    return list(deduped.values())


async def ingest_roles(
    sf: Salesforce,
    *,
    connection: ConnectionRef,  # noqa: ARG001
) -> None:
    users = query_all(sf, _USER_SOQL)
    roles = query_all(sf, _ROLE_SOQL)
    rows = build_manager_of_rows_from_role_tree(users, roles)
    await merge_manager_of(rows)
    logger.info("merged_manager_of count=%s", len(rows))
