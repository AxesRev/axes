"""Unit tests for HAS_PERMISSION relationship properties."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_has_permission_rel_exposes_permission_and_optional_extra() -> None:
    from nodes.relationships import HasPermissionRel  # noqa: PLC0415

    property_names = set(HasPermissionRel.defined_properties(aliases=False, rels=False).keys())

    assert property_names == {"permission", "effect", "extra"}


@pytest.mark.unit
def test_has_permission_rel_effect_choices() -> None:
    from nodes.relationships import HasPermissionRel  # noqa: PLC0415

    effect_prop = HasPermissionRel.defined_properties(aliases=False, rels=False)["effect"]

    assert effect_prop.required is False
    assert set(effect_prop.choices.keys()) == {"grant", "mute"}


@pytest.mark.unit
def test_profile_uses_has_permission_rel_model() -> None:
    from nodes.profile import Profile  # noqa: PLC0415
    from nodes.relationships import HasPermissionRel  # noqa: PLC0415

    assert Profile.permitted_resources.definition["model"] is HasPermissionRel
