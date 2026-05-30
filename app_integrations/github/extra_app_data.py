"""Helpers for per-app metadata stored on ``UserIdentity.extra_app_data``."""

from __future__ import annotations

from typing import Any

from app_integrations.github.models import UserIdentity

_GITHUB_KEY = "github"


def get_github_extra(identity: UserIdentity) -> dict[str, str]:
    """Return the GitHub slice of *identity.extra_app_data*, or an empty dict."""
    raw = identity.extra_app_data.get(_GITHUB_KEY)
    if not isinstance(raw, dict):
        return {}
    result: dict[str, str] = {}
    if raw.get("user_id"):
        result["user_id"] = str(raw["user_id"])
    if raw.get("username"):
        result["username"] = str(raw["username"])
    return result


def github_is_linked(identity: UserIdentity) -> bool:
    github = get_github_extra(identity)
    return bool(github.get("user_id") and github.get("username"))


def set_github_extra(
    identity: UserIdentity,
    *,
    user_id: str,
    username: str,
) -> None:
    """Persist GitHub user id and login under ``extra_app_data.github``."""
    extra: dict[str, Any] = dict(identity.extra_app_data)
    extra[_GITHUB_KEY] = {"user_id": user_id, "username": username}
    identity.extra_app_data = extra
