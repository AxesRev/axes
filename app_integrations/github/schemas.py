"""Pydantic schemas for the GitHub identity-linking integration."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class IdentityLinked(BaseModel):
    """Returned when a Slack user has a confirmed GitHub mapping."""

    status: Literal["LINKED"]
    slack_user_id: str
    github_user_id: str
    github_email: str
    github_installation_id: str = ""


class IdentityNotLinked(BaseModel):
    """Returned when no GitHub mapping exists for the Slack user."""

    status: Literal["NOT_LINKED"]
    connect_url: str


class AccessRequestResult(BaseModel):
    """Wrapper returned by handle_access_request."""

    linked: bool
    identity: IdentityLinked | None = None
    not_linked: IdentityNotLinked | None = None
