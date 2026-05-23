from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator

PERMISSION_READ = "read"
PERMISSION_CREATE = "create"
PERMISSION_EDIT = "edit"
PERMISSION_DELETE = "delete"
PERMISSION_VIEW_ALL = "view_all"
PERMISSION_MODIFY_ALL = "modify_all"

PERMISSION_EFFECT_GRANT = "grant"
PERMISSION_EFFECT_MUTE = "mute"


class SalesforceConnectionExtra(BaseModel):
    """Shape stored on AppConnection.extra for a Salesforce org."""

    org_id: str
    instance_url: str
    owd: dict[str, str]


class SalesforcePermissionExtra(BaseModel):
    """Shape stored on HAS_PERMISSION.extra for Salesforce profile permissions.

    Object and field access to the same SObject are modeled as separate
    HAS_PERMISSION edges from a Profile to one Resource (kind ``object``).
    Field-scoped edges list the affected field API names in ``fields``.
    """

    access_type: Literal["object", "field"]
    fields: list[str] | None = None

    @model_validator(mode="after")
    def validate_fields_for_access_type(self) -> SalesforcePermissionExtra:
        if self.access_type == "field":
            if not self.fields:
                msg = "fields is required and must be non-empty when access_type is 'field'"
                raise ValueError(msg)
            return self

        if self.fields:
            msg = "fields must be omitted when access_type is 'object'"
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


class SalesforceAppIdentityExtra(BaseModel):
    """Optional shape stored on AppIdentity.extra for Salesforce users."""

    role_id: str | None = None
    role_name: str | None = None


class SalesforceProfileExtra(BaseModel):
    """Optional shape stored on Profile.extra for Salesforce-backed profiles."""

    kind: Literal["profile", "permission_set", "permission_set_group", "muting_permission_set"]
