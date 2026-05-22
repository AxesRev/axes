"""GitHub repository permissions via GraphQL → HAS_PERMISSION edges."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Literal

from github import GithubException
from github.MainClass import Github
from github.Repository import Repository

from nodes.app_connection import AppConnection
from nodes.app_identity import AppIdentity
from nodes.group import Group
from nodes.resource import Resource

logger = logging.getLogger(__name__)

_GITHUB_APP = "github"

DEFAULT_REPO_BATCH_SIZE = 25
_COLLABORATORS_FRAGMENT = """
    collaborators(first: 100) {
      edges {
        permission
        node {
          login
        }
      }
    }"""
_ORG_TEAMS_FRAGMENT = """
    teams(first: 100) {
      pageInfo {
        hasNextPage
      }
      edges {
        node {
          slug
          repositories(first: 100) {
            pageInfo {
              hasNextPage
            }
            edges {
              permission
              node {
                name
                owner {
                  login
                }
              }
            }
          }
        }
      }
    }"""


@dataclass(frozen=True)
class RepoPermissionGrant:
    """One subject's permission on a repository."""

    repo_full_name: str
    subject_kind: Literal["user", "team"]
    subject_key: str
    permission: str


def repo_alias(index: int) -> str:
    """Return a stable GraphQL alias for a repo block."""
    return f"repo{index}"


def build_repo_collaborators_graphql(repos: list[Repository]) -> str:
    """Build a multi-repo GraphQL query for direct collaborator access."""
    if not repos:
        return "query { __typename }"

    blocks: list[str] = []
    for index, repo in enumerate(repos):
        owner, name = repo.full_name.split("/", 1)
        alias = repo_alias(index)
        blocks.append(
            f"""
  {alias}: repository(owner: {_gql_string(owner)}, name: {_gql_string(name)}) {{
{_COLLABORATORS_FRAGMENT}
  }}"""
        )

    return f"query {{{''.join(blocks)}\n}}"


def build_org_team_permissions_graphql(org_login: str) -> str:
    """Build a GraphQL query for team → repository permissions via the org."""
    return f"""query {{
  organization(login: {_gql_string(org_login)}) {{
{_ORG_TEAMS_FRAGMENT}
  }}
}}"""


def parse_repo_collaborator_permissions_response(
    repos: list[Repository],
    response: dict[str, object],
) -> list[RepoPermissionGrant]:
    """Parse collaborator permissions from a batched repository query."""
    data = response.get("data")
    if not isinstance(data, dict):
        logger.warning("permissions_graphql_missing_data")
        return []

    grants: list[RepoPermissionGrant] = []
    for index, repo in enumerate(repos):
        repo_data = data.get(repo_alias(index))
        if not isinstance(repo_data, dict):
            logger.warning("permissions_graphql_repo_missing full_name=%s", repo.full_name)
            continue

        grants.extend(_parse_collaborator_grants(repo.full_name, repo_data))

    return grants


def parse_org_team_permissions_response(
    *,
    org_login: str,
    target_repo_uris: set[str],
    response: dict[str, object],
) -> list[RepoPermissionGrant]:
    """Parse team permissions from an organization teams query."""
    data = response.get("data")
    if not isinstance(data, dict):
        logger.warning("permissions_graphql_missing_data")
        return []

    organization = data.get("organization")
    if not isinstance(organization, dict):
        logger.warning("permissions_graphql_org_missing org=%s", org_login)
        return []

    teams = organization.get("teams")
    if not isinstance(teams, dict):
        return []

    page_info = teams.get("pageInfo")
    if isinstance(page_info, dict) and page_info.get("hasNextPage") is True:
        logger.warning("permissions_graphql_teams_truncated org=%s", org_login)

    edges = teams.get("edges")
    if not isinstance(edges, list):
        return []

    grants: list[RepoPermissionGrant] = []
    for team_edge in edges:
        if not isinstance(team_edge, dict):
            continue
        team_node = team_edge.get("node")
        if not isinstance(team_node, dict):
            continue
        slug = team_node.get("slug")
        if not isinstance(slug, str):
            continue

        repositories = team_node.get("repositories")
        if not isinstance(repositories, dict):
            continue

        repo_page_info = repositories.get("pageInfo")
        if isinstance(repo_page_info, dict) and repo_page_info.get("hasNextPage") is True:
            logger.warning("permissions_graphql_team_repos_truncated org=%s team=%s", org_login, slug)

        repo_edges = repositories.get("edges")
        if not isinstance(repo_edges, list):
            continue

        for repo_edge in repo_edges:
            if not isinstance(repo_edge, dict):
                continue
            permission = repo_edge.get("permission")
            repo_node = repo_edge.get("node")
            if not isinstance(permission, str) or not isinstance(repo_node, dict):
                continue

            repo_name = repo_node.get("name")
            if not isinstance(repo_name, str):
                continue

            owner_login = org_login
            owner = repo_node.get("owner")
            if isinstance(owner, dict):
                owner_value = owner.get("login")
                if isinstance(owner_value, str):
                    owner_login = owner_value

            repo_full_name = f"{owner_login}/{repo_name}"
            if repo_full_name not in target_repo_uris:
                continue

            grants.append(
                RepoPermissionGrant(
                    repo_full_name=repo_full_name,
                    subject_kind="team",
                    subject_key=slug,
                    permission=permission,
                )
            )

    return grants


def fetch_repo_permissions(
    gh: Github,
    repos: list[Repository],
    *,
    org_login: str | None = None,
    batch_size: int = DEFAULT_REPO_BATCH_SIZE,
) -> list[RepoPermissionGrant]:
    """Fetch collaborator and team permissions for repositories via GraphQL."""
    grants: list[RepoPermissionGrant] = []
    target_repo_uris = {repo.full_name for repo in repos}

    for start in range(0, len(repos), batch_size):
        batch = repos[start : start + batch_size]
        query = build_repo_collaborators_graphql(batch)
        _headers, response = gh.requester.graphql_query(query, {})
        grants.extend(parse_repo_collaborator_permissions_response(batch, response))

    if org_login is not None:
        query = build_org_team_permissions_graphql(org_login)
        _headers, response = gh.requester.graphql_query(query, {})
        grants.extend(
            parse_org_team_permissions_response(
                org_login=org_login,
                target_repo_uris=target_repo_uris,
                response=response,
            )
        )

    return grants


async def sync_repo_permissions(
    gh: Github,
    repos: list[Repository],
    resources_by_uri: dict[str, Resource],
    connection: AppConnection,
    *,
    org_login: str | None = None,
) -> None:
    """Upsert teams/users and write HAS_PERMISSION edges for repository access."""
    grants = fetch_repo_permissions(gh, repos, org_login=org_login)
    logger.info("permissions_fetched grants=%s repos=%s", len(grants), len(repos))

    for grant in grants:
        resource = resources_by_uri.get(grant.repo_full_name)
        if resource is None:
            logger.warning("permissions_skip_unknown_repo full_name=%s", grant.repo_full_name)
            continue

        if grant.subject_kind == "user":
            identity = await _get_or_create_identity_by_login(gh, grant.subject_key, connection)
            if identity is None:
                continue
            await _connect_resource_permission(identity, resource, grant.permission)
            continue

        group = await _upsert_group(grant.subject_key, connection)
        await _connect_resource_permission(group, resource, grant.permission)


def _gql_string(value: str) -> str:
    return json.dumps(value)


def _parse_collaborator_grants(repo_full_name: str, repo_data: dict[str, object]) -> list[RepoPermissionGrant]:
    collaborators = repo_data.get("collaborators")
    if not isinstance(collaborators, dict):
        return []

    edges = collaborators.get("edges")
    if not isinstance(edges, list):
        return []

    grants: list[RepoPermissionGrant] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        permission = edge.get("permission")
        node = edge.get("node")
        if not isinstance(permission, str) or not isinstance(node, dict):
            continue
        login = node.get("login")
        if not isinstance(login, str):
            continue
        grants.append(
            RepoPermissionGrant(
                repo_full_name=repo_full_name,
                subject_kind="user",
                subject_key=login,
                permission=permission,
            )
        )
    return grants


async def _get_or_create_identity_by_login(
    gh: Github,
    login: str,
    connection: AppConnection,
) -> AppIdentity | None:
    candidates = await AppIdentity.nodes.filter(app=_GITHUB_APP, name=login).all()
    for identity in candidates:
        if await identity.connection.is_connected(connection):
            return identity

    try:
        user = gh.get_user(login)
    except GithubException:
        logger.warning("permissions_skip_unknown_user login=%s", login)
        return None

    from integrations.github.fetcher import _upsert_identity

    return await _upsert_identity(user, connection)


async def _upsert_group(slug: str, connection: AppConnection) -> Group:
    candidates = await Group.nodes.filter(name=slug).all()
    for group in candidates:
        if await group.connection.is_connected(connection):
            return group

    group = await Group(name=slug).save()
    await group.connection.connect(connection)
    logger.info("created_group slug=%s", slug)
    return group


async def _connect_resource_permission(
    subject: AppIdentity | Group,
    resource: Resource,
    permission: str,
) -> None:
    rel = subject.permitted_resources
    await rel.connect(resource, {"permission": permission})
