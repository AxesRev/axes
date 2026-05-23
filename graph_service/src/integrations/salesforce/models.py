from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator


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


def build_object_permission_extra() -> dict[str, object]:
    """Return serialized extra payload for object-level Salesforce access."""
    return SalesforcePermissionExtra(access_type="object").model_dump()


def build_field_permission_extra(*fields: str) -> dict[str, object]:
    """Return serialized extra payload for field-level Salesforce access."""
    return SalesforcePermissionExtra(
        access_type="field",
        fields=list(fields),
    ).model_dump()
