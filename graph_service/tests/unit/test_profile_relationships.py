"""Unit tests for Profile node relationships."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_app_identity_links_to_profile_via_assigned_profile() -> None:
    from nodes.app_identity import AppIdentity  # noqa: PLC0415
    from nodes.profile import Profile  # noqa: PLC0415

    assert AppIdentity.profiles.definition["relation_type"] == "ASSIGNED_PROFILE"
    assert Profile.assigned_identities.definition["relation_type"] == "ASSIGNED_PROFILE"


@pytest.mark.unit
def test_group_links_to_profile_via_assigned_profile() -> None:
    from nodes.group import Group  # noqa: PLC0415
    from nodes.profile import Profile  # noqa: PLC0415

    assert Group.profiles.definition["relation_type"] == "ASSIGNED_PROFILE"
    assert Profile.assigned_groups.definition["relation_type"] == "ASSIGNED_PROFILE"


@pytest.mark.unit
def test_profile_links_to_profile_via_member_of() -> None:
    from nodes.profile import Profile  # noqa: PLC0415

    assert Profile.groups.definition["relation_type"] == "MEMBER_OF"
    assert Profile.profile_members.definition["relation_type"] == "MEMBER_OF"
