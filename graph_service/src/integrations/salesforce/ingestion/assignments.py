"""Salesforce profile assignment ingestion → ASSIGNED_PROFILE edges."""

from __future__ import annotations

import logging
from typing import Any

from simple_salesforce import Salesforce

from integrations.salesforce.client import query_all
from integrations.salesforce.ingestion.shared import (
    SALESFORCE_APP,
    AssignedProfileRow,
    ConnectionRef,
    merge_assigned_profile,
)

logger = logging.getLogger(__name__)

_ASSIGNMENT_SOQL = "SELECT Id, AssigneeId, PermissionSetId FROM PermissionSetAssignment"
_USER_PROFILE_SOQL = "SELECT Id, ProfileId FROM User WHERE IsActive = true AND ProfileId != null"


def build_assignment_rows(
    assignments: list[dict[str, Any]],
    users: list[dict[str, Any]],
) -> list[AssignedProfileRow]:
    rows: list[AssignedProfileRow] = []
    for assignment in assignments:
        assignee_id = str(assignment["AssigneeId"])
        profile_id = str(assignment["PermissionSetId"])
        if assignee_id.startswith("005"):
            rows.append(
                AssignedProfileRow(
                    subject_kind="identity",
                    subject_external_id=assignee_id,
                    subject_app=SALESFORCE_APP,
                    profile_app=SALESFORCE_APP,
                    profile_external_id=profile_id,
                )
            )
        elif assignee_id.startswith("00G"):
            rows.append(
                AssignedProfileRow(
                    subject_kind="group",
                    subject_external_id=assignee_id,
                    subject_app=SALESFORCE_APP,
                    profile_app=SALESFORCE_APP,
                    profile_external_id=profile_id,
                )
            )
    for user in users:
        rows.append(
            AssignedProfileRow(
                subject_kind="identity",
                subject_external_id=str(user["Id"]),
                subject_app=SALESFORCE_APP,
                profile_app=SALESFORCE_APP,
                profile_external_id=str(user["ProfileId"]),
            )
        )
    return rows


async def ingest_assignments(
    sf: Salesforce,
    *,
    connection: ConnectionRef,  # noqa: ARG001
) -> None:
    assignments = query_all(sf, _ASSIGNMENT_SOQL)
    users = query_all(sf, _USER_PROFILE_SOQL)
    rows = build_assignment_rows(assignments, users)
    await merge_assigned_profile(rows)
    logger.info("merged_assigned_profile count=%s", len(rows))
