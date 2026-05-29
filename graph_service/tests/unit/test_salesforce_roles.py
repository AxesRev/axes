"""Unit tests for Salesforce role hierarchy mappers."""

from __future__ import annotations

import pytest

from integrations.salesforce.ingestion.roles import build_manager_of_rows_from_role_tree


@pytest.mark.unit
def test_build_manager_of_rows_from_role_tree_links_ancestor_to_descendant_users() -> None:
    roles = [
        {"Id": "ROLE_CEO", "ParentRoleId": None},
        {"Id": "ROLE_REP", "ParentRoleId": "ROLE_CEO"},
    ]
    users = [
        {"Id": "USER_CEO", "UserRoleId": "ROLE_CEO"},
        {"Id": "USER_REP", "UserRoleId": "ROLE_REP"},
    ]

    rows = build_manager_of_rows_from_role_tree(users, roles)

    assert rows == [
        {
            "manager_app": "salesforce",
            "manager_external_id": "USER_CEO",
            "report_app": "salesforce",
            "report_external_id": "USER_REP",
        }
    ]


@pytest.mark.unit
def test_build_manager_of_rows_from_role_tree_skips_self_edges() -> None:
    roles = [{"Id": "ROLE_ONLY", "ParentRoleId": None}]
    users = [{"Id": "USER_ONLY", "UserRoleId": "ROLE_ONLY"}]

    rows = build_manager_of_rows_from_role_tree(users, roles)

    assert rows == []
