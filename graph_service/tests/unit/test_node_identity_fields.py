"""Unit tests for shared node identity fields on BaseNode."""

from __future__ import annotations

import pytest
from neomodel.properties import Property

from nodes import AppConnection, AppIdentity, Group, Identity, Profile, Resource, Tenant


@pytest.mark.parametrize(
    "node_cls",
    [Tenant, Identity, AppConnection, AppIdentity, Group, Resource, Profile],
)
@pytest.mark.unit
def test_all_nodes_inherit_optional_app_and_external_id(node_cls: type) -> None:
    properties = node_cls.defined_properties(aliases=False, rels=False)

    for field_name in ("app", "external_id"):
        prop = properties[field_name]
        assert isinstance(prop, Property)
        assert prop.required is False


@pytest.mark.unit
def test_resource_does_not_require_external_id() -> None:
    properties = Resource.defined_properties(aliases=False, rels=False)

    assert "name" in properties
    assert properties["name"].required is True
    assert properties["external_id"].required is False
