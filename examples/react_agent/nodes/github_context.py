"""Node that loads GitHub context for the authenticated user.

Runs immediately after __start__ to populate state with the user's
repos and organizations before any other processing occurs.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from github import Auth, Github
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.state import State

logger = logging.getLogger(__name__)


def _fetch_github_context(pat: str, github_username: str) -> dict[str, list[str]]:
    """Fetch repo full names and org logins for *github_username* using the service PAT."""
    auth = Auth.Token(pat)
    with Github(auth=auth) as gh:
        user = gh.get_user(github_username)
        repos = [repo.full_name for repo in user.get_repos()]
        orgs = [org.login for org in user.get_orgs()]
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
