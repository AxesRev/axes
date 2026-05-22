"""Unit tests for GitHub repository permission GraphQL helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from integrations.github.ingestion.permissions import (
    RepoPermissionGrant,
    build_org_team_permissions_graphql,
    build_repo_collaborators_graphql,
    parse_org_team_permissions_response,
    parse_repo_collaborator_permissions_response,
    repo_alias,
)


def _mock_repo(full_name: str) -> MagicMock:
    repo = MagicMock()
    repo.full_name = full_name
    return repo


@pytest.mark.unit
def test_repo_alias() -> None:
    assert repo_alias(0) == "repo0"
    assert repo_alias(3) == "repo3"


@pytest.mark.unit
def test_build_repo_collaborators_graphql_single_repo() -> None:
    query = build_repo_collaborators_graphql([_mock_repo("myorg/repo-a")])

    assert 'repo0: repository(owner: "myorg", name: "repo-a")' in query
    assert "collaborators(first: 100)" in query
    assert "permission" in query
    assert "login" in query
    assert "teams(first: 100)" not in query


@pytest.mark.unit
def test_build_repo_collaborators_graphql_multiple_repos() -> None:
    repos = [_mock_repo("myorg/repo-a"), _mock_repo("myorg/repo-b")]
    query = build_repo_collaborators_graphql(repos)

    assert 'repo0: repository(owner: "myorg", name: "repo-a")' in query
    assert 'repo1: repository(owner: "myorg", name: "repo-b")' in query


@pytest.mark.unit
def test_build_repo_collaborators_graphql_escapes_special_characters() -> None:
    query = build_repo_collaborators_graphql([_mock_repo('my"org/weird-repo')])

    assert 'owner: "my\\"org"' in query
    assert 'name: "weird-repo"' in query


@pytest.mark.unit
def test_build_repo_collaborators_graphql_empty_repos() -> None:
    assert build_repo_collaborators_graphql([]) == "query { __typename }"


@pytest.mark.unit
def test_build_org_team_permissions_graphql() -> None:
    query = build_org_team_permissions_graphql("myorg")

    assert 'organization(login: "myorg")' in query
    assert "teams(first: 100)" in query
    assert "repositories(first: 100)" in query
    assert "slug" in query


@pytest.mark.unit
def test_parse_repo_collaborator_permissions_response_maps_users() -> None:
    repos = [_mock_repo("myorg/repo-a")]
    response = {
        "data": {
            "repo0": {
                "collaborators": {
                    "edges": [
                        {
                            "permission": "ADMIN",
                            "node": {"login": "alice"},
                        },
                        {
                            "permission": "READ",
                            "node": {"login": "bob"},
                        },
                    ]
                },
            }
        }
    }

    grants = parse_repo_collaborator_permissions_response(repos, response)

    assert grants == [
        RepoPermissionGrant("myorg/repo-a", "user", "alice", "ADMIN"),
        RepoPermissionGrant("myorg/repo-a", "user", "bob", "READ"),
    ]


@pytest.mark.unit
def test_parse_org_team_permissions_response_maps_teams() -> None:
    response = {
        "data": {
            "organization": {
                "teams": {
                    "pageInfo": {"hasNextPage": False},
                    "edges": [
                        {
                            "node": {
                                "slug": "platform",
                                "repositories": {
                                    "pageInfo": {"hasNextPage": False},
                                    "edges": [
                                        {
                                            "permission": "WRITE",
                                            "node": {
                                                "name": "repo-a",
                                                "owner": {"login": "myorg"},
                                            },
                                        },
                                        {
                                            "permission": "ADMIN",
                                            "node": {
                                                "name": "other-repo",
                                                "owner": {"login": "myorg"},
                                            },
                                        },
                                    ],
                                },
                            }
                        }
                    ],
                }
            }
        }
    }

    grants = parse_org_team_permissions_response(
        org_login="myorg",
        target_repo_uris={"myorg/repo-a"},
        response=response,
    )

    assert grants == [
        RepoPermissionGrant("myorg/repo-a", "team", "platform", "WRITE"),
    ]


@pytest.mark.unit
def test_parse_repo_collaborator_permissions_response_skips_missing_repo_block() -> None:
    repos = [_mock_repo("myorg/repo-a"), _mock_repo("myorg/repo-b")]
    response = {
        "data": {
            "repo0": {
                "collaborators": {"edges": []},
            }
        }
    }

    grants = parse_repo_collaborator_permissions_response(repos, response)

    assert grants == []
