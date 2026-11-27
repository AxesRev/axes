from __future__ import annotations

from typing import Literal

from common.permissions import PERMISSION_ALL
from pydantic import BaseModel, Field, model_validator


class SalesforceConnectionExtra(BaseModel):
    """Shape stored on AppConnection.extra for a Salesforce org."""

    org_id: str
    instance_url: str
    owd: dict[str, str]


class SalesforcePermissionExtra(BaseModel):
    """Shape stored on HAS_PERMISSION.extra for Salesforce profile permissions.

    Object and field access to the same SObject are modeled as separate
    HAS_PERMISSION edges from a Profile to one Scope.
    Field-scoped edges list the affected field API names in ``fields``.
    """

    access_type: Literal["object", "field", "system"]
    fields: list[str] | None = None
    api_name: str | None = None
    """Salesforce permission field for ``system`` access (e.g. PermissionsApiEnabled)."""

    @model_validator(mode="after")
    def validate_fields_for_access_type(self) -> SalesforcePermissionExtra:
        if self.access_type == "field":
            if not self.fields:
                msg = "fields is required and must be non-empty when access_type is 'field'"
                raise ValueError(msg)
            return self

        if self.fields:
            msg = f"fields must be omitted when access_type is '{self.access_type}'"
            raise ValueError(msg)
        return self


class SalesforceRecordPermissionExtra(BaseModel):
    """Shape stored on HAS_PERMISSION.extra for record-level Share access."""

    access_type: Literal["record"] = "record"
    record_id: str
    row_cause: str
    access_level: str


def build_object_permission_extra() -> dict[str, object]:
    """Return serialized extra payload for object-level Salesforce access."""
    return SalesforcePermissionExtra(access_type="object").model_dump()


def build_field_permission_extra(*fields: str) -> dict[str, object]:
    """Return serialized extra payload for field-level Salesforce access."""
    return SalesforcePermissionExtra(
        access_type="field",
        fields=list(fields),
    ).model_dump()


def build_system_permission_extra(api_name: str) -> dict[str, object]:
    """Return serialized extra payload for an org-wide system permission (API Enabled, …)."""
    return SalesforcePermissionExtra(access_type="system", api_name=api_name).model_dump()


def build_owner_permission_extra(*, record_id: str) -> dict[str, object]:
    """Return serialized extra for record ownership."""
    return SalesforceRecordPermissionExtra(
        record_id=record_id,
        row_cause="Owner",
        access_level=PERMISSION_ALL,
    ).model_dump()


def build_record_permission_extra(
    *,
    record_id: str,
    row_cause: str,
    access_level: str,
) -> dict[str, object]:
    """Return serialized extra payload for record-level Share access."""
    return SalesforceRecordPermissionExtra(
        record_id=record_id,
        row_cause=row_cause,
        access_level=access_level,
    ).model_dump()


class SalesforceGroupExtra(BaseModel):
    """Optional shape stored on Group.extra for Salesforce-backed groups."""

    kind: Literal["public_group", "role_group"]


class SalesforceUserPermissionFlag(BaseModel):
    label: str
    enabled: bool


class SalesforceAppIdentityExtra(BaseModel):
    """Optional shape stored on AppIdentity.extra for Salesforce users."""

    role_id: str | None = None
    role_name: str | None = None
    user_permissions: dict[str, SalesforceUserPermissionFlag] = Field(default_factory=dict)


class SalesforceProfileExtra(BaseModel):
    """Optional shape stored on Profile.extra for Salesforce-backed profiles."""

    kind: Literal["profile", "permission_set", "permission_set_group", "muting_permission_set"]
