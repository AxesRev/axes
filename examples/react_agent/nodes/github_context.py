"""Node that loads GitHub context for the authenticated user.

Runs immediately after __start__ to populate state with the user's
repos and organizations before any other processing occurs.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from github import Auth, Github, GithubException
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.state import State

logger = logging.getLogger(__name__)


def _fetch_github_context(pat: str, github_username: str) -> dict[str, list[str]]:
    """Fetch repo full names and org logins for *github_username* using the service PAT.

    Because the target user's org memberships may be private (hidden from the public
    ``/users/{username}/orgs`` endpoint), we take a two-pronged approach:

    1. Collect the user's own public repos directly from their profile.
    2. Walk through every org the *service PAT* belongs to and check whether the
       target user is also a member.  For each shared org we include the org itself
       and all its repos that the service PAT can see.
    """
    auth = Auth.Token(pat)
    with Github(auth=auth) as gh:
        named_user = gh.get_user(github_username)

        # Own public repos (may be empty for users with no public activity)
        repos: list[str] = [repo.full_name for repo in named_user.get_repos()]
        orgs: list[str] = []

        # Discover shared orgs via the service account
        service_user = gh.get_user()
        for svc_org in service_user.get_orgs():
            try:
                org_obj = gh.get_organization(svc_org.login)
                if not org_obj.has_in_members(named_user):
                    continue
                orgs.append(svc_org.login)
                for org_repo in org_obj.get_repos():
                    if org_repo.full_name not in repos:
                        repos.append(org_repo.full_name)
            except GithubException as exc:
                logger.warning("load_github_context: skipping org %s — %s", svc_org.login, exc)
                continue

    return {"github_repos": repos, "github_orgs": orgs}


async def load_github_context(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Fetch the requesting user's GitHub repos and organizations and store them in state.

    Uses the service PAT to look up the specific user identified by
    ``github_username`` (resolved from the DB via OAuth, never from user input).
    Skips gracefully if either ``github_pat`` or ``github_username`` is absent.
    """
    pat = runtime.context.github_pat
    github_username = runtime.context.github_username

    if not pat or not github_username:
        logger.info("load_github_context: skipped — github_pat or github_username not set")
        return {}

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _fetch_github_context, pat, github_username)

    logger.info(
        "load_github_context: fetched github context",
        extra={
            "github_username": github_username,
            "repo_count": len(result["github_repos"]),
            "org_count": len(result["github_orgs"]),
        },
    )
    return result
