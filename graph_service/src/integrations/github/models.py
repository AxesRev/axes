from __future__ import annotations

from pydantic import BaseModel


class GithubConnectionExtra(BaseModel):
    """Extra fields stored on an AppConnection node for a GitHub installation."""

    org_id: int
    login: str
    type: str
    html_url: str
    avatar_url: str | None = None


class GithubIdentityExtra(BaseModel):
    """Extra fields stored on an AppIdentity node for a GitHub user."""

    login: str
    name: str | None = None
    email: str | None = None
    type: str
    html_url: str
    avatar_url: str | None = None


class GithubResourceExtra(BaseModel):
    """Extra fields stored on a Resource node for a GitHub repository."""

    repo_id: int
    full_name: str
    private: bool
    default_branch: str
    html_url: str
    visibility: str


class GithubTeamExtra(BaseModel):
    """Metadata for a GitHub team mapped to a Group node."""

    team_id: int
    slug: str
    name: str
    description: str | None = None
    html_url: str | None = None
    privacy: str | None = None
    parent_slug: str | None = None
