"""Unit tests for Salesforce integration metadata models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from integrations.salesforce.models import (
    SalesforcePermissionExtra,
    build_field_permission_extra,
    build_object_permission_extra,
)


@pytest.mark.unit
def test_object_permission_extra_allows_access_type_object_only() -> None:
    extra = SalesforcePermissionExtra(access_type="object")

    assert extra.access_type == "object"
    assert extra.fields is None
    assert build_object_permission_extra() == {"access_type": "object", "fields": None}


@pytest.mark.unit
def test_field_permission_extra_requires_non_empty_fields() -> None:
    extra = SalesforcePermissionExtra(access_type="field", fields=["AnnualRevenue"])

    assert extra.fields == ["AnnualRevenue"]
    assert build_field_permission_extra("AnnualRevenue", "Name") == {
        "access_type": "field",
        "fields": ["AnnualRevenue", "Name"],
    }


@pytest.mark.unit
def test_field_permission_extra_rejects_empty_fields() -> None:
    with pytest.raises(ValidationError, match="fields is required"):
        SalesforcePermissionExtra(access_type="field", fields=[])


@pytest.mark.unit
def test_object_permission_extra_rejects_fields() -> None:
    with pytest.raises(ValidationError, match="fields must be omitted"):
        SalesforcePermissionExtra(access_type="object", fields=["AnnualRevenue"])


@pytest.mark.unit
def test_salesforce_group_extra_accepts_public_group_kind() -> None:
    from integrations.salesforce.models import SalesforceGroupExtra  # noqa: PLC0415

    extra = SalesforceGroupExtra(kind="public_group")

    assert extra.kind == "public_group"


@pytest.mark.unit
def test_salesforce_profile_extra_accepts_permission_set_group_kind() -> None:
    from integrations.salesforce.models import SalesforceProfileExtra  # noqa: PLC0415

    extra = SalesforceProfileExtra(kind="permission_set_group")

    assert extra.kind == "permission_set_group"
