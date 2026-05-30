"""Unit tests for GitHub OAuth user/email fetch helpers."""

from __future__ import annotations

import pytest

from app_integrations.github.oauth_user import (
    _pick_primary_email,
    normalize_github_email,
)


@pytest.mark.unit
def test_normalize_github_email() -> None:
    assert normalize_github_email("  Alice@Example.COM ") == "alice@example.com"
    assert normalize_github_email("not-an-email") is None


@pytest.mark.unit
def test_pick_primary_email_prefers_primary_verified() -> None:
    email = _pick_primary_email(
        [
            {"email": "other@example.com", "primary": False, "verified": True},
            {"email": "primary@example.com", "primary": True, "verified": True},
        ]
    )
    assert email == "primary@example.com"


@pytest.mark.unit
def test_pick_primary_email_falls_back_to_first_verified() -> None:
    email = _pick_primary_email(
        [
            {"email": "first@example.com", "primary": False, "verified": True},
            {"email": "second@example.com", "primary": False, "verified": True},
        ]
    )
    assert email == "first@example.com"
