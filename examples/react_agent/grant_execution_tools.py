"""Per-app tool loaders for the access grant execution subgraph."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.nodes.github_openapi_tools import build_openapi_toolkit

logger = logging.getLogger(__name__)

AppGrantToolLoader = Callable[[Runtime[Context]], list[Any]]


def _load_github_grant_tools(runtime: Runtime[Context]) -> list[Any]:
    return build_openapi_toolkit(runtime).get_tools()


def _load_salesforce_grant_tools(runtime: Runtime[Context]) -> list[Any]:
    return []


GRANT_EXECUTION_TOOLS_BY_APP: dict[str, AppGrantToolLoader] = {
    "github": _load_github_grant_tools,
    "salesforce": _load_salesforce_grant_tools,
}


def load_grant_execution_tools(*, runtime: Runtime[Context], selected_apps: list[str]) -> list[Any]:
    """Load grant-execution tools for each app in ``selected_apps``."""
    tools: list[Any] = []
    loaded_apps: list[str] = []

    for app in selected_apps:
        loader = GRANT_EXECUTION_TOOLS_BY_APP.get(app)
        if loader is None:
            logger.warning("load_grant_execution_tools: no tools registered for app=%s", app)
            continue

        app_tools = loader(runtime)
        tools.extend(app_tools)
        loaded_apps.append(app)
        logger.info(
            "load_grant_execution_tools: app=%s tool_count=%d",
            app,
            len(app_tools),
        )

    logger.info(
        "load_grant_execution_tools: selected=%s loaded_apps=%s total_tools=%d",
        selected_apps,
        loaded_apps,
        len(tools),
    )
    return tools
